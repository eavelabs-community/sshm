#!/usr/bin/env python3
"""
作者服务 - 作者信息的解析 / 关联 / 应用（可复用的服务层）。

负责：从状态文件 / 公钥注释 / remote URL 解析作者信息、读取 git 配置、
以及"密钥↔作者自动联动"（切换密钥时自动设置 git user）。命令编排层通过
本服务使用作者能力，避免在多个命令里重复实现。
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from ....i18n import _
from ....language import K
from ....ui.output import ICON_WARN, print
from ...utils.process import git
from ...errors import ErrCode


class AuthorService:
    """作者服务：作者信息解析与应用。"""

    def __init__(self, state_manager, keystore, gitrepo, fail: Callable[..., None]):
        self.state_manager = state_manager
        self.keystore = keystore
        self.gitrepo = gitrepo
        self._fail = fail

    # ------------------------------------------------------------------
    # git 配置读取
    # ------------------------------------------------------------------

    def git_get_config(self, repo_path: Path, scope: str, key: str) -> str | None:
        """读取 git 配置项（local/global）"""
        try:
            result = git(repo_path, "config", f"--{scope}", key)
            return result.stdout.strip() or None
        except (subprocess.CalledProcessError, OSError):
            return None

    # ------------------------------------------------------------------
    # 作者信息解析
    # ------------------------------------------------------------------

    def get_author_info(
        self,
        label: str,
        name: str | None = None,
        email: str | None = None,
        repo_path: str | Path | None = None,
        infer_from_remote: bool = True,
    ) -> dict[str, str] | None:
        """按优先级获取标签对应的作者信息

        infer_from_remote：当标签无显式作者名时，是否从 remote URL 推断用户名。
        在 clone 场景应传 False，因为 clone 的 remote 是 sshm 别名 URL
        （git@github-work:org/repo.git），其 user 段是组织名而非作者名。
        """
        label_lower = label.lower()
        result: dict[str, str] = {"name": name or "", "email": email or ""}

        # 1. 状态文件中的 authors 映射（add 时自动记录）
        stored = self.state_manager.read_authors().get(label_lower)
        if stored:
            if not result["name"]:
                result["name"] = stored.get("name", "")
            if not result["email"]:
                result["email"] = stored.get("email", "")

        # 2. 从公钥注释提取邮箱（-C email 写入）
        if not result["email"]:
            result["email"] = self.extract_email_from_pubkey(label_lower) or ""

        # 3. 从 remote URL 推断用户名（最低优先级）
        if not result["name"] and repo_path is not None and infer_from_remote:
            result["name"] = self.infer_author_name_from_remote(Path(repo_path)) or ""

        if not (result["name"] or result["email"]):
            key_type = self.keystore.detect_key_type_for_label(label)
            if not key_type:
                msg = _(K.err.key_not_found_short, label=label)
                self._fail(msg, hint=_(K.msg.use_all_keys_tip))
                return None
            msg = _(K.msg.not_usable_author, label=label)
            self._fail(
                msg,
                icon=ICON_WARN,
                hint="\n".join(
                    [
                        _(K.msg.available_remedies),
                        f'   - sshm key create {label} <email> --name "name"  # ' + _(K.msg.recreate_key),
                        f'   - sshm author add {label} --name "name" --email <email>  # ' + _(K.msg.temp_override),
                    ]
                ),
            )
            return None

        return result

    def extract_email_from_pubkey(self, label: str) -> str | None:
        """从带标签的公钥注释提取邮箱（委托 KeyStore）"""
        key_type = self.keystore.detect_key_type_for_label(label)
        if not key_type:
            return None
        return self.keystore.extract_email_from_pubkey(key_type, label)

    def infer_author_name_from_remote(self, repo_path: Path) -> str | None:
        """从 remote URL 推断用户名（git@github.com:allureyc/repo.git → allureyc）"""
        try:
            result = git(repo_path, "remote", "get-url", "origin")
            parsed = self.gitrepo.parse_git_url(result.stdout.strip())
            if parsed:
                return parsed[1]
        except (subprocess.CalledProcessError, OSError):
            pass
        return None

    # ------------------------------------------------------------------
    # 密钥↔作者自动联动
    # ------------------------------------------------------------------

    def apply_auto_author(
        self,
        label: str,
        repo_path: str | None = None,
        scope: str = "local",
        skip_confirm: bool = True,
    ) -> None:
        """密钥↔作者自动联动：切换密钥时，若该 label 绑定了 author，则自动设置。

        - scope='local'：设置仓库级 author（use_key_for_repo 调用）
        - scope='global'：设置全局 author（use -g / use --global 调用 switch_key）
        - 仅当 auto_author 开关开启且 label 有显式 author 绑定时才生效；
          无绑定则静默跳过，避免噪音。
        - infer_from_remote 关闭，避免把别名 URL 中的组织名错设成作者名。
        """
        if not self.state_manager.read_auto_author():
            return
        author = self.get_author_info(label, repo_path=None, infer_from_remote=False)
        if not author or not (author.get("name") or author.get("email")):
            return  # 无 author 绑定，不联动

        repo = Path(repo_path).resolve() if repo_path else Path.cwd()
        try:
            if author.get("name"):
                git(repo, "config", f"--{scope}", "user.name", author["name"])
            if author.get("email"):
                git(repo, "config", f"--{scope}", "user.email", author["email"])
        except (subprocess.CalledProcessError, OSError) as e:
            self._fail(ErrCode.AUTO_AUTHOR_FAILED, err=e, icon=ICON_WARN)
            return

        print(f"{_(K.msg.auto_set_author, label=label)}: {author.get('name', '') or ''} <{author.get('email', '') or ''}>")
