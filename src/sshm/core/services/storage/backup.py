#!/usr/bin/env python3
"""
备份服务 - 密钥备份 / 恢复 / 列表。

只负责备份目录相关操作，错误通过注入的 error_reporter（门面的 _fail）上报，
确认/输出走 Output 抽象（confirm / section / print）。
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from ....constants import SSH_CONFIG_NAME, STATE_FILE_NAME
from ....i18n import _
from ....language import K
from ...utils.fileperms import secure_key_perms
from ....ui.console import format_timestamp
from ....ui.icons import ok as _ok
from ....ui.icons import tip as _tip
from ....ui.output import confirm, print, section


class BackupService:
    """备份服务：backup / restore / list。"""

    def __init__(
        self,
        ssh_dir: Path,
        backup_dir: Path,
        state_file: Path,
        config_file: Path,
        error_reporter: Callable[..., None],
    ):
        self.ssh_dir = ssh_dir
        self.backup_dir = backup_dir
        self.state_file = state_file
        self.config_file = config_file
        self._error = error_reporter

    def create(self, silent: bool = False) -> Path:
        """备份所有密钥"""
        # 毫秒级时间戳：避免同一秒内多次备份合并到同一目录
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        backup_path = self.backup_dir / f"backup_{timestamp}"
        backup_path.mkdir(mode=0o700, exist_ok=True)

        key_files = list(self.ssh_dir.glob("id_*"))
        backed_up: list[str] = []

        for key_file in key_files:
            if key_file.is_file():
                shutil.copy2(key_file, backup_path / key_file.name)
                backed_up.append(key_file.name)

        if self.state_file.exists():
            shutil.copy2(self.state_file, backup_path / STATE_FILE_NAME)
            backed_up.append(STATE_FILE_NAME)

        # 一并备份 SSH config（仅存档；恢复时不会自动覆盖当前 config）
        if self.config_file.exists():
            shutil.copy2(self.config_file, backup_path / SSH_CONFIG_NAME)
            backed_up.append(SSH_CONFIG_NAME)

        if not silent:
            print(f"{_ok(K.msg.backup_complete)} {backup_path}")
            print("📦 " + _(K.msg.files_backed_up, count=len(backed_up)))

        return backup_path

    def list(self) -> None:
        """列出所有备份"""
        section(_(K.hdr.backup_list))

        backups = sorted(
            self.backup_dir.glob("backup_*"),
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )

        if not backups:
            print("📭 " + _(K.msg.no_backups))
            return

        for i, backup in enumerate(backups, 1):
            mtime = datetime.fromtimestamp(backup.stat().st_mtime, tz=timezone.utc)
            files = list(backup.glob("id_*"))
            print(f"\n[{i}] {backup.name}")
            print(f"    {_(K.lbl.time)} {format_timestamp(mtime)}")
            print(f"    {_(K.lbl.files)} {len(files)}")
            print(f"    {_(K.lbl.path)} {backup}")

    def restore(
        self,
        backup_name: str | None = None,
        key_type: str | None = None,
        skip_confirm: bool = False,
    ) -> None:
        """从备份恢复密钥"""
        section(_(K.hdr.restore))

        if backup_name:
            # 校验备份名，防止路径穿越 / 绝对路径 / 家目录逃逸出备份目录
            candidate = Path(backup_name)
            if candidate.is_absolute() or ".." in candidate.parts or str(backup_name).startswith("~"):
                self._error("INVALID_BACKUP_NAME", name=backup_name)
                return
            backup_path = self.backup_dir / backup_name
            if not backup_path.exists():
                self._error("BACKUP_NOT_FOUND_PATH", path=backup_path)
                return
        else:
            backups = sorted(
                self.backup_dir.glob("backup_*"),
                key=lambda x: x.stat().st_mtime,
                reverse=True,
            )
            if not backups:
                print("📭 " + _(K.err.no_backups_restore))
                print("   " + _(K.err.use_backup_cmd))
                return
            backup_path = backups[0]
            print(f"📦 {_(K.msg.will_use_latest)} {backup_path.name}")

        files = sorted(p for p in backup_path.glob("id_*") if p.is_file())
        if key_type:
            files = [f for f in files if f.name.startswith(f"id_{key_type}")]

        if not files:
            self._error("NO_RECOVERABLE")
            return

        print("\n📂 " + _(K.msg.will_restore_count, count=len(files)))
        for f in files:
            print(f"   - {f.name}")

        if not skip_confirm and not confirm("\n" + _(K.msg.restore_prompt)):
            self._error("OPERATION_CANCELLED")
            return

        restored = []
        for f in files:
            try:
                target = self.ssh_dir / f.name
                shutil.copy2(f, target)
                # 恢复私钥时兜底 chmod 600（Unix），公钥 644
                secure_key_perms(target, private=not f.name.endswith(".pub"))
                restored.append(f.name)
            except OSError as e:
                self._error("RESTORE_FAILED_DETAIL", name=f.name, detail=e)
        # 恢复状态文件（包含 active_keys / authors / hosts 映射）
        state_backup = backup_path / STATE_FILE_NAME
        if state_backup.exists():
            shutil.copy2(state_backup, self.state_file)
            restored.append(STATE_FILE_NAME)

        if restored:
            print(f"\n✅ {_(K.msg.restored_count, count=len(restored))}")
            for name in restored:
                print(f"   - {name}")
            print(f"\n{_tip(K.msg.restore_tip)}")

        # 备份中的 config 仅供存档，不自动覆盖当前配置，提示手动重建别名
        config_backup = backup_path / SSH_CONFIG_NAME
        if config_backup.exists():
            print("\n📝  " + _(K.msg.backup_has_config))
            print("   " + _(K.msg.regenerate_alias))
