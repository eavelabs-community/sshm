#!/usr/bin/env python3
"""
参数解析工具 - 通用输入解析，消除 history.py 与 cli/app.py 重复的 _split_pair。
"""

from __future__ import annotations

__all__ = ["split_pair"]


def split_pair(value: str | None) -> tuple[str | None, str | None]:
    """解析 'OLD:NEW' 或 'NEW' 形式的参数。

    用于 `sshm history rewrite --name/--email` 的取值：
    - 包含 ':' 时按 'OLD:NEW' 拆分，空段归一为 None；
    - 不含 ':' 时视为仅提供新值，old 为 None；
    - 空值返回 (None, None)。

    Returns:
        (old, new)：old 仅在包含 ':' 时非空。
    """
    if not value:
        return None, None
    if ":" in value:
        old, _, new = value.partition(":")
        return (old or None), (new or None)
    return None, value
