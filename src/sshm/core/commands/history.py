#!/usr/bin/env python3
"""
历史重写命令组 - 重写 Git 历史作者/邮箱的编排。

负责把用户意图翻译为对 rewrite 模块的编排调用 + 渲染输出。
共享状态与错误上报通过门面 SSHKeyManager（self.m）。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..utils.parse import split_pair
from ..utils.process import git
from typing import TYPE_CHECKING

from ...i18n import _
from ...language import K
from ...ui.output import (
    ICON_WARN,
)
from ...ui.output import (
    confirm as prompt_confirm,
)
from ...ui.output import (
    print as rich_print,
)
from ..errors import ErrCode
from ...ui.output import (
    section as print_section_header,
)
from ...ui.output import (
    status as output_status,
)

if TYPE_CHECKING:
    from ..manager import SSHKeyManager


class HistoryCommands:
    """历史重写命令组（对应 CLI `sshm history rewrite`）。"""

    def __init__(self, m: SSHKeyManager):
        self.m = m

    @staticmethod
    def _split_pair(value: str | None):
        """解析 'OLD:NEW' 或 'NEW' 形式的参数（委托 core.utils.parse.split_pair）。"""
        return split_pair(value)

    def rewrite(
        self,
        repo_path: str | Path = ".",
        name: str | None = None,
        email: str | None = None,
        author: str | None = None,
        skip_confirm: bool = False,
    ):
        """重写 Git 历史中的作者/邮箱。

        三种互斥模式：
        1. --author <label>  全量刷新：把历史所有作者/邮箱统一为该 label
        2. --name NEW / --email NEW   全量刷新该字段：所有 name/email 统一为新值
        3. --name OLD:NEW / --email OLD:NEW   精细替换：OLD -> NEW
        """
        from ..services.git.rewrite import (
            RewriteConfig,
            get_authors_in_repo,
            rewrite_history,
        )

        repo_path = Path(repo_path).resolve()
        if not (repo_path / ".git").exists():
            self.m._fail(ErrCode.NOT_GIT_REPO, path=repo_path)
            return

        old_name, new_name = split_pair(name)
        old_email, new_email = split_pair(email)

        # 模式判定
        precise = bool(old_name or old_email)  # 精细替换（OLD:NEW）
        full_name = bool(new_name and not old_name)  # --name 单值全量
        full_email = bool(new_email and not old_email)  # --email 单值全量
        full_author = bool(author)  # --author <label> 全量

        # 互斥校验：精细替换不能与任何全量刷新混用
        if precise and (full_author or full_name or full_email):
            self.m._fail(ErrCode.AUTHOR_EXCLUSIVE, hint=_(K.err.rewrite_usage_tip))
            return
        # --author 不能与 --name/--email 单值全量混用
        if full_author and (full_name or full_email):
            self.m._fail(ErrCode.AUTHOR_EXCLUSIVE, hint=_(K.err.rewrite_usage_tip))
            return

        if author:
            # 从作者列表读取 label 对应的 name/email
            stored = self.m.state_manager.read_authors().get(author.lower())
            if not stored:
                self.m._fail(
                    _(K.err.author_not_found, label=author),
                    hint=_(K.err.use_author_list),
                )
                return
            match_all = True
            new_name = stored.get("name") or None
            new_email = stored.get("email") or None
            if not new_name and not new_email:
                self.m._fail(ErrCode.AUTHOR_EMPTY, label=author)
                return
        elif full_name or full_email:
            # 单值全量刷新：match_all 模式，只刷新提供的字段
            match_all = True
        else:
            match_all = False
            if not old_name and not old_email:
                self.m._fail(ErrCode.NEED_OLD, hint=_(K.err.rewrite_usage_tip))
                return
            if not new_name and not new_email:
                self.m._fail(ErrCode.NEED_NEW)
                return

        print_section_header(_(K.hdr.rewrite))
        rich_print(f"\n{_(K.lbl.repo_path)} {repo_path}")

        # 预览：列出历史中的作者
        authors = get_authors_in_repo(repo_path)
        rich_print(f"\n{_(K.lbl.current_authors)}")
        for a in authors:
            rich_print(f"   - {a}")

        # 构造规则并预估受影响提交
        cfg = RewriteConfig(
            old_name=old_name,
            new_name=new_name,
            old_email=old_email,
            new_email=new_email,
            match_all=match_all,
        )
        if match_all:
            # 只展示实际被刷新的字段（--author 全量刷两者；单值只刷其一）
            parts = []
            if new_name:
                parts.append(f"{_(K.misc.name)} -> '{new_name}'")
            if new_email:
                parts.append(f"{_(K.misc.email)} -> '{new_email}'")
            match_desc = [f"{_(K.misc.all)} [{' | '.join(parts)}]"]
        else:
            match_desc = []
            if old_name:
                match_desc.append(f"{_(K.misc.name)} '{old_name}' -> '{new_name or old_name}'")
            if old_email:
                match_desc.append(f"{_(K.misc.email)} '{old_email}' -> '{new_email or old_email}'")
        rich_print(f"\n🛠 {_(K.lbl.rules)} {', '.join(match_desc)}")

        # 用 dry-run 预估（fast-export 到临时流，不导入）。
        # 显式传活跃 refs（排除 refs/original/ 备份），避免 matched 计数
        # 反复命中已重写过的旧历史。
        try:
            from ..services.git.rewrite import _active_refs, _count_matches

            active = _active_refs(repo_path)
            # 用原始字节导出（仓库历史可能含二进制 blob，文本模式 errors="replace"
            # 会改坏 data 块字节数；这里只用于统计，同样必须按字节）。
            export = git(repo_path, "fast-export", *active)
            matched = _count_matches(export.stdout, cfg)
        except Exception:
            matched = 0
        if matched == 0:
            self.m._fail(ErrCode.NO_MATCHES, icon=ICON_WARN)
            return
        rich_print(f"📝  {_(K.msg.will_rewrite_count, count=matched)}")

        # 破坏性操作确认
        rich_print(f"\n⚠️  {_(K.msg.rewrites_history)}")
        rich_print("   " + _(K.msg.force_push))
        if not skip_confirm:
            if not prompt_confirm(_(K.msg.continue_rewrite), default="y"):
                self.m._fail(_(K.misc.operation_cancelled))
                return

        try:
            with output_status(_(K.msg.rewriting)):
                result = rewrite_history(repo_path, cfg)
        except Exception as e:
            self.m._fail(ErrCode.REWRITE_FAILED, err=e)
            return

        rich_print(f"\n✅ {_(K.msg.history_rewritten)}")
        rich_print(f"   {_(K.msg.matched_commits, count=result.get('matched_commits', 0))}")
        rich_print(f"   {_(K.msg.rewritten_lines, count=result.get('rewritten', 0))}")
        rich_print(f"\n⚠️  {_(K.msg.refs_backed_up)}")
        rich_print(f"   {_(K.msg.force_push_all)}")
