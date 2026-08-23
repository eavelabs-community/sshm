#!/usr/bin/env python3
"""
i18n - 翻译入口

设计：
- 稳定 key：所有用户可见文案使用 `K.*` 常量（见 language/keys.py）作为 key，
  通过 `_()` 查找对应语言文本，禁止在代码中硬编码中文/英文文案。
- 运行时可变语言：_current_lang 由 set_lang / load_from_state 控制。
- 语义图标翻译助手（ok/warn/tip/done/err）放在 ui/icons.py，
  避免 i18n ↔ ui.output 的循环依赖，调用点从 ui.icons 导入。
"""

import os

# 重新导出语言字典，便于外部直接访问
__all__ = [
    "EN",
    "ZH",
    "_",
    "ok",
    "warn",
    "tip",
    "done",
    "err",
    "get_lang",
    "language_display_name",
    "load_from_state",
    "resolve_lang",
    "set_lang",
]


# --------------------------------------------------------------------------
# 当前语言（运行时可变）
# --------------------------------------------------------------------------
_current_lang: str = "en"


def set_lang(lang: str) -> None:
    """设置当前语言（en/zh），非法值回退 en"""
    global _current_lang
    _current_lang = lang if lang == "zh" else "en"


def get_lang() -> str:
    """获取当前语言"""
    return _current_lang


def language_display_name(lang: str) -> str:
    """返回语言的本地化显示名（如 zh → '中文'，en → 'English'）。

    收敛 config/version 展示里硬编码的 "Chinese"/"English" 语言名。
    用 K.* 常量访问，便于守门工具识别 key 被使用。
    """
    from .language import K

    key = K.lbl.language_zh_name if lang == "zh" else K.lbl.language_en_name
    return _(key)


# --------------------------------------------------------------------------
# 语言解析
# --------------------------------------------------------------------------


def resolve_lang(env: str | None = None, state_lang: str | None = None) -> str:
    """解析最终语言: env > state > 'en'

    Args:
        env: SSHM_LANG 环境变量值
        state_lang: 状态文件中保存的 lang 字段
    """
    if env:
        e = env.strip().lower()
        if e in ("zh", "zh-cn", "zh_cn", "cn", "zh-hans", "zh_hans"):
            return "zh"
        if e in ("en", "en-us", "en_us", "us"):
            return "en"
    if state_lang:
        s = state_lang.strip().lower()
        if s in ("zh", "zh-cn", "zh_cn", "cn", "zh-hans", "zh_hans"):
            return "zh"
        if s in ("en", "en-us", "en_us", "us"):
            return "en"
    return "en"


def load_from_state(state_lang: str | None) -> None:
    """从状态文件加载语言并应用（环境变量优先）"""
    env = os.environ.get("SSHM_LANG")
    set_lang(resolve_lang(env, state_lang))


# --------------------------------------------------------------------------
# 语义图标翻译助手
# --------------------------------------------------------------------------
# 把「图标 + 翻译 key」的拼接提取到一处，调用点不再手写 emoji：
#   tip(K.suggest.usage)   等价于  f"{ICON_TIP} {_(K.suggest.usage)}"
#   ok(K.msg.key_created)  等价于  f"{ICON_OK} {_(K.msg.key_created)}"
# 图标用字面量（与 ui.output 的 ICON_* / _EMOJI_STYLE 字符一致），不 import
# ui.output，避免 i18n ↔ ui.output 的循环依赖。
# 注意：错误类消息（ErrCode）的图标由错误类型绑定（_fail(icon=...)），
#       不在此处处理；动态拼接的已翻译文本（如 confirm_msg）也保持原样。


def ok(key: str, **kwargs) -> str:
    """带 ✅ 的成功消息"""
    return f"✅ {_(key, **kwargs)}"


def warn(key: str, **kwargs) -> str:
    """带 ⚠️ 的警告/提示消息"""
    return f"⚠️  {_(key, **kwargs)}"


def tip(key: str, **kwargs) -> str:
    """带 💡 的提示消息"""
    return f"💡 {_(key, **kwargs)}"


def done(key: str, **kwargs) -> str:
    """带 🎉 的完成消息"""
    return f"🎉 {_(key, **kwargs)}"


def err(key: str, **kwargs) -> str:
    """带 ❌ 的错误消息"""
    return f"❌ {_(key, **kwargs)}"


import sys as _sys

del _sys


# --------------------------------------------------------------------------
# 翻译函数
# --------------------------------------------------------------------------


def _(text: str, **kwargs) -> str:
    """按当前语言查找稳定 key 对应的文本（支持 {placeholder} 格式化）

    Args:
        text: 稳定翻译 key（如 'cmd.list' / 'opt.label'）
        **kwargs: 占位符变量

    若当前语言字典中缺失该 key，回退到英文；英文也缺失则返回 key 本身，
    便于发现遗漏的翻译。
    """
    table = ZH if _current_lang == "zh" else EN
    result = table.get(text)
    if result is None:
        result = EN.get(text, text)
    if kwargs:
        try:
            result = result.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            pass
    return result


# language 字典延后到本文件末尾导入，避免包初始化期间 i18n 加载到一半
# 就被 language → core → commands → author 链要求 _ok 而陷入循环。
from .language.i18n_en import EN
from .language.i18n_zh import ZH
