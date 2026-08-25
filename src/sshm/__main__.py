#!/usr/bin/env python3
"""
主程序入口 - 支持 python -m sshm 运行
"""

import sys
import threading

import click

# typer 0.27 起自研了 typer._click 子模块：用法错误（缺参数/非法枚举/未知选项）
# 抛出的是 typer._click.exceptions.*（不再继承公开 click.UsageError）。
# 为兼容新旧 typer，main() 统一同时捕获两种；旧版 typer 无 _click，回退为 click.UsageError。
try:
    from typer._click.exceptions import UsageError as _TyperUsageError
except ImportError:
    _TyperUsageError = click.UsageError  # type: ignore[assignment,misc]

from .constants import DEFAULT_SSH_DIR, STATE_FILE_NAME
from .core.errors import SSHMError
from .core.services.net.updater import UpdateManager
from .core.services.storage.state import StateManager
from .i18n import load_from_state


def _load_lang_before_parse() -> None:
    """在解析参数/显示帮助前应用语言（环境变量优先于状态文件）"""
    try:
        state = StateManager(DEFAULT_SSH_DIR / STATE_FILE_NAME)
        load_from_state(state.read_lang())
    except Exception:
        load_from_state(None)


def _silent_update_check() -> None:
    """非 update 命令时静默检查更新（不干扰用户）"""
    try:
        updater = UpdateManager()
        updater.check_and_notify()
    except Exception:
        # 静默失败，不影响正常使用
        pass


def _should_silent_check() -> bool:
    """判断是否需要静默更新检查（排除版本/帮助/更新命令自身）

    仅当首个非选项参数是实际业务命令时才检查；`sshm version update` /
    `sshm version reinstall` 自身会处理更新，以及 `-v` / `--help` 等
    无命令调用均跳过，避免把命令参数里的 "update" 字样误判
    （如 `sshm key add my-update-key`）。
    """
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args:
        return False  # 无子命令（如 -v / --help / 空）
    # 更新命令归 version 组：`sshm version update` / `sshm version reinstall`
    # 自身会检查或执行更新，跳过静默检查以免重复
    return not (len(args) >= 2 and args[0] == "version" and args[1] in ("update", "reinstall"))


def main() -> None:
    """主函数入口"""
    # 无论 CLI 还是其它路径，都先应用语言
    _load_lang_before_parse()

    # 双击/无参数运行：展示帮助作为入口引导（交互式菜单已移除）
    if len(sys.argv) == 1:
        from .cli.app import app

        app(["--help"])
        return

    # 实际执行业务命令时静默检查更新（后台线程，避免网络等待阻塞命令执行）
    if _should_silent_check():
        threading.Thread(target=_silent_update_check, daemon=True).start()

    # 运行 Typer 应用（统一捕获业务异常，避免裸 traceback 抛给用户）
    from .cli import suggest
    from .cli.app import app

    # 未知命令预校验：基于注册表层级做模糊建议，取代 Click 无建议的报错
    suggestions = suggest.suggest(list(sys.argv[1:]))
    if suggestions is not None:
        suggest.render_error(list(sys.argv[1:]), suggestions)
        raise SystemExit(2)

    try:
        # standalone_mode=False：让 Click 的 UsageError（缺参数/非法值/未知选项/
        # 未知命令）抛出来，统一走 suggest.render_usage_error 渲染，取代原生面板
        app(standalone_mode=False)
    except SSHMError as e:
        # 业务错误统一走全局异常解析器组装 ❌/⚠️ + 💡 模板（与 _fail 渲染一致）
        from .core.errors import resolve_error
        from .ui.output import ICON_ERR, ICON_WARN, print as _print
        from .ui.tip import render_business_error

        msg, hint, code, warn = resolve_error(e)
        render_business_error(msg, icon=ICON_WARN if warn else ICON_ERR, hint=hint)
        raise SystemExit(code)
    except (click.UsageError, _TyperUsageError) as e:
        # 用法错误（缺参数/非法枚举/未知选项/未知命令等）：统一模板渲染。
        # typer 0.27 起用法错误为 typer._click.exceptions.*，需与 click.UsageError
        # 一并捕获，否则会裸 traceback 抛给用户。
        suggest.render_usage_error(e, list(sys.argv[1:]))
        raise SystemExit(e.exit_code)


if __name__ == "__main__":
    main()
