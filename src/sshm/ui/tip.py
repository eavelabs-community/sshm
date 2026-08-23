#!/usr/bin/env python3
"""
统一"tip 段"渲染模板 - 复用于命令底部与错误场景，避免到处手写不同的输出格式。

设计动机：
  原代码里"ICON_TIP 提示 + 列表"以多种形式散落在 _show_tip、单行 tip、
  内联 print 等多处，样式不一致；错误场景更是另起一个红色 Panel，
  风格与正常命令底部脱节。本模块提供唯一渲染入口：

    render_tip_block(lines)
      ───── separator ─────   ← 上下分隔线（与 ui.console.print_separator 一致）
      <line 1>                ← emoji 前缀自动着色（见 ui.output._EMOJI_STYLE）
      <line 2>
      ───── separator ─────

  这样：
    - 常规命令底部：💡 操作提示 + 💡 相关命令列表   → 同一段
    - 未知命令错误：❌ 错误信息 + 💡 你是不是要找     → 同一段
    - 多段堆叠：连续调用即可自动衔接（每段自带上下分隔线）

依赖：ui.console（分隔线）、ui.output（按 emoji 自动着色）。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .console import print_separator
from .output import ICON_BULLET, ICON_ERR, ICON_TIP
from .output import print as _print

__all__ = [
    "ITEM_BULLET",
    "command_list_lines",
    "related_command_blocks",
    "render_business_error",
    "render_tip_block",
]

# 命令/建议列表项统一前缀图标（与 💡 标题形成视觉层级，一处定义全局复用）
ITEM_BULLET = ICON_BULLET


def render_tip_block(lines: Iterable[str], *, top: bool = True, style: str | None = None) -> None:
    """渲染统一的 tip 段：可选顶部分隔线 + 内容行。

    设计：每段默认带一个**顶部分隔线**，不带底部分隔线。这样：
    - 单段使用：顶部 ─ + 内容，与底部自然过渡。
    - 多段连续调用：每段顶端各一条 ─，段间不会出现"双线"。
      例如连续两次 render_tip_block([...]) 输出：

        ──── separator ────
        <line 1>
        <line 2>
        ──── separator ────
        <line 3>
        <line 4>

    Args:
        lines: 内容行序列（每个元素一行）。
        top: 是否输出顶部分隔线。设为 False 时该段紧贴前文（如错误场景里
             `❌ 错误消息`作为首行，上方不应有分隔线）。
        style: 整段统一样式（如 'dim' 降亮度）。不传时按行首 emoji 自动着色
             （见 ui.output._EMOJI_STYLE）：💡 → cyan、❌ → bold red 等。

    非 tty 下分隔线降级为纯 ASCII 横线（与 ui.console.print_separator 一致）。
    """
    if top:
        print_separator("─")
    for line in lines:
        if style:
            _print(line, style=style)
        else:
            _print(line)


def command_list_lines(group: str | None, cmds: Iterable[Any], title_key: str = "misc.related_tip") -> list[str]:
    """统一生成"ICON_TIP More commands in this group"命令清单行（唯一格式来源）。

    收敛了原先散落在 app._show_tip 与 suggest._group_commands_lines /
    _top_level_lines 的命令行格式化逻辑，避免格式漂移。

    Args:
        group: 分组名（用于拼 `sshm <group> <name>`）；顶层场景传 None。
        cmds: 命令项序列。元素可以是：
          - CommandMeta（含 .name/.help_key）→ `sshm <group> <name>  <desc>`
          - 字符串（顶层分组名，无描述）→ `sshm <name>`

    返回可直接交给 render_tip_block 的行列表（首行为 💡 标题）。
    """
    from ..i18n import _

    lines = [f"{ICON_TIP} {_(title_key)}"]
    for item in cmds:
        if isinstance(item, str):
            lines.append(f"{ITEM_BULLET} sshm {item}")
        else:
            desc = _(item.help_key)
            # 用命令自身的分组（item.group）而非调用方传入的 group，
            # 使跨组 related 命令（如 key switch → repo use）正确显示为 `sshm repo use`
            item_group = item.group or group
            lines.append(f"{ITEM_BULLET} sshm {item_group} {item.name:<10} {desc}")
    return lines


def related_command_blocks(group: str | None, cmds: Iterable[Any]) -> list[list[str]]:
    """把相关命令分为「本组」与「跨组 related」两块，各自带标题行。

    同组命令标题为 misc.related_tip（More commands in this group）；
    跨组 related 命令（item.group != group）标题为 misc.related_tip_cross
    （More related commands），使 `key switch` 这类跨组关联一目了然。
    顶层分组名（字符串项）归入本组块。返回可逐块交给 render_tip_block 的二维列表。
    """
    from ..language import K

    local, cross = [], []
    for item in cmds:
        if isinstance(item, str):
            local.append(item)
        elif (item.group or group) != (group or ""):
            cross.append(item)
        else:
            local.append(item)
    blocks = []
    if local:
        blocks.append(command_list_lines(group, local, title_key=K.misc.related_tip))
    if cross:
        blocks.append(command_list_lines(group, cross, title_key=K.misc.related_tip_cross))
    return blocks


def render_business_error(msg: str, *, icon: str = ICON_ERR, hint: str | None = None) -> None:
    """统一渲染业务错误：顶部空行 + icon 消息 +（可选）💡 建议 tip 段。

    这是所有业务错误（_fail / SSHMError 的 CLI 出口）的唯一渲染点，
    避免调用点各自拼 `❌` 与手工格式化。

    Args:
        msg: 错误消息（不含图标前缀，调用点只需传纯消息）。
        icon: 状态图标，默认 ❌（硬错误、终止命令）；软告警传 ⚠️。
        hint: 可选建议行，如 `Use 'sshm author list' ...`，渲染为 💡 tip 段。
    """
    _print()
    _print(f"{icon} {msg}")
    if hint:
        # hint 可为多行（\n 分隔），逐行渲染为 💡 tip 段，保留既有缩进/前缀
        lines = [f"{ICON_TIP} {ln}" if idx == 0 else ln for idx, ln in enumerate(hint.split("\n"))]
        render_tip_block(lines)
