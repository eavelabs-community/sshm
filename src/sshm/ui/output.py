#!/usr/bin/env python3
"""
输出抽象 - 将核心层与具体控制台输出解耦。

核心层（core）不再直接调用内置 print，而是通过本模块的路由函数输出；
默认实现基于 rich（正式依赖），非 tty 时自动降级为纯文本。后续 GUI /
`--json` / 静默模式只需 `set_output()` 换实现。

设计：
- Output        ：接口（print / section / table / separator / confirm）
- ConsoleOutput ：默认实现，委托 ui.console（基于 rich）
- NullOutput    ：静默实现（供测试 / 无输出场景，confirm 恒为 True）
- 模块级当前输出 + set_output / get_output 注入点
- 路由函数与 core 层既有调用保持同名，行为委托给当前输出
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import ClassVar

from rich.console import Console as _RichConsole
from rich.progress import Progress as _RichProgress

from .console import (
    _console,
    print_section_header,
    print_separator,
    print_table,
    prompt_confirm,
)

__all__ = [
    "ConsoleOutput",
    "NullOutput",
    "Output",
    "confirm",
    "get_output",
    "print",
    "progress",
    "section",
    "separator",
    "set_output",
    "status",
    "table",
]


class Output:
    """输出接口：核心层通过本接口输出，可替换为 GUI / JSON / 静默实现。"""

    def print(self, *args, **kwargs) -> None:
        raise NotImplementedError

    def section(self, title: str) -> None:
        raise NotImplementedError

    def table(self, headers, rows, **kwargs) -> None:
        raise NotImplementedError

    def separator(self, char: str = "=", length: int = 80) -> None:
        raise NotImplementedError

    def confirm(self, message: str, default: str | None = None) -> bool:
        raise NotImplementedError


# 语义图标常量：输出/命令/服务统一引用，避免各处硬编码 emoji 字符。
ICON_OK = "✅"
ICON_ERR = "❌"
ICON_WARN = "⚠️"
ICON_TIP = "💡"
ICON_DONE = "🎉"
ICON_BULLET = "➖"


class ConsoleOutput(Output):
    """默认控制台输出：基于 rich 渲染，非 tty 自动降级为纯文本。"""

    # 状态 emoji 前缀 -> 语义颜色：按消息开头 emoji 自动着色，
    # 无需改动各命令调用点即可获得语义化的终端配色。
    _EMOJI_STYLE: ClassVar[dict] = {
        ICON_OK: "bold green",
        ICON_DONE: "bold green",
        "✔": "bold green",
        ICON_WARN: "yellow",
        "❗": "yellow",
        ICON_ERR: "bold red",
        "✘": "bold red",
        ICON_TIP: "cyan",
        "🔀": "cyan",
        "📝": "cyan",
    }
    _style_map: ClassVar[dict] = {
        "info": "cyan",
        "success": "bold green",
        "warn": "yellow",
        "error": "bold red",
        "dim": "dim",
    }

    def print(self, *args, **kwargs) -> None:
        # style 语义参数：映射为 rich 颜色；显式 style 优先级最高，
        # 未指定时按消息开头 emoji 自动识别语义颜色。
        style: str | None = kwargs.pop("style", None)
        if style is None and args:
            first = str(args[0])
            for emoji, color in self._EMOJI_STYLE.items():
                if first.startswith(emoji):
                    style = color
                    break
        rich_style: str | None
        if isinstance(style, str):
            rich_style = self._style_map.get(style, style)
        else:
            rich_style = None
        _console.print(*args, style=rich_style, **kwargs)

    def section(self, title: str) -> None:
        print_section_header(title)

    def table(self, headers, rows, **kwargs) -> None:
        print_table(headers, rows, **kwargs)

    def separator(self, char: str = "=", length: int = 80) -> None:
        print_separator(char, length)

    def confirm(self, message: str, default: str | None = None) -> bool:
        return prompt_confirm(message, default)


class NullOutput(Output):
    """静默输出：不产生任何输出；确认一律视为 True（自动通过）。"""

    def print(self, *args, **kwargs) -> None:
        pass

    def section(self, title: str) -> None:
        pass

    def table(self, headers, rows, **kwargs) -> None:
        pass

    def separator(self, char: str = "=", length: int = 80) -> None:
        pass

    def confirm(self, message: str, default: str | None = None) -> bool:
        return True


# --------------------------------------------------------------------------
# 模块级当前输出（注入点）
# 默认基于 rich 渲染；非 tty（管道/重定向/测试）时 rich 自动降级为纯文本。
# 需要还原无颜色旧行为可用 set_output(ConsoleOutput())。
# --------------------------------------------------------------------------
_current: Output = ConsoleOutput()


def set_output(output: Output) -> None:
    """替换当前输出实现（GUI / JSON / 静默模式入口）"""
    global _current
    _current = output


def get_output() -> Output:
    """获取当前输出实现"""
    return _current


# --------------------------------------------------------------------------
# 路由函数：与 core 层既有调用保持同名，行为委托给当前输出
# --------------------------------------------------------------------------
def print(*args, **kwargs) -> None:
    _current.print(*args, **kwargs)


def section(title: str) -> None:
    _current.section(title)


def table(headers, rows, **kwargs) -> None:
    _current.table(headers, rows, **kwargs)


def separator(char: str = "=", length: int = 80) -> None:
    _current.separator(char, length)


def confirm(message: str, default: str | None = None) -> bool:
    return _current.confirm(message, default)


# --------------------------------------------------------------------------
# 进度条 / spinner。基于 rich，非 tty 时自动降级为无操作，保证安全。
# --------------------------------------------------------------------------
class _NoopProgress:
    """rich 不可用时的空进度句柄：所有调用静默，不产生任何输出。"""

    def __init__(self, total: float | None = None, desc: str = "") -> None:
        self.completed = 0.0
        self.total = total

    def update(
        self,
        completed: float = 1,
        advance: float | None = None,
        total: float | None = None,
        **kwargs,
    ) -> None:
        if advance is not None:
            self.completed += advance
        else:
            self.completed = completed

    def advance(self, amount: float = 1) -> None:
        self.completed += amount

    def stop(self) -> None:
        pass


class _RichProgressHandle:
    """rich 进度句柄：封装 Progress 与 task_id，暴露统一的 update/advance。"""

    def __init__(self, progress: _RichProgress, task_id, total):
        self._progress = progress
        self._task_id = task_id
        self._total = total
        self.completed = 0.0

    def update(
        self,
        completed: float = 1,
        advance: float | None = None,
        total: float | None = None,
        **kwargs,
    ) -> None:
        if advance is not None:
            self.completed += advance
        else:
            self.completed = completed
        kwargs.setdefault("total", self._total if total is None else total)
        self._progress.update(self._task_id, completed=self.completed, **kwargs)

    def advance(self, amount: float = 1) -> None:
        self.completed += amount
        self._progress.advance(self._task_id, amount)

    def stop(self) -> None:
        self._progress.stop_task(self._task_id)


@contextmanager
def progress(total: float | None = None, desc: str = "") -> Iterator:
    """进度条上下文管理器。

    rich 可用时显示真实进度条；非 tty 时自动降级为无操作。

    用法::

        with progress(total=100, desc="下载中") as p:
            p.advance(25)      # 或 p.update(completed=50)

    注意：在需要实时刷新的 for 循环里，务必将进度条置于 `with` 内并逐次 advance。
    """
    console = _RichConsole(force_terminal=False)
    # 仅在「创建/启动」进度条阶段降级：非 tty / rich 渲染不可用时返回空句柄，
    # 业务照常执行。body 内抛出的异常必须原样向上传播，绝不能在 except 里再次
    # yield（那会触发 contextlib 的 "generator didn't stop after throw()"，
    # 并掩盖真实的业务错误）。
    try:
        prog = _RichProgress(console=console, transient=True)
        prog.__enter__()
    except Exception:
        yield _NoopProgress(total, desc)
        return
    try:
        task_id = prog.add_task(desc, total=total)
        yield _RichProgressHandle(prog, task_id, total)
    finally:
        prog.__exit__(None, None, None)


@contextmanager
def status(desc: str = "") -> Iterator:
    """spinner 上下文管理器。

    用于短时但可能耗时的操作（如历史重写）：显示一个转圈动画 + 描述。
    非 tty 时静默无操作。
    """
    console = _RichConsole(force_terminal=False)
    # 仅在「创建/启动」spinner 阶段降级：非 tty / rich 渲染不可用时静默无操作，
    # 业务照常执行。body 内抛出的异常必须原样向上传播，绝不能在 except 里再次
    # yield（那会触发 contextlib 的 "generator didn't stop after throw()"，
    # 并掩盖真实的业务错误——例如 history rewrite 中 fast-import 的真实失败原因）。
    try:
        status_obj = console.status(desc, spinner="dots")
        status_obj.__enter__()
    except Exception:
        yield
        return
    try:
        yield
    finally:
        status_obj.__exit__(None, None, None)
