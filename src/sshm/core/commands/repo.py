#!/usr/bin/env python3
"""
Git 仓库命令组 - 仓库相关命令的编排（use / clone / info / test）。

负责把用户意图翻译为对 GitRepoService / SSHTester / AuthorService 等服务的
编排调用 + 渲染输出。共享状态与错误上报通过门面 SSHKeyManager（self.m）。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from ...i18n import _
from ...language import K
from ...ui.output import (
    ICON_ERR,
    ICON_OK,
    ICON_WARN,
    print,
)
from ...ui.output import (
    confirm as prompt_confirm,
)
from ...ui.output import (
    section as print_section_header,
)
from ...ui.output import (
    separator as print_separator,
)
from ...ui.output import (
    table as print_table,
)
from ...ui.tip import render_tip_block
from ..services.ssh.keypaths import private_key_path, public_key_path

if TYPE_CHECKING:
    from ..manager import SSHKeyManager


class RepoCommands:
    """Git 仓库命令编排。"""

    def __init__(self, m: SSHKeyManager):
        self.m = m

    def use(self, label: str, repo_path: str | Path = ".", skip_confirm: bool = False):
        """为指定 Git 仓库配置使用特定密钥"""
        repo_path = Path(repo_path).resolve()

        if not (repo_path / ".git").exists():
            self.m._fail("NOT_GIT_REPO", path=repo_path)
            return

        key_type = self.m.keystore.detect_key_type_for_label(label)
        if not key_type:
            msg = _(K.err.key_not_found_short, label=label)
            self.m._fail(msg, hint=_(K.msg.use_all_keys_tip))
            return

        print_section_header(_(K.hdr.configure, label=label))
        print(f"{_(K.lbl.repo_path)} {repo_path}\n")

        key_file = private_key_path(self.m.ssh_dir, key_type, label)

        try:
            result = subprocess.run(
                ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                check=True,
            )
            current_url = result.stdout.strip()
            print(f"{_(K.lbl.current_remote_url)}\n   {current_url}\n")

            parsed = self.m.gitrepo.parse_git_url(current_url)
            if not parsed:
                self.m._fail("FAILED_PARSE")
                return

            platform, user, repo = parsed
            print(f"{_(K.lbl.parsed_info)}")
            print(f"   {_(K.lbl.platform)} {platform}")
            print(f"   {_(K.lbl.user_org)} {user}")
            print(f"   {_(K.lbl.repo)} {repo}\n")

            # 私有化/非标准 Git：校验并自动对齐 hostname 映射
            repo_hostname = self.m.gitrepo.resolve_repo_hostname(current_url)
            if not self.m.gitrepo.align_hostname_with_repo(label, repo_hostname, skip_confirm):
                return

            # 确保 SSH config 别名存在且唯一（此时 hostname 已对齐，别名正确）
            host_alias = self.m.gitrepo.get_host_alias(label)
            self.m.gitrepo.update_ssh_config_alias(label, key_file)
            new_url = f"git@{host_alias}:{user}/{repo}.git"

            print(f"{_(K.lbl.new_remote_url)}")
            print(f"   {new_url}\n")

            if not skip_confirm:
                if not prompt_confirm(_(K.msg.update_url_prompt)):
                    self.m._fail(_(K.misc.operation_cancelled))
                    return

            # 先测试 SSH 连接，再更新 URL，避免留下无法认证的坏配置
            print("🧪 " + _(K.msg.testing_ssh))
            test_ok, test_msg = self.m.tester.test(host_alias)
            if test_ok:
                print("✅ " + _(K.msg.ssh_test_passed))
                if "Hi" in test_msg or "Welcome" in test_msg:
                    print(f"   {test_msg}")
            else:
                print("⚠️  " + _(K.msg.ssh_test_failed))
                print(f"   {test_msg}")
                print("   " + _(K.msg.not_added_yet))
                if not skip_confirm:
                    if not prompt_confirm(_(K.msg.update_url_anyway)):
                        self.m._fail(_(K.misc.operation_cancelled))
                        return

            subprocess.run(
                ["git", "-C", str(repo_path), "remote", "set-url", "origin", new_url],
                check=True,
            )
            print("✅ " + _(K.msg.remote_url_updated) + "\n")

            print()
            print_separator()
            print("✅ " + _(K.hdr.config_complete))
            print(f"   cd {repo_path}")
            print("   git push")
            print_separator()

            # 密钥↔作者自动联动：局部切换时自动设置仓库 author（若 label 有绑定）
            self.m.author_service.apply_auto_author(label, repo_path=str(repo_path), scope="local")

        except subprocess.CalledProcessError as e:
            if "No such remote" in str(e.stderr):
                self.m._fail("NO_ORIGIN_REMOTE")
            else:
                self.m._fail("GIT_FAILED", err=e)
        except subprocess.TimeoutExpired:
            self.m._fail("SSH_TEST_TIMEOUT")
        except Exception as e:
            self.m._fail("GIT_FAILED", err=e)

    def clone(
        self,
        label: str,
        url: str,
        target_dir: str | None = None,
        skip_confirm: bool = False,
    ):
        """使用指定密钥标签克隆 Git 仓库，并在克隆后为该仓库配置该密钥"""
        # 校验标签存在密钥
        key_type = self.m.keystore.detect_key_type_for_label(label)
        if not key_type:
            self.m._fail("KEY_NOT_FOUND_SHORT", label=label)
            return

        # 解析 URL
        parsed = self.m.gitrepo.parse_git_url(url)
        if not parsed:
            self.m._fail("FAILED_PARSE")
            return
        _platform, user, repo = parsed
        repo_name = repo.rstrip(".git") or repo

        print_section_header(_(K.hdr.clone, label=label))
        print(f"{_(K.lbl.key_type)}: {label} ({key_type})")
        print(f"{_(K.lbl.source_url)} {url}\n")

        # 对齐 hostname（适配私有化 Git），并确保 SSH config 别名存在
        repo_hostname = self.m.gitrepo.resolve_repo_hostname(url)
        if not self.m.gitrepo.align_hostname_with_repo(label, repo_hostname, skip_confirm):
            return

        key_file = private_key_path(self.m.ssh_dir, key_type, label)
        self.m.gitrepo.update_ssh_config_alias(label, key_file)

        # 重写为别名 URL：git@{alias}:user/repo.git
        host_alias = self.m.gitrepo.get_host_alias(label)
        new_url = f"git@{host_alias}:{user}/{repo_name}.git"

        print(f"{_(K.lbl.clone_url)}")
        print(f"   {new_url}\n")

        if not skip_confirm:
            if not prompt_confirm(_(K.msg.clone_confirm)):
                self.m._fail(_(K.misc.operation_cancelled))
                return

        # 执行 git clone（支持可选的目录名）
        clone_args = ["git", "clone", new_url]
        if target_dir:
            clone_args.append(target_dir)
        try:
            subprocess.run(clone_args, check=True)
        except subprocess.CalledProcessError as e:
            detail = (e.stderr or b"").decode("utf-8", "replace").strip() or str(e)
            self.m._fail("CLONE_FAILED", err=detail)
            return

        # 克隆完成后定位仓库目录（用于后续 author 设置）
        cloned_dir = target_dir or repo_name
        print(f"\n✅ {_(K.msg.clone_complete)} {cloned_dir}")
        print("   " + _(K.msg.repo_uses_key, label=label))

        # 设置作者（若标签有显式作者信息）。
        # 注意：这里禁用 remote 推断，因为 clone 的 remote 是 sshm 别名 URL，
        # 其 user 段是组织名而非作者名，推断会把 org 名错设成 user.name。
        author = self.m.author_service.get_author_info(label, repo_path=cloned_dir, infer_from_remote=False)
        if author and (author.get("name") or author.get("email")):
            print()
            self.m.author.use(label, cloned_dir, skip_confirm=True, infer_from_remote=False)

        print()
        print_separator()
        print("✅ " + _(K.hdr.config_complete))
        print(f"   cd {cloned_dir}")
        print("   git push")
        print_separator()

    def info(self, repo_path: str | Path = "."):
        """显示当前 Git 仓库的 SSH 配置信息"""
        print_section_header(_(K.hdr.repo_info))

        repo_path = Path(repo_path).resolve()

        if not (repo_path / ".git").exists():
            self.m._fail("NOT_VALID_GIT", path=repo_path)
            return

        print(f"{_(K.lbl.repo_path)} {repo_path}")

        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            remote_url = result.stdout.strip()
            print(f"{_(K.lbl.remote_url)} {remote_url}")

            parsed = self.m.gitrepo.parse_git_url(remote_url)
            if parsed:
                platform, user, repo = parsed
                print(f"\n{_(K.lbl.parsed_info)}")
                print(f"  ├─ {_(K.lbl.platform)} {platform}")
                print(f"  ├─ {_(K.lbl.user_org)} {user}")
                print(f"  └─ {_(K.lbl.repo)} {repo}")

                ssh_pattern = r"git@([^:]+):"
                match = re.match(ssh_pattern, remote_url)
                if match:
                    host_alias = match.group(1)
                    # 反解别名对应的标签（容忍主机名首段含连字符，如 git-codecommit-{label}）
                    label = self.m.gitrepo.resolve_label_from_alias(host_alias)
                    if label:
                        print(f"\n{_(K.lbl.current_alias, alias=host_alias)}")

                        key_type = self.m.keystore.detect_key_type_for_label(label)
                        if key_type:
                            key_file = private_key_path(self.m.ssh_dir, key_type, label)
                            pub_file = public_key_path(self.m.ssh_dir, key_type, label)

                            print(f"\n{_(K.lbl.key_info)}")
                            print(f"  ├─ {_(K.lbl.label)}: {label}")
                            print(f"  ├─ {_(K.lbl.key_type)}: {key_type}")
                            print(f"  ├─ {_(K.lbl.private_key)} {key_file}")
                            print(f"  └─ {_(K.lbl.public_key)} {pub_file}")

                            ssh_config = self.m.config_manager.config_file
                            if ssh_config.exists():
                                # 按 Host 块解析，打印匹配该别名的完整配置块
                                block = self.m.gitrepo.extract_ssh_config_block(host_alias)
                                if block:
                                    print(f"\n{_(K.lbl.ssh_config)}")
                                    for line in block:
                                        print(f"  {line}")
                        else:
                            msg = _(K.err.key_not_found_file, label=label)
                            print(f"\n⚠️  {msg}")
                    else:
                        render_tip_block(
                            [
                                f"💡 {_(K.msg.current_alias_unconfigured)}",
                                "   " + _(K.msg.use_to_configure),
                            ]
                        )
                else:
                    render_tip_block(
                        [
                            f"💡 {_(K.msg.https_url_tip)}",
                            "   " + _(K.msg.use_to_ssh),
                        ]
                    )
            else:
                print("\n⚠️  " + _(K.msg.failed_parse_url))

        except subprocess.CalledProcessError as e:
            if "No such remote" in str(e.stderr):
                print("\n⚠️  " + _(K.msg.no_origin_configured))
            else:
                self.m._fail("GIT_FAILED", err=e)
        except Exception as e:
            self.m._fail("GIT_FAILED", err=e)

    def test(
        self,
        label: str | None = None,
        test_all: bool = False,
        repo_path: str | Path = ".",
    ):
        """测试 SSH 连接"""
        if test_all:
            print_section_header(_(K.hdr.test_all))

            keys_by_label = self.m.keystore.scan_all_keys()
            if not keys_by_label:
                self.m._fail("NO_KEYS", hint=_(K.msg.use_all_keys_tip))
                return

            results = []
            no_alias_msg = _(K.msg.no_alias_configured)

            # 分两类：未配置别名的直接判定（无需联网），需联网的并行测试
            outcome = {}
            network_tasks = []
            for label, key_infos in keys_by_label.items():
                host_alias = self.m.gitrepo.get_host_alias(label)
                key_types = ", ".join([k["type"] for k in key_infos])

                # 未配置 config 别名的标签无法路由，跳过并给出明确提示
                if not self.m.config_manager.has_host(host_alias):
                    outcome[label] = (False, no_alias_msg)
                else:
                    network_tasks.append((label, host_alias, key_types))

            # 并行执行联网测试，缩短多密钥场景总耗时
            if network_tasks:
                from concurrent.futures import ThreadPoolExecutor

                workers = min(8, len(network_tasks))
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    future_map = {label: pool.submit(self.m.tester.test, alias) for label, alias, _ in network_tasks}
                    for label, _alias, _kt in network_tasks:
                        outcome[label] = future_map[label].result()

            # 按原始顺序汇总结果，保证输出顺序稳定
            for label, key_infos in keys_by_label.items():
                host_alias = self.m.gitrepo.get_host_alias(label)
                key_types = ", ".join([k["type"] for k in key_infos])
                results.append((label, host_alias, key_types, outcome[label]))

            print()
            print_separator()
            print(_(K.hdr.test_results))
            print_separator()
            # 用 rich Table 渲染对齐（替代手写 pad_cell），message 作为独立提示
            table_rows = []
            for label, host_alias, key_types, (success, message) in results:
                status = ICON_OK if success else ICON_ERR
                table_rows.append([status, label, host_alias, key_types])
            print_table(
                [_(K.lbl.status), _(K.lbl.label), _(K.lbl.alias), _(K.lbl.key_type)],
                table_rows,
                center_cols=[0],
            )
            # 失败项的详细错误信息作为提示展示
            for label, host_alias, key_types, (success, message) in results:
                if not success:
                    print(f"   ❌ {label}: {message}")

            # 只要有任一连接失败，标记业务失败（供 CLI 层返回非零退出码）
            if any(not ok for _, _, _, (ok, _) in results):
                self.m._mark_error()

        elif label:
            print_section_header(_(K.hdr.test_one, label=label))

            key_type = self.m.keystore.detect_key_type_for_label(label)
            if not key_type:
                msg = _(K.err.key_not_found_files, label=label)
                self.m._fail(msg)
                print("\n💡 " + _(K.msg.use_all_keys_tip))
                return

            host_alias = self.m.gitrepo.get_host_alias(label)

            print(f"{_(K.lbl.key_type)}: {label}")
            print(f"{_(K.lbl.host)} {host_alias}")

            # 未配置 config 别名时无法路由到真实主机，直接给出友好提示
            if not self.m.config_manager.has_host(host_alias):
                print(f"\n⚠️  {_(K.msg.alias_not_configured, alias=host_alias)}")
                print("   " + _(K.msg.run_use_first, label=label))
                print("   " + _(K.msg.run_use_global, label=label))
                self.m._mark_error()
                return

            print("\n🧪 " + _(K.msg.testing))

            success, message = self.m.tester.test(host_alias)
            if success:
                print(f"✅ {message}")
            else:
                self.m._fail(message)
        else:
            print_section_header(_(K.hdr.test_current))

            repo_path = Path(repo_path).resolve()

            if not (repo_path / ".git").exists():
                self.m._fail("NOT_VALID_GIT", path=repo_path)
                return

            print(f"{_(K.lbl.repo_path)} {repo_path}")

            try:
                result = subprocess.run(
                    ["git", "remote", "get-url", "origin"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                remote_url = result.stdout.strip()
                print(f"{_(K.lbl.remote_url)} {remote_url}")

                ssh_pattern = r"git@([^:]+):"
                match = re.match(ssh_pattern, remote_url)
                if match:
                    host_alias = match.group(1)
                    print(f"\n🧪 {_(K.msg.testing_host, host=host_alias)}")

                    success, message = self.m.tester.test(host_alias)
                    if success:
                        print(f"✅ {message}")
                    else:
                        self.m._fail(message)
                        print("\n💡 " + _(K.msg.check_config_tip))
                        print("   " + _(K.msg.use_info))
                else:
                    print("\n⚠️  " + _(K.msg.not_ssh_url))
                    print("   " + _(K.msg.use_to_convert))

            except subprocess.CalledProcessError as e:
                if "No such remote" in str(e.stderr):
                    print("\n⚠️  " + _(K.msg.no_origin_configured))
                else:
                    self.m._fail("GIT_FAILED", err=e)
            except Exception as e:
                self.m._fail("GIT_FAILED", err=e)
