#!/usr/bin/env python3
"""
业务异常层次 - 统一错误协议（全局异常处理器）

设计目标（对标 Spring Boot 的 @ControllerAdvice + @ExceptionHandler）：
- 调用点只抛出**语义异常** SSHMError(code, **params)，不再手写消息 / hint 字符串；
- 错误码 → (消息 i18n key, 默认 hint i18n key, 退出码, 是否软告警) 由 ERROR_REGISTRY 集中维护；
- CLI 入口（__main__.py）统一捕获 SSHMError，经 resolve_error() 组装 ❌/⚠️ + 💡 模板后退出，
  避免裸 traceback 与"裸 ❌ 缺 hint"两类问题。

两种错误方式的分工（core 层）：
- 校验失败 / 无法继续 → 抛 SSHMError(code, **params)（CLI 统一转退出码 + 模板）
- 软错误（提示 + 命令继续/收尾）→ 沿用 manager._fail(code, **params)（置 _had_error，
  CLI 用 _fail_exit 检查退出码）。二者底层都走 resolve_error + render_business_error，
  保证渲染一致；_fail 不改为抛异常，因为部分调用点是"告警但继续"语义。
"""

from __future__ import annotations

from dataclasses import dataclass

from sshm.i18n import _

__all__ = [
    "SSHMError",
    "ValidationError",
    "ErrorSpec",
    "ERROR_REGISTRY",
    "resolve_error",
]


class SSHMError(Exception):
    """业务错误基类（CLI 层统一处理）。

    两种构造方式（兼容并存）：
    1. 语义式（推荐）：SSHMError("KEY_NOT_FOUND", label="x")
       - code: ERROR_REGISTRY 中的错误码
       - params: 消息模板所需的格式化参数（如 label/name/email）
       - 由 resolve_error() 统一组装 i18n 消息与默认 hint
    2. 文本式（遗留兼容）：SSHMError("some raw message")
       - 当 code 不在 ERROR_REGISTRY 中时，作为纯消息透传（hint 需 CLI 自行处理）

    注：项目当前所有错误实际走 manager._fail，本类暂无实例化点；引入错误码体系后，
    新代码应优先用语义式构造。
    """

    exit_code = 1

    def __init__(self, code: str, **params):
        # 文本式兼容：若 code 不是已知错误码，视为裸消息
        if code not in ERROR_REGISTRY:
            super().__init__(code)
            self.code = None
            self.params: dict = {}
            return
        spec = ERROR_REGISTRY[code]
        super().__init__(code)
        self.code = code
        self.params = params
        self.exit_code = spec.exit_code
        self.is_warn = spec.warn


class ValidationError(SSHMError, ValueError):
    """参数/标签校验失败。

    同时继承 ValueError，保持对旧调用方与既有测试（pytest.raises(ValueError)）
    的兼容。
    """

    exit_code = 2


@dataclass(frozen=True)
class ErrorSpec:
    """错误码规格：消息模板、默认 hint、退出码、软告警标记。"""

    code: str
    msg_key: str
    hint_key: str | None = None
    exit_code: int = 1
    warn: bool = False


# --------------------------------------------------------------------------
# 错误码注册表（集中维护：新增错误类型只改这里 + i18n 两个 key）
# --------------------------------------------------------------------------
ERROR_REGISTRY: dict[str, ErrorSpec] = {
    "KEY_NOT_FOUND": ErrorSpec("KEY_NOT_FOUND", "err.key_not_found", "msg.use_all_keys_tip"),
    "KEY_NOT_FOUND_SHORT": ErrorSpec("KEY_NOT_FOUND_SHORT", "err.key_not_found_short", "msg.use_all_keys_tip"),
    "AUTHOR_DUP_ID": ErrorSpec("AUTHOR_DUP_ID", "err.author_dup_identity", "err.author_dup_hint"),
    "REWRITE_USAGE": ErrorSpec("REWRITE_USAGE", "err.author_exclusive", "err.rewrite_usage_tip"),
    "NEED_OLD": ErrorSpec("NEED_OLD", "err.need_old", "err.rewrite_usage_tip"),
    "NEED_NEW": ErrorSpec("NEED_NEW", "err.need_new", "err.rewrite_usage_tip"),
    "NOT_GIT_REPO": ErrorSpec("NOT_GIT_REPO", "err.not_git_repo", None),
    "NO_KEYS": ErrorSpec("NO_KEYS", "err.no_keys", "msg.use_all_keys_tip"),
    "NO_ORIGIN_REMOTE": ErrorSpec("NO_ORIGIN_REMOTE", "msg.no_origin_remote", "msg.add_remote_first"),
    "GIT_FAILED": ErrorSpec("GIT_FAILED", "err.git_failed", None),
    "SSH_TEST_TIMEOUT": ErrorSpec("SSH_TEST_TIMEOUT", "msg.ssh_test_timed_out", None, warn=True),
    "NO_RECOVERABLE": ErrorSpec("NO_RECOVERABLE", "err.no_recoverable", None),
    "OPERATION_CANCELLED": ErrorSpec("OPERATION_CANCELLED", "err.operation_cancelled", None),
    "INVALID_BACKUP_NAME": ErrorSpec("INVALID_BACKUP_NAME", "err.invalid_backup_name", None),
    "BACKUP_NOT_FOUND_PATH": ErrorSpec("BACKUP_NOT_FOUND_PATH", "err.backup_not_found_path", "err.use_backups_cmd"),
    "RESTORE_FAILED_DETAIL": ErrorSpec("RESTORE_FAILED_DETAIL", "err.restore_failed_detail", None),
}


def resolve_error(exc: SSHMError) -> tuple[str, str | None, int, bool]:
    """按错误码组装 (msg, hint, exit_code, warn)。

    对应 Spring 的 @ExceptionHandler：从异常类型/错误码 + 参数组装响应体。
    文本式异常（code 为 None）原样返回消息，hint 留空。
    """
    if exc.code is None:
        return (str(exc), None, exc.exit_code, getattr(exc, "is_warn", False))

    spec = ERROR_REGISTRY[exc.code]
    msg = _(spec.msg_key).format(**exc.params)
    hint = _(spec.hint_key).format(**exc.params) if spec.hint_key else None
    return (msg, hint, spec.exit_code, spec.warn)
