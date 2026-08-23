#!/usr/bin/env python3
"""
CLI 命令注册表 - 命令分组 / 命令元数据 / 同组关联 的单一事实来源。

设计目标：
- 所有命令的分组、名称、帮助 key、同组关联**集中在此定义**，cli.py 据此
  注册 Typer 命令，避免分组/命令清单散落各处。
- 任意命令输出底部的"相关指令" tip 由本注册表自动推导（按分组聚合），
  无需在各命令尾部手写硬编码。
- 颜色 token（语义样式名 -> rich 颜色）也集中于此，供 ui 层统一读取。

本模块只依赖 language.K（纯常量），不依赖 cli/ui 层，避免循环依赖。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..language import K


@dataclass(frozen=True)
class CommandMeta:
    """单条命令的注册元数据。"""

    name: str  # 命令名（如 'list'）
    help_key: str  # i18n help key（如 'cmd.key_list'）
    group: str  # 所属分组名（如 'key'）
    # 手动补充的"相关命令"（用于跨分组关联，如 switch 后提示 use）；为空时
    # 自动取同分组其余命令。字段为命令名，支持显式顺序。
    related: tuple = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# 分组定义：分组名 -> 有序命令清单（顺序即帮助/ tip 展示顺序）
# ---------------------------------------------------------------------------
GROUPS: dict[str, list[CommandMeta]] = {
    "key": [
        CommandMeta("list", K.cmd.key_list, "key"),
        CommandMeta("create", K.cmd.key_create, "key"),
        CommandMeta("remove", K.cmd.key_remove, "key"),
        CommandMeta("rename", K.cmd.key_rename, "key"),
        CommandMeta("label", K.cmd.key_label, "key"),
        CommandMeta("switch", K.cmd.key_switch, "key", related=("use",)),
        CommandMeta("current", K.cmd.key_current, "key"),
    ],
    "repo": [
        CommandMeta("use", K.cmd.repo_use, "repo"),
        CommandMeta("clone", K.cmd.repo_clone, "repo"),
        CommandMeta("info", K.cmd.repo_info, "repo"),
        CommandMeta("test", K.cmd.repo_test, "repo"),
    ],
    "backup": [
        CommandMeta("create", K.cmd.backup_create, "backup"),
        CommandMeta("list", K.cmd.backup_list, "backup"),
        CommandMeta("restore", K.cmd.backup_restore, "backup"),
    ],
    "author": [
        CommandMeta("list", K.cmd.author_list, "author"),
        CommandMeta("add", K.cmd.author_add, "author"),
        CommandMeta("update", K.cmd.author_update, "author"),
        CommandMeta("remove", K.cmd.author_remove, "author"),
        CommandMeta("use", K.cmd.author_use, "author"),
        CommandMeta("unset", K.cmd.author_unset, "author"),
    ],
    "history": [
        CommandMeta("rewrite", K.cmd.history_rewrite, "history"),
    ],
    "config": [
        CommandMeta("language", K.cmd.config_language, "config"),
        CommandMeta("auto-author", K.cmd.config_auto_author, "config"),
    ],
    "version": [
        CommandMeta("update", K.cmd.version_update, "version"),
        CommandMeta("reinstall", K.cmd.version_reinstall, "version"),
    ],
}

# 分组展示顺序（顶层帮助中的分组排列）
GROUP_ORDER: list[str] = ["key", "repo", "backup", "author", "history", "config", "version"]


# ---------------------------------------------------------------------------
# 便捷查询
# ---------------------------------------------------------------------------


def commands_in_group(group: str) -> list[CommandMeta]:
    """返回某分组的命令清单（无则空列表）。"""
    return list(GROUPS.get(group, []))


def related_commands(group: str, current: str, extra: tuple = ()) -> list[CommandMeta]:
    """返回某命令的"相关指令"（用于 tip）。

    - related 命令名作为**追加的跨组关联**（可跨分组，如 `key switch` 追加 `repo use`），
      命令名全局查找；同时仍保留同分组其余命令。
    - 无 related 时，自动取同分组其余命令（保持分组定义顺序）。
    - extra 用于手动追加跨分组的关联命令。
    """
    group_cmds = commands_in_group(group)
    # related 命令名可能跨分组，全局查找一次即可
    all_cmds = [m for g in GROUPS.values() for m in g]
    related_ordered: list[CommandMeta] = []
    for meta in group_cmds:
        if meta.name == current and meta.related:
            for nm in meta.related:
                for m in all_cmds:
                    if m.name == nm:
                        related_ordered.append(m)
                        break
            break
    related_names = {m.name for m in related_ordered}
    rest = [m for m in group_cmds if m.name != current and m.name not in related_names]
    return related_ordered + rest + list(extra)
