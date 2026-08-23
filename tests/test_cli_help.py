"""CLI 帮助测试：验证所有命令/子命令的 --help 正常生成"""

import pytest
from conftest import strip_ansi


@pytest.mark.parametrize(
    "args",
    [
        ["key"],
        ["repo"],
        ["backup"],
        ["author"],
        ["history"],
        ["config"],
    ],
)
def test_help_command(args, cli_runner):
    """每个一级分组命令的 --help 都能正常生成"""
    runner, app = cli_runner
    result = runner.invoke(app, args + ["--help"])
    assert result.exit_code == 0, f"{args} help failed: {result.exception}"
    assert "Usage" in result.output


@pytest.mark.parametrize(
    "args",
    [
        ["key", "list"],
        ["key", "create"],
        ["key", "remove"],
        ["key", "rename"],
        ["key", "label"],
        ["key", "switch"],
        ["key", "current"],
        ["repo", "use"],
        ["repo", "clone"],
        ["repo", "info"],
        ["repo", "test"],
        ["backup", "create"],
        ["backup", "list"],
        ["backup", "restore"],
        ["author", "list"],
        ["author", "add"],
        ["author", "update"],
        ["author", "remove"],
        ["author", "use"],
        ["author", "unset"],
        ["history", "rewrite"],
        ["config", "language"],
        ["config", "auto-author"],
        ["version", "update"],
        ["version", "reinstall"],
    ],
)
def test_subcommands_help(args, cli_runner):
    """各分组子命令的 --help 正常"""
    runner, app = cli_runner
    result = runner.invoke(app, args + ["--help"])
    assert result.exit_code == 0, f"{args} help failed: {result.exception}"
    assert "Usage" in result.output


def test_main_help_lists_all_commands(cli_runner):
    """主 --help 包含所有分组命令"""
    runner, app = cli_runner
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ["key", "repo", "backup", "author", "history", "config"]:
        assert cmd in result.output, f"{cmd} missing from help"


def test_version_flag(cli_runner):
    """-v / --version 输出版本"""
    from sshm.constants import VERSION

    runner, app = cli_runner
    r1 = runner.invoke(app, ["-v"])
    assert r1.exit_code == 0
    assert VERSION in strip_ansi(r1.output)
    r2 = runner.invoke(app, ["--version"])
    assert r2.exit_code == 0
    assert VERSION in strip_ansi(r2.output)


def test_version_src_mode_has_no_build_line(cli_runner):
    """源码运行（非打包）时 -v 不显示 Build（构建来源）行"""
    from sshm.cli.app import app

    runner, _ = cli_runner
    # 强制源码模式：sys.frozen 不存在
    result = runner.invoke(app, ["-v"])
    assert result.exit_code == 0
    assert "Build" not in result.output
    assert "Platform" in result.output


def test_version_help_shorthand(cli_runner):
    """-h 可作为 --help 的简写"""
    runner, app = cli_runner
    r1 = runner.invoke(app, ["-h"])
    assert r1.exit_code == 0
    assert "Usage" in r1.output
    r2 = runner.invoke(app, ["author", "-h"])
    assert r2.exit_code == 0
    assert "Usage" in r2.output


def test_build_source_detection(monkeypatch, tmp_path):
    """构建来源判断：根据 exe 旁的标记文件区分本地/线上/未知"""
    import importlib

    cli_mod = importlib.import_module("sshm.cli.app")

    def _run(flag: str):
        # 模拟 PyInstaller 打包：sys.executable 指向临时目录里的 exe
        # （_build_source 只读 sys.executable 旁的标记文件，不依赖 sys.frozen）
        fake_exe = tmp_path / "sshm.exe"
        fake_exe.write_bytes(b"")
        monkeypatch.setattr(cli_mod.sys, "executable", str(fake_exe))
        # 先清理上次留下的标记，保证每次独立
        for m in (".source_local", ".source_release"):
            (tmp_path / m).unlink(missing_ok=True)
        if flag == "local":
            (tmp_path / ".source_local").write_text("", encoding="utf-8")
        elif flag == "release":
            (tmp_path / ".source_release").write_text("", encoding="utf-8")
        return cli_mod._build_source()

    # 本地编译
    assert "local" in _run("local")
    # 线上发布
    assert "release" in _run("release")
    # 无标记 -> 未知
    assert "unknown" in _run("none")
