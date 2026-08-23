#!/usr/bin/env python3
"""
未知命令"你是不是要找"建议 - 基于命令注册表层级做模糊匹配。

当用户输入不存在的命令（顶层分组名或组内子命令）时，根据 cli.registry 的
GROUPS / GROUP_ORDER 层级结构，用 difflib 做模糊匹配，动态给出最相近的完整
命令路径建议，取代 Click 默认的无建议报错（仅"No such command 'X'."）。

设计：
- 只对"首 token 是分组 / 组内子命令"两类错误做建议；合法路径、顶层选项
  （-h/--version 等）一律返回 None，交由 Typer/Click 正常处理。
- 层级感知：组内错误只在该组内建议；顶层错误建议相近分组 + 相近的子命令全路径。
"""

from __future__ import annotations

import difflib
from typing import Any

from ..i18n import _
from ..language import K
from ..ui.console import _console, get_display_width
from ..ui.icons import tip as _tip
from ..ui.tip import command_list_lines


from .registry import GROUP_ORDER, commands_in_group, related_commands

# difflib 相似度阈值：精确/拼写错误的强匹配阈值，低于此值视为无相近候选
_CUTOFF = 0.6

# 全局帮助/版本选项：命中时不干预，交由 Click 的 eager callback 处理
_NON_INTERFERING = ("-h", "--help", "-v", "--version")


def _sub_names(group: str) -> list[str]:
    """某分组的子命令名清单（保持注册表顺序）。"""
    return [m.name for m in commands_in_group(group)]


def _fuzzy(needle: str, choices: list[str], n: int = 3, cutoff: float = _CUTOFF) -> list[str]:
    """返回与 needle 相近的候选（按相似度降序，最多 n 个）。"""
    return difflib.get_close_matches(needle, choices, n=n, cutoff=cutoff)


def _known_groups() -> list[str]:
    return list(GROUP_ORDER)


def suggest(argv: list[str]) -> list[str] | None:
    """判断命令路径是否合法，返回建议命令清单；合法 / 不应干预返回 None。

    argv 为 `sys.argv[1:]`（不含程序名），仅取非选项 token 判断层级。

    建议规则（层级感知、控制噪音）：
    - 组内错误：只在该组内按强阈值做相近子命令匹配；
    - 顶层错误：先给"精确子命令"全路径（最可能忘写分组），再给相近分组，
      最后给相近子命令全路径；相似度低于阈值的不建议，避免误导。
    """
    # 命中帮助/版本选项：交给 Click 的 eager callback，不干预
    if any(flag in argv for flag in _NON_INTERFERING):
        return None

    args = [a for a in argv if not a.startswith("-") and a]
    groups = _known_groups()
    if not args:
        return None
    first = args[0]

    # 场景 1：组内子命令错误（如 `sshm key lst`）
    if first in groups:
        if len(args) < 2:
            return None  # 仅分组名，合法（默认视图 / 帮助）
        second = args[1]
        if second in _sub_names(first):
            return None  # 合法子命令
        matches = _fuzzy(second, _sub_names(first))
        return [f"sshm {first} {m}" for m in matches] if matches else []

    # 场景 2：顶层命令错误（如 `sshm list` / `sshm keyz`）
    suggests: list[str] = []
    # 2a. 精确子命令全路径（最可能忘写分组）：sshm <group> <sub>
    for g in groups:
        if first in _sub_names(g):
            suggests.append(f"sshm {g} {first}")
    # 2b. 相近分组（分组名拼写错误）：sshm <group>
    for g in _fuzzy(first, groups):
        suggests.append(f"sshm {g}")
    # 2c. 相近子命令全路径（子命令拼写错误）：sshm <group> <sub>
    for g in groups:
        for m in _fuzzy(first, _sub_names(g), n=1):
            suggests.append(f"sshm {g} {m}")
    return _dedup(suggests)


def _dedup(items: list[str]) -> list[str]:
    """去重并保持首次出现顺序。"""
    seen = set()
    result = []
    for it in items:
        if it not in seen:
            seen.add(it)
            result.append(it)
    return result


def render_error(argv: list[str], suggestions: list[str]) -> None:
    """渲染"未知命令"错误 + 建议 + 本组相关命令（统一 tip 段模板）。

    结构（与常规命令底部 tip 完全同源，均走 render_tip_block）：

        ❌ No such command 'list'.            ← 首行，无上方分隔线
        ──── separator ────
        💡 Did you mean:                       ← 建议块
          sshm key list
          sshm backup list
        ──── separator ────
        💡 More commands in this group         ← 本组相关命令块
          sshm key create   ...

    组内错误（first 为合法分组）→ 展示该分组命令；顶层未知 → 展示顶层分组。
    """
    from ..ui.output import print as _print
    from ..ui.tip import render_tip_block

    args = [a for a in argv if not a.startswith("-") and a]
    first = args[0] if args else ""

    # 判定错误场景类型与主消息
    if first in _known_groups() and len(args) >= 2:
        group = first
        msg = _(K.err.no_such_subcommand, group=group, cmd=args[1])
    else:
        group = None
        msg = _(K.err.no_such_command, cmd=first)

    # 与常规命令输出一致：顶部先空一行，再输出内容
    _print()

    # 块1：错误消息（作为首行，不带上方分隔线）
    # 命令名/参数可能含方括号（如 [en|zh]），rich 会误判为 markup，需转义
    from rich.markup import escape as _rich_escape

    render_tip_block([f"❌ {_rich_escape(msg)}"], top=False)

    # 块2：建议 / 提示（建议行统一用 ➖ 前缀，与命令列表一致）
    from ..ui.tip import ITEM_BULLET

    if suggestions:
        tip_lines = [_tip(K.suggest.did_you_mean)]
        tip_lines += [f"{ITEM_BULLET} {s}" for s in suggestions]
    else:
        tip_lines = [_tip(K.suggest.hint_help)]
    render_tip_block(tip_lines)

    # 块3：本组相关命令（组内错误 → 该分组全量命令；顶层未知 → 顶层分组名）
    # 该区域与命令底部"More commands"一致，用 dim 降亮度
    cmds = commands_in_group(group) if group else _known_groups()
    render_tip_block(command_list_lines(group, cmds), style="dim")


def _command_params_block(exc: Any) -> list[str]:
    """统一生成"命令参数说明块"（从 Click 命令参数解析、填充数据）。

    这是所有用法错误场景复用的唯一解析入口。输出两条信息：
      1. `💡 Usage: ...` 完整签名 —— 必填参数 `<LABEL>`，可选选项 `[...]`
      2. 每个参数一行 —— 签名 token 左对齐 + 必填/可选 + 含义（help）

    例如 `key switch`：
        💡 Usage: sshm key switch <LABEL> [--type/-t <TYPE>]
          <LABEL>              必填  key label
          [--type/-t <TYPE>]   可选  key type (default: auto-detect)

    Args:
        exc: 带 `ctx` 的 Click 异常（MissingParameter 等）。

    Returns:
        参数说明行列表；拿不到命令/参数时返回 []。
    """
    ctx = getattr(exc, "ctx", None)
    cmd = ctx.command if ctx is not None else None
    if cmd is None or not getattr(cmd, "params", None):
        return []
    group = ctx.parent.info_name if (ctx is not None and ctx.parent is not None) else None
    if group:
        base = f"sshm {group} {cmd.name}"
    elif cmd.name in (None, "sshm"):
        # 顶层命令（应用名即 sshm）：避免拼出 `sshm sshm` 的重复
        base = "sshm"
    else:
        base = f"sshm {cmd.name}"

    # 每个参数：签名 token + 是否必填 + 含义
    # typer 0.27 起 TyperArgument/TyperOption 不再继承 click.core.Argument
    # （改用自研的 typer._click.core.Parameter 基类），仅 isinstance(click.Argument)
    # 会把位置参数误判为选项，渲染成 `label LABEL` 而非 `<LABEL>`（CI 三平台失败）。
    # 同时兼容新旧 typer：旧版 TyperArgument 是 click.Argument 子类，新版不是。
    from click.core import Argument as _ClickArgument
    from typer.core import TyperArgument as _TyperArgument

    entries = []
    for p in cmd.params:
        # 统一大写：`human_readable_name` 在 Linux/Windows 上大小写可能不同
        # （如 `label` vs `LABEL`），统一转大写以保证跨平台 Usage 一致
        human = (getattr(p, "human_readable_name", None) or p.name or "").upper()
        required = bool(getattr(p, "required", False))
        help_txt = getattr(p, "help", None) or ""
        is_argument = isinstance(p, _ClickArgument) or isinstance(p, _TyperArgument)
        opts = getattr(p, "opts", None) or []
        flag = "/".join(opts) if opts else (human or "")
        # 枚举/选择参数（Click Choice）：直接展示支持值 ed25519|rsa|...，
        # 避免 metavar 组合出 <[en|zh]> / [LANG]: 等怪名（与原生 help 一致）
        choices = getattr(getattr(p, "type", None), "choices", None)
        if choices:
            value = "|".join(choices)
            token = f"{flag} {value}" if not is_argument and opts else value
        elif is_argument:
            # 位置参数：<LABEL>（必填）；可选参数由下方统一包成 [TARGET]
            token = f"<{human}>" if required else human
        elif getattr(p, "is_flag", False):
            # 布尔选项：--global/-g，不带值占位符
            token = flag
        else:
            # 普通选项：--path/-p <PATH>
            token = f"{flag} {human.upper()}" if human else flag
        if not required:
            token = f"[{token}]"
        entries.append((token, required, help_txt))

    # Usage 完整签名：按实际终端宽度（rich Console）自适应续行，
    # 续行缩进对齐到 "ICON_TIP Usage: " 之后（用显示宽度计算，中文/emoji 双宽正确）。
    prefix = f"{_tip(K.suggest.usage)} {base}"
    indent = " " * get_display_width(prefix)
    term_width = max(getattr(_console, "width", None) or 80, 1)
    tokens = [t for t, _, _ in entries]
    lines = []
    cur = prefix
    for tok in tokens:
        if get_display_width(cur) + 1 + get_display_width(tok) > term_width:
            lines.append(cur)
            cur = indent + tok
        else:
            cur += " " + tok
    lines.append(cur)

    # 参数解释行（token 列对齐）
    if entries:
        width = max(len(t) for t, _, _ in entries)
        for token, required, help_txt in entries:
            tag = _(K.suggest.required) if required else _(K.suggest.optional)
            row = f"  {token:<{width}}  {tag}"
            if help_txt:
                row += f"  {help_txt}"
            lines.append(row)
    # 方括号（如 [en|zh] / [--type/-t ...]）会被 rich 当作 markup 吞掉，
    # 统一转义，保证命令签名原样显示。
    from rich.markup import escape

    return [escape(line) for line in lines]


def _infer_group_commands(argv: list[str]) -> list[list[str]]:
    """从 argv 推断当前分组，生成相关命令块（本组 + 跨组 related，各带标题）。

    如 `sshm key switch` → 分组 `key` → [本组 key 命令块, 跨组 repo use 块]。
    无法推断时返回 []。返回二维列表，逐块交给 render_tip_block。
    """
    from ..ui.tip import related_command_blocks

    args = [a for a in argv if not a.startswith("-") and a]
    if not args or args[0] not in _known_groups():
        return []
    group = args[0]
    current = args[1] if len(args) > 1 else ""
    # 用 related_commands 推导：命令若声明了跨组 related（如 key switch → repo use），
    # 缺参/用法错误提示同样能展示该跨组关联命令，与命令正常执行后的 tip 一致。
    cmds = related_commands(group, current) if current else commands_in_group(group)
    return related_command_blocks(group, cmds)


def render_usage_error(exc: Any, argv: list[str]) -> None:
    """统一渲染任意 Click 用法错误（缺参数/非法值/未知选项/未知命令等）。

    取代 Click 原生 `┌─ Error ─...` 面板，全部走 render_tip_block 统一模板，
    与 `render_error`（命令建议）视觉一致：

        ❌ Missing argument 'LABEL'.        ← 首行，无上方分隔线
        ──── separator ────
        💡 Run 'sshm --help' to see all ...   ← 用法提示块

    判定规则：
    - 若 suggest(argv) 判定为"未知命令"（返回非 None）→ 复用 render_error 的
      完整命令建议（Did you mean + More commands）。
    - 否则（缺参数/非法值/未知选项等命令合法但用法不对）→ ❌ 错误消息 +
      `-h` 用法提示。

    Args:
        exc: 捕获到的 Click UsageError（如 MissingParameter、BadParameter、
             NoSuchOption 或未知命令的通用 UsageError）。
        argv: 原始命令参数（sys.argv[1:]）。
    """
    from ..ui.output import print as _print
    from ..ui.tip import render_tip_block

    # 未知命令：复用完整命令建议（含 Did you mean + More commands）
    suggestions = suggest(argv)
    if suggestions is not None:
        render_error(argv, suggestions)
        return

    msg = exc.format_message()  # 如 "Missing argument 'LABEL'."
    _print()
    # 错误消息可能含方括号（如 Invalid value for '[en|zh]'），rich 会误判为
    # markup 而吞掉，统一转义保证原样显示。
    from rich.markup import escape as _rich_escape

    render_tip_block([f"❌ {_rich_escape(msg)}"], top=False)

    # 所有用法错误统一展示：该命令完整参数说明 + 同组相关命令
    # （缺必填参数、非法枚举值、选项缺值等，全部复用 _command_params_block）
    params = _command_params_block(exc) if getattr(exc, "ctx", None) else []
    if params:
        render_tip_block(params)
    for block in _infer_group_commands(argv):
        render_tip_block(block, style="dim")
