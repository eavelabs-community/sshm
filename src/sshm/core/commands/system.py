#!/usr/bin/env python3
"""
系统命令组 - 系统级命令的编排（update / reinstall / add_path）。

只负责把用户意图翻译为对 UpdateManager / path 的编排调用 + 渲染。
系统配置（语言 / 自动作者）见 config.py 的 ConfigCommands。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...i18n import _
from ...language import K
from ...ui.console import prompt_confirm
from ...ui.icons import done as _done
from ...ui.icons import ok as _ok
from ...ui.icons import tip as _tip
from ...ui.output import print as rich_print
from ...ui.output import separator as print_separator

if TYPE_CHECKING:
    from ..manager import SSHKeyManager
    from ..services.net.updater import UpdateManager


class SystemCommands:
    """系统命令编排（更新 / 重新安装 / PATH）。"""

    def __init__(self, m: SSHKeyManager):
        self.m = m

    def update(
        self,
        check: bool = False,
        force: bool = False,
        yes: bool = False,
    ) -> int | None:
        """检查并更新到最新版本。

        Args:
            check: 仅检查不更新
            force: 忽略缓存强制检查
            yes: 跳过确认直接更新

        Returns:
            退出码（0 成功 / 1 失败）；无需退出（已最新 / 仅检查 / 取消）返回 None
        """
        from ..services.net.updater import UpdateCheckError, UpdateManager

        updater = UpdateManager()
        print_separator()
        rich_print(_(K.hdr.update))
        print_separator()
        rich_print(f"\n{_(K.lbl.current_version)} v{updater.current_version}")
        rich_print(f"{_(K.lbl.platform)} {updater.platform}")

        rich_print("\n" + _(K.upd.checking))
        try:
            update_info = updater.check_update(force=force)
        except UpdateCheckError as e:
            self.m._fail(_(K.upd.check_failed, detail=str(e)))
            return 1

        if not update_info:
            rich_print(_ok(K.upd.up_to_date))
            return None

        return self._apply_update(updater, update_info, check=check, yes=yes)

    def reinstall(
        self,
        target_version: str | None = None,
        force: bool = False,
        yes: bool = False,
    ) -> int | None:
        """重新安装（覆盖当前可执行文件）。

        - 不指定 target_version：默认升级到最新版本（与 update 等价）。
        - 指定 target_version：下载该 tag 资产覆盖（用于修复损坏 / 回滚到指定版本）。

        Returns:
            退出码（0 成功 / 1 失败）；无匹配资产 / 取消时返回 None
        """
        from ..services.net.updater import UpdateCheckError, UpdateManager

        updater = UpdateManager()
        print_separator()
        rich_print(_(K.hdr.update))
        print_separator()
        rich_print(f"\n{_(K.lbl.current_version)} v{updater.current_version}")
        rich_print(f"{_(K.lbl.platform)} {updater.platform}")

        try:
            if target_version:
                rich_print("\n" + _(K.upd.reinstall_checking, version=target_version))
                update_info = updater.get_release_by_tag(target_version)
                if not update_info:
                    self.m._fail(_(K.upd.reinstall_not_found, version=target_version))
                    return None
                # 指定版本即目标，无需再比较新旧
                return self._apply_update(updater, update_info, check=False, yes=yes, reinstall=True)
            else:
                # 不指定版本：重装当前版本（强制覆盖），不判断新旧
                rich_print("\n" + _(K.upd.reinstall_checking, version=f"v{updater.current_version}"))
                update_info = updater.get_release_by_tag(f"v{updater.current_version}")
                if not update_info:
                    self.m._fail(_(K.upd.reinstall_not_found, version=f"v{updater.current_version}"))
                    return None
                return self._apply_update(updater, update_info, check=False, yes=yes, reinstall=True)
        except UpdateCheckError as e:
            self.m._fail(_(K.upd.check_failed, detail=str(e)))
            return 1

    def _apply_update(
        self,
        updater: "UpdateManager",
        update_info: dict,
        *,
        check: bool = False,
        yes: bool = False,
        reinstall: bool = False,
    ) -> int | None:
        """展示更新信息并（在获得确认后）执行下载替换。

        update / reinstall 共用：负责信息展示、确认逻辑、下载调用。
        """
        rich_print(f"\n{_done(K.upd.new_version, version=update_info['version'])}")
        rich_print(f"{_(K.upd.release_date)} {update_info.get('published_at') or _(K.msg.unknown)}")

        if update_info.get("body"):
            rich_print(f"\n{_(K.upd.update_notes)}")
            for line in update_info["body"].split("\n")[:10]:
                rich_print(f"  {line}")
            if len(update_info["body"].split("\n")) > 10:
                rich_print("  ...")

        if check:
            rich_print(f"\n{_tip(K.upd.run_update)}")
            return None

        if not yes:
            rich_print()
            if not prompt_confirm(_(K.upd.prompt, version=update_info["version"]), default="y"):
                self.m._fail(_(K.upd.cancelled))
                return None

        rich_print()
        success = updater.download_and_update(update_info["download_url"])
        return 0 if success else 1

    def add_to_path(self) -> int:
        """把当前可执行文件目录添加到系统 PATH。

        失败或用户取消时标记软错误，保证退出码非 0。
        """
        from ..services.ssh.path import add_to_path

        ok = add_to_path()
        if not ok:
            self.m._mark_error()
            return 1
        return 0
