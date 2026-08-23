#!/usr/bin/env python3
"""
语义图标翻译助手 - 把「图标 + 翻译 key」的拼接集中到一处。

i18n.py 定义了 ok/warn/tip/done/err，本模块作为 UI 层的统一入口，供
commands / services / cli 复用，消除各处重复定义的 `_ok/_tip/_warn/_done`
转发函数。

设计：
- 仅延迟转发到 sshm.i18n（函数体内 import），模块顶层不 import i18n，
  避免 sshm 包初始化期间 commands 被强制加载时触发 i18n 循环依赖。
- 不 import ui.output，避免 i18n ↔ ui.output 的循环依赖（与 i18n.py 注释一致）。
- 图标字面量与 ui.output 的 ICON_* 一致，但为规避循环依赖在此不引用。
"""

from __future__ import annotations

__all__ = ["done", "err", "ok", "tip", "warn"]


def ok(key: str, **kwargs) -> str:
    """带 ✅ 的成功消息"""
    from ..i18n import ok

    return ok(key, **kwargs)


def warn(key: str, **kwargs) -> str:
    """带 ⚠️ 的警告/提示消息"""
    from ..i18n import warn

    return warn(key, **kwargs)


def tip(key: str, **kwargs) -> str:
    """带 💡 的提示消息"""
    from ..i18n import tip

    return tip(key, **kwargs)


def done(key: str, **kwargs) -> str:
    """带 🎉 的完成消息"""
    from ..i18n import done

    return done(key, **kwargs)


def err(key: str, **kwargs) -> str:
    """带 ❌ 的错误消息"""
    from ..i18n import err

    return err(key, **kwargs)
