#!/usr/bin/env python3
"""
配置命令组 - 系统配置（语言 / 自动作者联动开关 / 配置总览）。

只负责把用户意图翻译为对 StateManager 的编排调用 + 渲染。
系统级命令（更新 / 重新安装 / PATH）不在本组，见 system.py。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...i18n import _
from ...language import K
from ...ui.output import print
from ...ui.output import section as print_section_header

if TYPE_CHECKING:
    from ..manager import SSHKeyManager


class ConfigCommands:
    """配置命令编排。"""

    def __init__(self, m: SSHKeyManager):
        self.m = m

    def show(self) -> None:
        """显示当前系统配置总览（语言 + 自动作者联动开关）。"""
        from ...i18n import get_lang, language_display_name

        lang = get_lang()
        print_section_header(_(K.hdr.auto_author))
        print(f"   {_(K.lbl.current_language)} {language_display_name(lang)} ({lang})")

        auto_author = self.m.state_manager.read_auto_author()
        status = _(K.misc.on) if auto_author else _(K.misc.off)
        print(f"   🔀 {_(K.msg.auto_author_status, status=status)}")

    def language(self, lang: str) -> str:
        """设置输出语言并持久化到状态文件

        Args:
            lang: 'en' 或 'zh'

        Returns:
            实际生效的语言（非法值回退 'en'）
        """
        lang = lang if lang == "zh" else "en"
        self.m.state_manager.write_lang(lang)
        from ...i18n import set_lang

        set_lang(lang)
        return lang
