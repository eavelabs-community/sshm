#!/usr/bin/env python3
"""
系统工具模块 - PATH 配置等系统级操作
"""

import os
import sys
from pathlib import Path

from ....i18n import _
from ....language import K
from ....ui.console import print_section_header, prompt_confirm
from ....ui.output import print
from ....ui.tip import render_business_error


def add_to_path() -> None:
    """将当前可执行文件路径添加到环境变量"""
    print_section_header(_(K.hdr.add_to_path))

    # 获取当前可执行文件路径
    if getattr(sys, "frozen", False):
        # PyInstaller 打包后的可执行文件
        exe_path = Path(sys.executable).resolve()
        exe_dir = exe_path.parent
    else:
        # 开发环境中的 Python 脚本
        exe_path = Path(__file__).parent.parent.resolve()
        exe_dir = exe_path

    print(f"{_(K.sys.current_exe, path=exe_path)}")
    print(f"{_(K.sys.directory, dir=exe_dir)}")

    if sys.platform == "win32":
        _add_to_windows_path(exe_dir)
    else:
        _add_to_unix_path(exe_dir)


def _add_to_windows_path(exe_dir: Path) -> None:
    """Windows 环境变量配置"""
    import winreg

    try:
        # 读取当前用户的 PATH 环境变量
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Environment",
            0,
            winreg.KEY_READ | winreg.KEY_WRITE,
        )

        try:
            current_path, _value_type = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current_path = ""

        # 规范化路径
        exe_dir_str = str(exe_dir)
        path_entries = [p.strip() for p in current_path.split(";") if p.strip()]

        # 检查路径是否已存在
        existing_paths = [p for p in path_entries if Path(p).resolve() == exe_dir.resolve()]

        if existing_paths:
            print(_(K.sys.path_exists, path=existing_paths[0]))

            if existing_paths[0] != exe_dir_str:
                print(_(K.sys.current_path, path=exe_dir_str))
                print(_(K.sys.existing_path, path=existing_paths[0]))

                if prompt_confirm(_(K.sys.update_path_prompt), default="y"):
                    # 移除旧路径
                    path_entries = [p for p in path_entries if p not in existing_paths]
                    # 添加新路径到开头
                    path_entries.insert(0, exe_dir_str)
                    new_path = ";".join(path_entries)

                    winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
                    winreg.CloseKey(key)

                    # 广播环境变量更新
                    _broadcast_env_change()

                    print("\n✅ " + _(K.sys.env_updated))
                    print("\n💡 " + _(K.sys.restart_tip))
                    print("   " + _(K.sys.use_sshm_directly))
                else:
                    render_business_error(_(K.misc.operation_cancelled))
                    winreg.CloseKey(key)
            else:
                winreg.CloseKey(key)
        else:
            # 添加新路径到开头
            path_entries.insert(0, exe_dir_str)
            new_path = ";".join(path_entries)

            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
            winreg.CloseKey(key)

            # 广播环境变量更新
            _broadcast_env_change()

            print("\n✅ " + _(K.sys.env_added))
            print(f"   {exe_dir_str}")
            print("\n💡 " + _(K.sys.restart_tip))
            print("   " + _(K.sys.use_sshm_directly))

    except PermissionError:
        render_business_error(_(K.err.permission_denied))
    except Exception as e:
        render_business_error(_(K.err.add_failed, err=e))


def _add_to_unix_path(exe_dir: Path) -> None:
    """Unix/Linux/macOS 环境变量配置"""
    home = Path.home()
    exe_dir_str = str(exe_dir)

    # 检测 shell 类型
    shell = os.environ.get("SHELL", "/bin/bash")
    if "zsh" in shell:
        rc_file = home / ".zshrc"
    elif "fish" in shell:
        rc_file = home / ".config" / "fish" / "config.fish"
    else:
        rc_file = home / ".bashrc"

    export_line = f'export PATH="{exe_dir_str}:$PATH"'

    # 检查是否已添加
    if rc_file.exists():
        content = rc_file.read_text(encoding="utf-8")
        if exe_dir_str in content:
            print(_(K.sys.path_in, name=rc_file.name))
            return

    print(_(K.sys.will_add, path=rc_file))
    print(_(K.sys.command, cmd=export_line))

    if prompt_confirm("\n" + _("sys.continue"), default="y"):
        try:
            with rc_file.open("a", encoding="utf-8") as f:
                f.write("\n# Added by sshm\n")
                f.write(f"{export_line}\n")

            print("\n✅ " + _(K.sys.config_added))
            print("\n💡 " + _(K.sys.run_to_apply))
            print(f"   source {rc_file}")
            print("\n   " + _(K.sys.or_restart))
        except Exception as e:
            render_business_error(_(K.err.add_failed, err=e))
    else:
        render_business_error(_(K.misc.operation_cancelled))


def _broadcast_env_change() -> None:
    """广播 Windows 环境变量更新"""
    if sys.platform == "win32":
        try:
            import ctypes

            HWND_BROADCAST = 0xFFFF
            WM_SETTINGCHANGE = 0x001A
            SMTO_ABORTIFHUNG = 0x0002

            result = ctypes.c_long()
            SendMessageTimeout = ctypes.windll.user32.SendMessageTimeoutW
            SendMessageTimeout(
                HWND_BROADCAST,
                WM_SETTINGCHANGE,
                0,
                "Environment",
                SMTO_ABORTIFHUNG,
                5000,
                ctypes.byref(result),
            )
        except Exception:
            pass
