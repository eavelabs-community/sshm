"""PR1 错误码体系（全局异常处理器）测试。

验证：
- ERROR_REGISTRY / resolve_error 能从错误码 + 参数组装 i18n 消息与默认 hint；
- SSHMError 兼容文本式构造；
- manager._fail(code, **params) 自动注入默认 hint，无需调用点硬编码 hint 字符串；
- __main__ 捕获 SSHMError 后渲染统一 ❌ + 💡 模板（堵"抛异常必裸"漏洞）。
"""

import pytest

from sshm.core.errors import (
    ERROR_REGISTRY,
    ErrCode,
    ErrorSpec,
    SSHMError,
    ValidationError,
    convert_error_code,
    register_error_code_converter,
    resolve_error,
)
from sshm.core.manager import SSHKeyManager


def test_registry_keys_exist_in_i18n():
    """注册表里引用的 msg/hint key 必须在 i18n 字典中存在，否则运行时才会炸。"""
    from sshm.i18n import _

    for code, spec in ERROR_REGISTRY.items():
        assert _(spec.msg_key), f"{code}: msg_key {spec.msg_key} 解析为空"
        if spec.hint_key:
            assert _(spec.hint_key), f"{code}: hint_key {spec.hint_key} 解析为空"


def test_resolve_error_with_params_and_default_hint():
    """语义异常 → 正确组装 msg + 默认 hint + 退出码。"""
    exc = SSHMError("KEY_NOT_FOUND", label="eavelabs")
    msg, hint, code, warn = resolve_error(exc)
    assert "eavelabs" in msg
    assert hint is not None and "key list" in hint.lower()
    assert code == 1
    assert warn is False


def test_resolve_error_warn_flag():
    """warn 规格应透传为 ⚠️ 语义。"""
    spec = ErrorSpec("X", "err.no_keys", None, exit_code=1, warn=True)
    ERROR_REGISTRY["X"] = spec
    try:
        msg, hint, code, warn = resolve_error(SSHMError("X"))
        assert warn is True
    finally:
        del ERROR_REGISTRY["X"]


def test_sshmeror_text_mode_compat():
    """文本式构造（非注册码）原样透传，hint 为空，不破坏遗留调用。"""
    exc = SSHMError("some raw message")
    assert exc.code is None
    msg, hint, code, warn = resolve_error(exc)
    assert msg == "some raw message"
    assert hint is None


def test_validation_error_is_value_error():
    """ValidationError 仍兼容 ValueError（既有测试依赖）。"""
    with pytest.raises(ValueError):
        raise ValidationError("bad")


def test_manager_fail_code_injects_default_hint(capsys):
    """_fail(code, **params) 自动注入默认 hint，无需调用点手写 hint。"""
    m = SSHKeyManager()
    m._fail("KEY_NOT_FOUND", label="eavelabs")
    out = capsys.readouterr().out
    assert "❌" in out
    assert "eavelabs" in out
    assert "key list" in out.lower()  # 来自默认 hint
    assert m._had_error is True


def test_manager_fail_raw_msg_still_works(capsys):
    """_fail(纯消息) 旧签名行为不变（兼容遗留调用）。"""
    m = SSHKeyManager()
    m._fail("plain message", hint="do something")
    out = capsys.readouterr().out
    assert "plain message" in out
    assert "do something" in out


def test_manager_fail_with_param_and_default_hint(capsys):
    """_fail 错误码带参数 + 注册表默认 hint 自动注入（KEY_NOT_FOUND_SHORT）。"""
    m = SSHKeyManager()
    m._fail("KEY_NOT_FOUND_SHORT", label="eavelabs")
    out = capsys.readouterr().out
    assert "eavelabs" in out
    assert "key list" in out.lower()  # 默认 hint 自动注入


def test_resolve_error_warn_renders_warn_flag():
    """SSH_TEST_TIMEOUT 应为软告警（warn=True）。"""
    msg, hint, code, warn = resolve_error(SSHMError("SSH_TEST_TIMEOUT"))
    assert warn is True
    assert "timed out" in msg.lower()


def test_registry_codes_resolve_without_error():
    """所有已登记错误码都能被 resolve_error 正常组装（参数齐全）。"""
    from sshm.core.errors import ERROR_REGISTRY
    from sshm.i18n import _

    print("DBG REG KEYS:", [k for k in ERROR_REGISTRY if "BACKUP" in k])

    samples = {
        "KEY_NOT_FOUND": {"label": "x"},
        "KEY_NOT_FOUND_SHORT": {"label": "x"},
        "AUTHOR_DUP_ID": {"name": "n", "email": "e", "label": "l"},
        "REWRITE_USAGE": {},
        "NEED_OLD": {},
        "NEED_NEW": {},
        "NOT_GIT_REPO": {"path": "/p"},
        "NO_KEYS": {},
        "NO_ORIGIN_REMOTE": {},
        "GIT_FAILED": {"err": "boom"},
        "SSH_TEST_TIMEOUT": {},
        "NO_RECOVERABLE": {},
        "OPERATION_CANCELLED": {},
        "INVALID_BACKUP_NAME": {"name": "x"},
        "BACKUP_NOT_FOUND_PATH": {"path": "/p"},
        "RESTORE_FAILED_DETAIL": {"name": "k", "detail": "e"},
    }
    for code, params in samples.items():
        msg, hint, c, w = resolve_error(SSHMError(code, **params))
        assert msg, f"{code} 消息为空"
        # 确认没有未填充的占位符残留
        assert "{" not in msg, f"{code} 消息仍有未填充占位符: {msg}"
        if hint:
            assert "{" not in hint, f"{code} hint 仍有未填充占位符: {hint}"


def test_enum_and_string_code_equivalence():
    """ErrCode 枚举与同名字符串应被归一化为同一 key，且都能命中注册表。"""
    from sshm.core.manager import SSHKeyManager

    e = SSHMError(ErrCode.KEY_NOT_FOUND, label="x")
    s = SSHMError("KEY_NOT_FOUND", label="x")
    assert e.code == s.code == "KEY_NOT_FOUND"
    me, ms = resolve_error(e), resolve_error(s)
    assert me[0] == ms[0] and me[3] == ms[3]

    m = SSHKeyManager()
    m._fail(ErrCode.KEY_NOT_FOUND, label="x")
    assert m._had_error is True


def test_unknown_code_type_raises_type_error():
    """未注册转换器类型应抛 TypeError，提示可扩展注册。"""
    with pytest.raises(TypeError):
        convert_error_code(12345)


def test_custom_converter_is_extensible():
    """可扩展点：注册自定义类型转换器后，convert_error_code 走新路径。"""

    class MyCode:
        def __init__(self, name: str):
            self.name = name

    register_error_code_converter(MyCode, lambda c: convert_error_code.__globals__["_CodeConversion"](c.name, c.name in ERROR_REGISTRY))
    try:
        conv = convert_error_code(MyCode("KEY_NOT_FOUND"))
        assert conv.key == "KEY_NOT_FOUND"
        assert conv.known is True
        conv2 = convert_error_code(MyCode("totally unknown"))
        assert conv2.known is False
    finally:
        # 清理，避免污染其他测试
        from sshm.core.errors import _ERROR_CODE_CONVERTERS

        _ERROR_CODE_CONVERTERS.pop(MyCode, None)
