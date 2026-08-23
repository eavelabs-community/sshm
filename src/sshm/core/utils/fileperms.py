#!/usr/bin/env python3
"""
文件权限工具 - 设置密钥文件权限（Unix）。

keystore.py 的 _secure_perms 与 backup.py 的 _secure_key_perms 原本各有一份
逐字一致的实现，收敛到此共享函数，避免重复定义。
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["secure_key_perms"]


def secure_key_perms(path: Path, private: bool) -> None:
    """Unix 下兜底设置密钥文件权限：私钥 600，公钥 644。

    非 POSIX 平台（如 Windows）直接返回；权限设置失败（只读/平台异常）
    时静默忽略，不影响主流程。
    """
    if os.name != "posix":
        return
    try:
        path.chmod(0o600 if private else 0o644)
    except OSError:
        pass  # 平台/只读异常时忽略，不影响主流程
