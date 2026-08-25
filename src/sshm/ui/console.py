#!/usr/bin/env python3
"""
控制台工具模块 - 格式化输出、Windows 编码修复等。

渲染能力基于 rich 实现（rich 为正式依赖）：表格 / 分隔线 / 确认提示等
统一委托 rich，非 tty（管道 / 重定向 / 测试）下 rich 自动降级为纯文本，
不产生 ANSI 码，输出行为保持干净可预测。
"""

import sys
from collections.abc import Iterable
from datetime import datetime

from rich.console import Console
from rich.prompt import Confirm as RichConfirm
from rich.rule import Rule
from rich.table import Table
from wcwidth import wcswidth as _wcswidth
from wcwidth import wcwidth as _wcwidth_char

from ..language import K

# 统一的 rich Console：非 tty 时自动禁用颜色/装饰，保证管道输出干净
_console = Console()


def setup_windows_console() -> None:
    """修复 Windows 控制台 UTF-8 编码问题。

    设置控制台代码页为 UTF-8，并正确处理 stdout/stderr 编码：
    - tty（真实控制台）：切换为 UTF-8，配合 SetConsoleOutputCP(65001)，
      中文与 emoji 均正确显示；
    - 非 tty（管道/重定向）：保留系统编码（如 GBK，管道消费方可读中文），
      仅放宽 errors='replace'，使 emoji 等无法编码的字符替换为 '?' 而非崩溃。

    通过 `reconfigure` 原地修改现有流对象（而非替换），避免破坏 pytest
    捕获等场景；流对象不支持 reconfigure 时自动跳过。必须在任何输出之前完成。
    """
    if sys.platform != "win32":
        return

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        # 设置控制台代码页为 UTF-8 (65001)
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleCP(65001)
    except Exception:
        pass  # 静默失败（如无 ctypes / 控制台句柄异常）

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            if getattr(stream, "isatty", lambda: False)():
                reconfigure(encoding="utf-8", errors="replace")
            else:
                reconfigure(errors="replace")
        except Exception:
            pass  # 静默失败（如流不支持该操作）


def format_timestamp(dt: datetime) -> str:
    """格式化时间戳"""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def format_size(size_bytes: int) -> str:
    """格式化文件大小为人类可读形式"""
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size_bytes} B"


def get_display_width(text: str) -> int:
    """计算字符串在终端中的显示宽度（中文/emoji 按双宽计）

    优先使用 wcwidth 库（Unicode 标准宽度，正确处理 emoji 与
    变体选择符），未安装时回退到内置的 Unicode 判断逻辑。
    """
    try:
        width = _wcswidth(text)
        if width >= 0:
            return width
    except Exception:
        pass
    return sum(_char_width(ch) for ch in text)


def _char_width(ch: str) -> int:
    """计算单个字符的显示宽度（wcwidth 优先，含零宽变体选择符处理）"""
    try:
        width = _wcwidth_char(ch)
        if width >= 0:
            return width
    except Exception:
        pass
    import unicodedata

    code = ord(ch)
    # 零宽字符：变体选择符（emoji 后续 FE0F/FE0E）、零宽连接符等
    if code in (0x200B, 0x200C, 0x200D, 0x2060) or 0xFE00 <= code <= 0xFE0F:
        return 0
    # 常见 emoji/符号区域（多数终端按双宽渲染）
    if 0x2600 <= code <= 0x27FF or 0x2B00 <= code <= 0x2BFF or 0x1F000 <= code <= 0x1FAFF:
        return 2
    if unicodedata.east_asian_width(ch) in ("W", "F", "A"):
        return 2
    return 1


def pad_cell(text: str | None, width: int, align: str = "left") -> str:
    """按显示宽度对齐单元格文本，超宽时截断并追加省略号。

    text 为 None 时按空串处理（适配解包自 Unknown 元组的调用点）。
    """
    text = text or ""
    text_width = get_display_width(text)
    if text_width > width:
        result = ""
        result_width = 0
        ellipsis_width = _char_width("…")
        for ch in text:
            ch_width = _char_width(ch)
            if result_width + ch_width > width - ellipsis_width:
                break
            result += ch
            result_width += ch_width
        if result_width + ellipsis_width <= width:
            result += "…"
        return result

    padding = width - text_width
    if align == "right":
        return " " * padding + text
    if align == "center":
        left = padding // 2
        return " " * left + text + " " * (padding - left)
    return text + " " * padding


def print_table(
    headers: list,
    rows: list,
    truncatable: Iterable[int] | None = None,
    center_cols: Iterable[int] | None = None,
    min_widths: dict | None = None,
) -> None:
    """以表格形式打印数据，完全基于 rich Table 原生能力。

    Args:
        headers: 表头列表
        rows: 数据行列表（二维列表）
        truncatable: 允许超宽截断的列索引集合（对应 rich overflow='ellipsis'）
        center_cols: 数据居中对齐的列索引集合
        min_widths: {列索引: 最小宽度}，保证关键列（如表头）可读；rich 在
            窄终端下会优先压缩未设 min_width 的列，而非截断列头。
    """
    headers = [str(h) for h in headers]
    rows = [[str(cell) for cell in row] for row in rows]
    if not headers:
        return
    truncatable = set(truncatable or [])
    center_cols = set(center_cols or [])
    min_widths = min_widths or {}

    # 交给 rich Table 自适应：不设置固定 width，列级 overflow 处理超宽单元格，
    # 关键列用 min_width 保证可读性（rich 在窄终端压缩其他列，不删列、不截表头）。
    table = Table(show_header=True, header_style="bold", pad_edge=False, box=None)

    for i, h in enumerate(headers):
        table.add_column(
            h,
            justify="center" if i in center_cols else "left",
            overflow="ellipsis" if i in truncatable else "crop",
            min_width=min_widths.get(i),
        )
    for row in rows:
        table.add_row(*row)

    _console.print(table)


def prompt_confirm(message: str, default: str | None = None) -> bool:
    """确认提示（基于 rich.prompt.Confirm）

    Args:
        message: 提示文本
        default: 回车时的默认值，'y' 默认确认，'n' 默认拒绝，None 时必须输入
    """
    if default == "y":
        rich_default = True
    elif default == "n":
        rich_default = False
    else:
        rich_default = None
    return bool(RichConfirm.ask(message, default=rich_default))


def print_separator(char: str = "=", length: int = 80) -> None:
    """打印分隔线。

    真实终端用 rich Rule（彩色横线）；非 tty（管道/重定向/GBK 控制台）用
    纯 ASCII 字符，避免 Unicode 横线被替换为乱码。NullOutput 下静默
    （供 GUI/JSON/静默模式与测试隔离），延迟导入避免 console↔output 循环依赖。
    """
    from .output import NullOutput, get_output

    if isinstance(get_output(), NullOutput):
        return
    if getattr(_console, "is_terminal", False):
        _console.print(Rule(style="cyan"))
    else:
        print(char * length)


def print_section_header(title: str) -> None:
    """打印章节标题（基于 rich Rule + 粗体标题）。"""
    from .output import NullOutput, get_output

    if isinstance(get_output(), NullOutput):
        return
    if getattr(_console, "is_terminal", False):
        _console.print(Rule(f"[bold]{title}[/bold]", style="cyan"))
    else:
        print(title)


def wait_for_key() -> None:
    """等待用户按键（基于 click.pause）"""
    import click

    from ..i18n import _

    click.pause(f"\n{_(K.menu.press_any)}")
