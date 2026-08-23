#!/usr/bin/env python3
"""
Git 仓库服务 - remote URL 解析、SSH config 别名与主机名对齐。

负责 Git 相关的基础设施：解析 scp-like / ssh:// / https:// URL、生成与反解
SSH config 别名、对齐标签与仓库真实 hostname（适配私有化 Git）等。
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from ...utils.process import git

from ....i18n import _
from ....language import K
from ....ui.icons import ok as _ok
from ....ui.icons import warn as _warn
from ....ui.output import ICON_WARN, confirm, print


from ....ui.tip import render_business_error


class GitRepoService:
    """Git 仓库服务：URL 解析 / 别名生成 / hostname 对齐。"""

    def __init__(
        self,
        ssh_dir: Path,
        config_manager,
        state_manager,
        keystore,
        error_reporter: Callable[[str], None],
    ):
        self.ssh_dir = ssh_dir
        self.config_manager = config_manager
        self.state_manager = state_manager
        self.keystore = keystore
        self._error = error_reporter

    # ------------------------------------------------------------------
    # URL 解析
    # ------------------------------------------------------------------

    def parse_git_url(self, url: str) -> tuple[str, str, str] | None:
        """解析 Git URL，支持 ssh://、git@、https:// 三种格式"""
        # scp-like 格式: git@github.com:user/repo.git
        ssh_pattern = r"git@([^:]+):([^/]+)/(.+?)(?:\.git)?$"
        match = re.match(ssh_pattern, url)
        if match:
            hostname, user, repo = match.groups()
            return (self.platform_from_hostname(hostname), user, repo)

        # 带协议前缀的 SSH 格式: ssh://git@host/user/repo.git
        #  或 ssh://git@host:port/user/repo.git
        ssh2_pattern = r"ssh://(?:git@)?([^/:]+)(?::\d+)?/([^/]+)/(.+?)(?:\.git)?$"
        match = re.match(ssh2_pattern, url)
        if match:
            hostname, user, repo = match.groups()
            return (self.platform_from_hostname(hostname), user, repo)

        # HTTPS 格式: https://host/user/repo.git
        https_pattern = r"https?://([^/]+)/([^/]+)/(.+?)(?:\.git)?$"
        match = re.match(https_pattern, url)
        if match:
            hostname, user, repo = match.groups()
            return (self.platform_from_hostname(hostname), user, repo)

        return None

    @staticmethod
    def platform_from_hostname(hostname: str) -> str:
        """从主机名推断平台标识（取首段，去掉可能的端口）"""
        hostname = hostname.split(":")[0]
        if "-" in hostname:
            return hostname.split("-")[0]
        return hostname.split(".")[0]

    # ------------------------------------------------------------------
    # 主机名 / 别名
    # ------------------------------------------------------------------

    def get_hostname_for_label(self, label: str) -> str:
        """根据标签获取主机名（优先使用 add 时记录的映射）"""
        label_lower = label.lower()
        hosts = self.state_manager.read_hosts()
        if hosts.get(label_lower):
            return hosts[label_lower]

        hostname_map = {
            "github": "github.com",
            "gitlab": "gitlab.com",
            "gitee": "gitee.com",
            "bitbucket": "bitbucket.org",
        }
        for key, host in hostname_map.items():
            if key in label_lower:
                return host
        return "github.com"

    def get_host_alias(self, label: str) -> str:
        """生成 SSH config 别名（统一小写，避免大小写变体冲突）

        别名格式为 '{主域名}-{label}'，如 github.com-Eavelabs。
        主域名 = 完整 hostname 移除最后一个 '.' 之后的 TLD 段，再把剩余的
        '.' 替换为 '-'，避免不同服务器的主域名前缀冲突。
        """
        hostname = self.get_hostname_for_label(label)
        # 移除最后一个 '.' 之后的 TLD 段（如 .com/.org/.net）
        base = hostname
        if "." in hostname:
            base = hostname.rsplit(".", 1)[0]
        # 剩余 '.' 替换为 '-'
        main_domain = base.replace(".", "-")
        return f"{main_domain}-{label.lower()}"

    def resolve_label_from_alias(self, host_alias: str) -> str | None:
        """从 SSH config 别名反解标签

        别名格式为 '{主机名首段}-{label}'，但主机名首段本身可能含连字符，
        因此遍历 hosts 映射与密钥标签，用完整别名精确匹配。
        """
        host_alias_lower = host_alias.lower()
        candidates = list(self.state_manager.read_hosts().keys())
        candidates.extend(self.keystore.scan_all_keys().keys())
        for label in candidates:
            if self.get_host_alias(label) == host_alias_lower:
                return label
        return None

    @staticmethod
    def extract_host_from_url(url: str) -> str | None:
        """从 scp-like Git URL（git@host:user/repo.git）提取 host/别名段。"""
        match = re.match(r"git@([^:]+):", url)
        return match.group(1) if match else None

    def resolve_repo_hostname(self, url: str) -> str | None:
        """从 Git remote URL 提取真实主机名（别名优先从 SSH config HostName 反查）"""
        ssh2_match = re.match(r"ssh://(?:git@)?([^/:]+)", url)
        host = ssh2_match.group(1) if ssh2_match else None
        if not host:
            host = self.extract_host_from_url(url)
        if not host:
            https_match = re.match(r"https?://([^/]+)/", url)
            host = https_match.group(1) if https_match else None
        if not host:
            return None

        # 若 SSH config 中存在该 Host 块，反查其 HostName 得到真实域名
        resolved = self.config_manager.get_hostname(host)
        if resolved:
            return resolved
        return host

    def extract_ssh_config_block(self, host_alias: str) -> list[str]:
        """从 SSH config 中提取指定 Host 别名对应的配置块（含 Host 行及缩进项）。"""
        config_file = self.config_manager.config_file
        if not config_file.exists():
            return []
        try:
            lines = config_file.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            return []

        block: list[str] = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            low = stripped.lower()
            if low.startswith("host ") or low == "host":
                host_patterns = [p.strip() for p in stripped.split(" ", 1)[1].split()] if " " in stripped else []
                if host_alias in host_patterns:
                    block.append(stripped)
                    for nxt in lines[i + 1 :]:
                        nxt_strip = nxt.strip()
                        if not nxt_strip:
                            break
                        if not (nxt.startswith(" ") or nxt.startswith("\t")):
                            break
                        block.append(nxt_strip)
                    return block
        return []

    # ------------------------------------------------------------------
    # hostname 对齐与别名维护
    # ------------------------------------------------------------------

    def align_hostname_with_repo(self, label: str, repo_hostname: str | None, skip_confirm: bool) -> bool:
        """确保标签映射到仓库的真实 hostname（适配私有化 Git）"""
        if not repo_hostname:
            return True
        current = self.get_hostname_for_label(label)
        if current == repo_hostname:
            return True

        render_business_error(
            _(K.msg.hostname_differs, host=repo_hostname, label=label, cur=current),
            icon=ICON_WARN,
            hint="\n".join(
                [
                    _(K.msg.private_server),
                    _(K.msg.need_ssh_config, host=repo_hostname),
                ]
            ),
        )

        if skip_confirm:
            self.state_manager.write_host(label, repo_hostname)
            print(_ok(K.msg.host_updated, label=label, host=repo_hostname))
            return True

        if confirm(_(K.msg.create_matching, host=repo_hostname), default="y"):
            self.state_manager.write_host(label, repo_hostname)
            print(_ok(K.msg.host_updated, label=label, host=repo_hostname))
            return True
        self._error(_warn(K.msg.skipped_no_mapping))
        return False

    def update_ssh_config_alias(self, label: str, key_file: Path) -> None:
        """自动更新 SSH config 别名配置"""
        hostname = self.get_hostname_for_label(label)
        host_alias = self.get_host_alias(label)

        self.config_manager.update_host(host_alias, hostname, key_file.resolve())
        self.state_manager.write_host(label, hostname)
        print(_(K.msg.ssh_config_alias, alias=host_alias, hostname=hostname))
        print(_(K.msg.alias_usage, alias=host_alias))

    def remove_ssh_config_alias(self, label: str) -> None:
        """删除 SSH config 别名配置"""
        host_alias = self.get_host_alias(label)

        self.config_manager.remove_host(host_alias)
        self.state_manager.remove_host(label)
        print(_(K.msg.alias_removed, alias=host_alias))

    def rename_ssh_config_alias(self, old_label: str, new_label: str, new_key_file: Path) -> None:
        """重命名 SSH config 别名配置（主机名保持不变，同一把密钥换标签）"""
        hostname = self.get_hostname_for_label(old_label)
        old_alias = self.get_host_alias(old_label)
        new_alias = self.get_host_alias(new_label)

        if old_alias != new_alias:
            self.config_manager.remove_host(old_alias)
            self.config_manager.update_host(new_alias, hostname, new_key_file.resolve())
            self.state_manager.write_host(new_label, hostname)
            print(_(K.msg.alias_updated, old=old_alias, new=new_alias))

    def detect_repo_key_label(self, repo_path: str | Path = ".") -> str | None:
        """检测当前 Git 仓库正在使用的密钥标签（仓库级）"""
        repo = Path(repo_path).resolve()
        if not (repo / ".git").exists():
            return None
        try:
            result = git(repo, "remote", "get-url", "origin")
            remote_url = result.stdout.strip()
        except (subprocess.CalledProcessError, OSError):
            return None

        host_alias = self.extract_host_from_url(remote_url)
        if not host_alias:
            return None
        return self.resolve_label_from_alias(host_alias)
