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
from enum import Enum

from sshm.i18n import _

__all__ = [
    "ErrCode",
    "SSHMError",
    "ValidationError",
    "ErrorSpec",
    "ERROR_REGISTRY",
    "resolve_error",
]


class ErrCode(str, Enum):
    """错误码枚举（单一事实来源，配合 ERROR_REGISTRY 使用）。

    继承 str：ErrCode.NOT_GIT_REPO == "NOT_GIT_REPO" 为真，向后兼容任何
    遗留的字符串比较；同时获得 IDE 自动补全与拼写保护。

    调用点一律引用 ErrCode.XXX 而非裸字符串，避免散落硬编码写错。
    """

    # --- 通用 ---
    KEY_NOT_FOUND = "KEY_NOT_FOUND"
    KEY_NOT_FOUND_SHORT = "KEY_NOT_FOUND_SHORT"
    KEY_NOT_FOUND_FILES = "KEY_NOT_FOUND_FILES"
    KEY_NOT_FOUND_FILE = "KEY_NOT_FOUND_FILE"
    KEY_EXISTS = "KEY_EXISTS"
    KEY_MISSING = "KEY_MISSING"
    DEFAULT_KEY_MISSING = "DEFAULT_KEY_MISSING"
    NO_DEFAULT_KEY = "NO_DEFAULT_KEY"
    NO_KEYS = "NO_KEYS"
    LABEL_EMPTY = "LABEL_EMPTY"
    LABEL_INVALID = "LABEL_INVALID"
    LABEL_RESERVED = "LABEL_RESERVED"
    LABEL_RESERVED_SWITCH = "LABEL_RESERVED_SWITCH"
    LABEL_EXISTS = "LABEL_EXISTS"
    TARGET_EXISTS = "TARGET_EXISTS"
    CANNOT_RENAME_DEFAULT = "CANNOT_RENAME_DEFAULT"
    SAME_LABEL = "SAME_LABEL"
    CREATE_FAILED = "CREATE_FAILED"
    KEYGEN_TIMEOUT = "KEYGEN_TIMEOUT"
    INVALID_EMAIL = "INVALID_EMAIL"
    UNSUPPORTED_TYPE = "UNSUPPORTED_TYPE"
    # --- 仓库 / git ---
    NOT_GIT_REPO = "NOT_GIT_REPO"
    NOT_VALID_GIT = "NOT_VALID_GIT"
    RUN_IN_REPO = "RUN_IN_REPO"
    FAILED_PARSE = "FAILED_PARSE"
    GIT_FAILED = "GIT_FAILED"
    CLONE_FAILED = "CLONE_FAILED"
    NO_ORIGIN_REMOTE = "NO_ORIGIN_REMOTE"
    SSH_TEST_TIMEOUT = "SSH_TEST_TIMEOUT"
    # --- 备份 ---
    NO_BACKUPS_RESTORE = "NO_BACKUPS_RESTORE"
    USE_BACKUP_CMD = "USE_BACKUP_CMD"
    USE_BACKUPS_CMD = "USE_BACKUPS_CMD"
    INVALID_BACKUP_NAME = "INVALID_BACKUP_NAME"
    BACKUP_NOT_FOUND_PATH = "BACKUP_NOT_FOUND_PATH"
    NO_RECOVERABLE = "NO_RECOVERABLE"
    RESTORE_FAILED_DETAIL = "RESTORE_FAILED_DETAIL"
    OPERATION_CANCELLED = "OPERATION_CANCELLED"
    DELETE_DEFAULT = "DELETE_DEFAULT"
    DELETE_ALL_DEFAULT = "DELETE_ALL_DEFAULT"
    # --- 作者 ---
    NO_AUTHOR_SET = "NO_AUTHOR_SET"
    AUTHOR_EXCLUSIVE = "AUTHOR_EXCLUSIVE"
    AUTHOR_NOT_FOUND = "AUTHOR_NOT_FOUND"
    AUTHOR_DUP_ID = "AUTHOR_DUP_ID"
    USE_AUTHOR_LIST = "USE_AUTHOR_LIST"
    NO_AUTHORS = "NO_AUTHORS"
    ADD_AUTHOR_USAGE = "ADD_AUTHOR_USAGE"
    AUTHOR_EMPTY = "AUTHOR_EMPTY"
    AUTO_AUTHOR_FAILED = "AUTO_AUTHOR_FAILED"
    # --- history rewrite ---
    REWRITE_USAGE = "REWRITE_USAGE"
    NEED_OLD = "NEED_OLD"
    NEED_NEW = "NEED_NEW"
    NO_MATCHES = "NO_MATCHES"
    REWRITE_FAILED = "REWRITE_FAILED"
    # --- 连接 / 网络 ---
    CONNECTION_FAILED = "CONNECTION_FAILED"
    CONNECTION_TIMEOUT = "CONNECTION_TIMEOUT"
    SSH_NOT_FOUND = "SSH_NOT_FOUND"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    ADD_FAILED = "ADD_FAILED"
    # --- CLI ---
    NO_SUCH_COMMAND = "NO_SUCH_COMMAND"
    NO_SUCH_SUBCOMMAND = "NO_SUCH_SUBCOMMAND"


class SSHMError(Exception):
    """业务错误基类（CLI 层统一处理）。

    两种构造方式（兼容并存）：
    1. 语义式（推荐）：SSHMError(ErrCode.KEY_NOT_FOUND, label="x")
       - code: ErrCode 枚举成员（ERROR_REGISTRY 中的错误码）
       - params: 消息模板所需的格式化参数（如 label/name/email）
       - 由 resolve_error() 统一组装 i18n 消息与默认 hint
    2. 文本式（遗留兼容）：SSHMError("some raw message")
       - 当 code 不在 ERROR_REGISTRY 中时，作为纯消息透传（hint 需 CLI 自行处理）

    注：项目当前所有错误实际走 manager._fail，本类暂无实例化点；引入错误码体系后，
    新代码应优先用语义式构造。
    """

    exit_code = 1

    def __init__(self, code: "str | ErrCode", **params):
        norm = _code_key(code)
        # 文本式兼容：若 code 不是已知错误码，视为裸消息
        if norm not in ERROR_REGISTRY:
            super().__init__(norm)
            self.code = None
            self.params: dict = {}
            return
        spec = ERROR_REGISTRY[norm]
        super().__init__(norm)
        self.code = norm
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
    """错误码规格：消息模板、默认 hint、退出码、软告警标记。

    code 接收 ErrCode 枚举成员（唯一字符串定义来源）或其字符串值；
    __post_init__ 归一化为字符串，保证 str(exc) / 日志一致。
    """

    code: "str | ErrCode"
    msg_key: str
    hint_key: str | None = None
    exit_code: int = 1
    warn: bool = False

    def __post_init__(self):
        if isinstance(self.code, ErrCode):
            object.__setattr__(self, "code", self.code.value)


# --------------------------------------------------------------------------
# 错误码注册表（集中维护：新增错误类型只改这里 + i18n 两个 key）
# --------------------------------------------------------------------------
# 错误码命名规则：err.<name> -> 错误码 <NAME>（大写、去点）。
# 迁移旧式调用 self.m._fail(OLD_MSG) 时，msg 部分替换为 "X_CODE"，hint 仍可按需在调用点显式传入。
# 此处仅登记 msg_key（保证渲染入口统一）；带通用默认 hint 的显式绑定 hint_key。
ERROR_REGISTRY: dict[str, ErrorSpec] = {
    # --- 通用 ---
    "KEY_NOT_FOUND": ErrorSpec(ErrCode.KEY_NOT_FOUND, "err.key_not_found", "msg.use_all_keys_tip"),
    "KEY_NOT_FOUND_SHORT": ErrorSpec(ErrCode.KEY_NOT_FOUND_SHORT, "err.key_not_found_short", "msg.use_all_keys_tip"),
    "KEY_NOT_FOUND_FILES": ErrorSpec(ErrCode.KEY_NOT_FOUND_FILES, "err.key_not_found_files", "msg.use_all_keys_tip"),
    "KEY_NOT_FOUND_FILE": ErrorSpec(ErrCode.KEY_NOT_FOUND_FILE, "err.key_not_found_file", "msg.use_all_keys_tip"),
    "KEY_EXISTS": ErrorSpec(ErrCode.KEY_EXISTS, "err.key_exists", None),
    "KEY_MISSING": ErrorSpec(ErrCode.KEY_MISSING, "err.key_missing", None),
    "DEFAULT_KEY_MISSING": ErrorSpec(ErrCode.DEFAULT_KEY_MISSING, "err.default_key_missing", None),
    "NO_DEFAULT_KEY": ErrorSpec(ErrCode.NO_DEFAULT_KEY, "err.no_default_key", None),
    "NO_KEYS": ErrorSpec(ErrCode.NO_KEYS, "err.no_keys", "msg.use_all_keys_tip"),
    "LABEL_EMPTY": ErrorSpec(ErrCode.LABEL_EMPTY, "err.label_empty", None),
    "LABEL_INVALID": ErrorSpec(ErrCode.LABEL_INVALID, "err.label_invalid", None),
    "LABEL_RESERVED": ErrorSpec(ErrCode.LABEL_RESERVED, "err.label_reserved", None),
    "LABEL_RESERVED_SWITCH": ErrorSpec(ErrCode.LABEL_RESERVED_SWITCH, "err.label_reserved_switch", None),
    "LABEL_EXISTS": ErrorSpec(ErrCode.LABEL_EXISTS, "err.label_exists", None),
    "TARGET_EXISTS": ErrorSpec(ErrCode.TARGET_EXISTS, "err.target_exists", None, warn=True),
    "CANNOT_RENAME_DEFAULT": ErrorSpec(ErrCode.CANNOT_RENAME_DEFAULT, "err.cannot_rename_default", None),
    "SAME_LABEL": ErrorSpec(ErrCode.SAME_LABEL, "err.same_label", None, warn=True),
    "CREATE_FAILED": ErrorSpec(ErrCode.CREATE_FAILED, "err.create_failed", None),
    "KEYGEN_TIMEOUT": ErrorSpec(ErrCode.KEYGEN_TIMEOUT, "err.keygen_timeout", None),
    "INVALID_EMAIL": ErrorSpec(ErrCode.INVALID_EMAIL, "err.invalid_email", None),
    "UNSUPPORTED_TYPE": ErrorSpec(ErrCode.UNSUPPORTED_TYPE, "err.unsupported_type", None),
    # --- 仓库 / git ---
    "NOT_GIT_REPO": ErrorSpec(ErrCode.NOT_GIT_REPO, "err.not_git_repo", "err.run_in_repo"),
    "NOT_VALID_GIT": ErrorSpec(ErrCode.NOT_VALID_GIT, "err.not_valid_git", None),
    "RUN_IN_REPO": ErrorSpec(ErrCode.RUN_IN_REPO, "err.run_in_repo", None),
    "FAILED_PARSE": ErrorSpec(ErrCode.FAILED_PARSE, "err.failed_parse", None),
    "GIT_FAILED": ErrorSpec(ErrCode.GIT_FAILED, "err.git_failed", None),
    "CLONE_FAILED": ErrorSpec(ErrCode.CLONE_FAILED, "err.clone_failed", None),
    "NO_ORIGIN_REMOTE": ErrorSpec(ErrCode.NO_ORIGIN_REMOTE, "msg.no_origin_remote", "msg.add_remote_first"),
    "SSH_TEST_TIMEOUT": ErrorSpec(ErrCode.SSH_TEST_TIMEOUT, "msg.ssh_test_timed_out", None, warn=True),
    # --- 备份 ---
    "NO_BACKUPS_RESTORE": ErrorSpec(ErrCode.NO_BACKUPS_RESTORE, "err.no_backups_restore", None),
    "USE_BACKUP_CMD": ErrorSpec(ErrCode.USE_BACKUP_CMD, "err.use_backup_cmd", None),
    "USE_BACKUPS_CMD": ErrorSpec(ErrCode.USE_BACKUPS_CMD, "err.use_backups_cmd", None),
    "INVALID_BACKUP_NAME": ErrorSpec(ErrCode.INVALID_BACKUP_NAME, "err.invalid_backup_name", None),
    "BACKUP_NOT_FOUND_PATH": ErrorSpec(ErrCode.BACKUP_NOT_FOUND_PATH, "err.backup_not_found_path", "err.use_backups_cmd"),
    "NO_RECOVERABLE": ErrorSpec(ErrCode.NO_RECOVERABLE, "err.no_recoverable", None),
    "RESTORE_FAILED_DETAIL": ErrorSpec(ErrCode.RESTORE_FAILED_DETAIL, "err.restore_failed_detail", None),
    "OPERATION_CANCELLED": ErrorSpec(ErrCode.OPERATION_CANCELLED, "err.operation_cancelled", None),
    "DELETE_DEFAULT": ErrorSpec(ErrCode.DELETE_DEFAULT, "err.delete_default", None),
    "DELETE_ALL_DEFAULT": ErrorSpec(ErrCode.DELETE_ALL_DEFAULT, "err.delete_all_default", None),
    # --- 作者 ---
    "NO_AUTHOR_SET": ErrorSpec(ErrCode.NO_AUTHOR_SET, "err.no_author_set", None),
    "AUTHOR_EXCLUSIVE": ErrorSpec(ErrCode.AUTHOR_EXCLUSIVE, "err.author_exclusive", "err.rewrite_usage_tip"),
    "AUTHOR_NOT_FOUND": ErrorSpec(ErrCode.AUTHOR_NOT_FOUND, "err.author_not_found", None),
    "AUTHOR_DUP_ID": ErrorSpec(ErrCode.AUTHOR_DUP_ID, "err.author_dup_identity", "err.author_dup_hint"),
    "USE_AUTHOR_LIST": ErrorSpec(ErrCode.USE_AUTHOR_LIST, "err.use_author_list", None),
    "NO_AUTHORS": ErrorSpec(ErrCode.NO_AUTHORS, "err.no_authors", None),
    "ADD_AUTHOR_USAGE": ErrorSpec(ErrCode.ADD_AUTHOR_USAGE, "err.add_author_usage", None),
    "AUTHOR_EMPTY": ErrorSpec(ErrCode.AUTHOR_EMPTY, "err.author_empty", None),
    "AUTO_AUTHOR_FAILED": ErrorSpec(ErrCode.AUTO_AUTHOR_FAILED, "err.auto_author_failed", None),
    # --- history rewrite ---
    "REWRITE_USAGE": ErrorSpec(ErrCode.REWRITE_USAGE, "err.author_exclusive", "err.rewrite_usage_tip"),
    "NEED_OLD": ErrorSpec(ErrCode.NEED_OLD, "err.need_old", "err.rewrite_usage_tip"),
    "NEED_NEW": ErrorSpec(ErrCode.NEED_NEW, "err.need_new", "err.rewrite_usage_tip"),
    "NO_MATCHES": ErrorSpec(ErrCode.NO_MATCHES, "err.no_matches", None, warn=True),
    "REWRITE_FAILED": ErrorSpec(ErrCode.REWRITE_FAILED, "err.rewrite_failed", None),
    # --- 连接 / 网络 ---
    "CONNECTION_FAILED": ErrorSpec(ErrCode.CONNECTION_FAILED, "err.connection_failed", None),
    "CONNECTION_TIMEOUT": ErrorSpec(ErrCode.CONNECTION_TIMEOUT, "err.connection_timeout", None, warn=True),
    "SSH_NOT_FOUND": ErrorSpec(ErrCode.SSH_NOT_FOUND, "err.ssh_not_found", None),
    "PERMISSION_DENIED": ErrorSpec(ErrCode.PERMISSION_DENIED, "err.permission_denied", None),
    "ADD_FAILED": ErrorSpec(ErrCode.ADD_FAILED, "err.add_failed", None),
    # --- CLI ---
    "NO_SUCH_COMMAND": ErrorSpec(ErrCode.NO_SUCH_COMMAND, "err.no_such_command", None),
    "NO_SUCH_SUBCOMMAND": ErrorSpec(ErrCode.NO_SUCH_SUBCOMMAND, "err.no_such_subcommand", None),
}


def _validate_registry() -> None:
    """保证 ErrCode 与 ERROR_REGISTRY 一一对应（单一事实来源约束）。

    任一侧新增/删除/改名未同步都会在此抛错，CI 与启动即可发现。
    """
    code_names = {c.value for c in ErrCode}
    reg_names = set(ERROR_REGISTRY)
    missing = code_names - reg_names
    extra = reg_names - code_names
    assert not missing, f"ErrCode 有但未登记到 ERROR_REGISTRY: {sorted(missing)}"
    assert not extra, f"ERROR_REGISTRY 有但 ErrCode 未定义: {sorted(extra)}"
    for code, spec in ERROR_REGISTRY.items():
        assert spec.code == code, f"注册表 {code} 的 ErrorSpec.code 不一致: {spec.code}"


_validate_registry()


def _code_key(code: "str | ErrCode") -> str:
    """归一化错误码：枚举转其字符串值，字符串原样返回。"""
    return code.value if isinstance(code, ErrCode) else code


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
