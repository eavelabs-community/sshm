"""BackupService 单元测试：备份 / 恢复 / 列表"""

import json
from pathlib import Path

import pytest


@pytest.fixture
def backup_env(tmp_path: Path):
    """构造 BackupService 所需目录结构"""
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir()
    backup_dir = ssh_dir / "key_backups"
    backup_dir.mkdir()
    state_file = ssh_dir / ".sshm_state"
    config_file = ssh_dir / "config"

    # 创建若干密钥文件
    (ssh_dir / "id_ed25519").write_bytes(b"priv-default")
    (ssh_dir / "id_ed25519.work").write_bytes(b"priv-work")
    (ssh_dir / "id_ed25519.work.pub").write_text("ssh-ed25519 AAAA pub@work.com")
    state_file.write_text(json.dumps({"lang": "en"}), encoding="utf-8")
    config_file.write_text("# ssh config\n", encoding="utf-8")

    return {
        "ssh_dir": ssh_dir,
        "backup_dir": backup_dir,
        "state_file": state_file,
        "config_file": config_file,
    }


@pytest.fixture
def service(backup_env):
    from sshm.core.services.storage.backup import BackupService

    errors = []

    def reporter(code, **params):
        # 适配错误码体系：error_reporter 需接收 (code, **params)
        errors.append((code, params))

    svc = BackupService(
        backup_env["ssh_dir"],
        backup_env["backup_dir"],
        backup_env["state_file"],
        backup_env["config_file"],
        error_reporter=reporter,
    )
    svc._errors = errors
    return svc


class TestBackupKeys:
    def test_backup_creates_dir_with_keys(self, service, backup_env):
        path = service.create(silent=True)
        assert path.is_dir()
        names = {f.name for f in path.glob("id_*")}
        assert "id_ed25519" in names
        assert "id_ed25519.work" in names

    def test_backup_includes_state_and_config(self, service, backup_env):
        path = service.create(silent=True)
        assert (path / ".sshm_state").exists()
        assert (path / "config").exists()

    def test_backup_dir_naming(self, service, backup_env):
        path = service.create(silent=True)
        assert path.name.startswith("backup_")


class TestListBackups:
    def test_empty_returns_no_backups(self, service, backup_env):
        # 无备份时不应崩溃
        service.list()

    def test_lists_created_backup(self, service, backup_env, capsys):
        service.create(silent=True)
        service.list()
        assert "backup_" in capsys.readouterr().out


class TestRestoreBackup:
    def test_restore_to_ssh_dir(self, service, backup_env, tmp_path):
        # 先备份，再从备份恢复到隔离目录
        backup_path = service.create(silent=True)

        # 破坏当前 ssh_dir 中的密钥，模拟恢复场景
        (backup_env["ssh_dir"] / "id_ed25519").unlink()
        assert not (backup_env["ssh_dir"] / "id_ed25519").exists()

        service.restore(backup_path.name, skip_confirm=True)
        assert (backup_env["ssh_dir"] / "id_ed25519").exists()
        assert (backup_env["ssh_dir"] / "id_ed25519").read_bytes() == b"priv-default"

    def test_restore_latest_when_no_name(self, service, backup_env):
        backup_path = service.create(silent=True)
        (backup_env["ssh_dir"] / "id_ed25519.work").unlink()
        service.restore(skip_confirm=True)
        assert (backup_env["ssh_dir"] / "id_ed25519.work").exists()

    def test_restore_restores_state(self, service, backup_env):
        backup_path = service.create(silent=True)
        # 修改状态文件后再恢复
        backup_env["state_file"].write_text(json.dumps({"lang": "zh"}), encoding="utf-8")
        service.restore(backup_path.name, skip_confirm=True)
        data = json.loads(backup_env["state_file"].read_text(encoding="utf-8"))
        assert data["lang"] == "en"  # 恢复回备份时状态

    def test_invalid_backup_name_rejected(self, service, backup_env):
        # 路径穿越 / 绝对路径应被拒绝
        service.restore("../etc/passwd", skip_confirm=True)
        assert service._errors, "应上报路径穿越错误"
        service.restore("/etc/passwd", skip_confirm=True)
        assert len(service._errors) == 2

    def test_nonexistent_backup_rejected(self, service, backup_env):
        service.restore("backup_nonexistent", skip_confirm=True)
        assert service._errors

    def test_restore_key_type_filter(self, service, backup_env, tmp_path):
        backup_path = service.create(silent=True)
        (backup_env["ssh_dir"] / "id_ed25519").unlink()
        # 只恢复 ed25519 类型
        service.restore(backup_path.name, key_type="ed25519", skip_confirm=True)
        assert (backup_env["ssh_dir"] / "id_ed25519").exists()
