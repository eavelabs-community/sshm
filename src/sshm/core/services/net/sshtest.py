#!/usr/bin/env python3
"""
SSH 连接测试 - 封装对 `ssh -T git@host` 的探测与结果判定。

判定策略经过重构（原实现的关键词列表含过宽的 'hi '，且未禁用交互式提示）：
1) 失败关键词优先（失败文案通常比成功更明确）
2) 成功关键词 / 欢迎语（并尝试提取用户名）
3) 未知平台文案时以退出码兜底

额外加固：`-o BatchMode=yes` 禁用交互式密码提示（避免挂起）、
`-o ConnectTimeout=10` 限制 TCP 连接超时。
"""

from __future__ import annotations

import re
import subprocess

from ....i18n import _
from ....language import K
from ...utils.process import run_checked

# 成功关键词：优先精确匹配，避免误报（不采用过宽的 'hi '）
_SSH_SUCCESS_MARKERS = (
    "successfully authenticated",
    "welcome to github",
    "welcome to gitlab",
    "you've successfully authenticated",
    "authenticated via ssh",
    "access granted",
    "connection established",
)

# 失败关键词：命中即判失败
_SSH_FAILURE_MARKERS = (
    "permission denied",
    "could not resolve hostname",
    "connection refused",
    "connection timed out",
    "authentication failed",
    "host key verification failed",
    "no such file or directory",
    "please make sure you have the correct access rights",
    "invalid key",
    "unable to negotiate",
    "remote host identification has changed",
    "error: ",
)


class SSHTester:
    """SSH 连接测试器：只负责单次连接探测，返回 (是否成功, 说明, 用户名)。"""

    # 识别 "Hi <user>!" 形式的认证欢迎语，用于提取用户名
    _HI_RE = re.compile(r"Hi ([^!]+)!", re.IGNORECASE)
    _WELCOME_RE = re.compile(r"Welcome to [^,]+, (@?[\w.-]+)")

    def test(self, host: str) -> tuple[bool, str, str | None]:
        """测试 SSH 连接（兼容 GitHub/GitLab/Bitbucket/自建 Git 平台）

        Returns:
            (是否成功, 说明文本, 提取到的用户名或 None)。
            用户名是结构化字段，调用方勿依赖翻译文本反解，避免中文环境下失效。
        """
        try:
            result = run_checked(
                [
                    "ssh",
                    "-T",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "ConnectTimeout=10",
                    f"git@{host}",
                ],
                timeout=10,
            )

            output = (result.stdout or "") + (result.stderr or "")
            low = output.lower()

            # 1) 失败关键词优先（失败通常比成功更明确）
            if any(m in low for m in _SSH_FAILURE_MARKERS):
                return (False, _(K.err.connection_failed, detail=output.strip()[:100]), None)

            # 2) 成功关键词 / 欢迎语
            if any(m in low for m in _SSH_SUCCESS_MARKERS):
                user = self._extract_user(output)
                if user:
                    return (True, _(K.msg.auth_success, user=user), user)
                return (True, _(K.msg.connected), None)

            # 3) 未知平台文案：以退出码兜底
            if result.returncode == 0:
                return (True, _(K.msg.connected), None)
            return (False, _(K.err.connection_failed, detail=output.strip()[:100]), None)

        except subprocess.TimeoutExpired:
            return (False, _(K.err.connection_timeout), None)
        except FileNotFoundError:
            return (False, _(K.err.ssh_not_found), None)
        except Exception as e:
            return (False, f"{_(K.misc.error)}: {e!s}", None)

    def _extract_user(self, output: str) -> str | None:
        """从输出中提取认证用户名（"Hi <user>!" / "Welcome to ..., <user>"）"""
        m = self._HI_RE.search(output) or self._WELCOME_RE.search(output)
        return m.group(1) if m else None
