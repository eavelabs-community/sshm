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
    ErrorSpec,
    SSHMError,
    ValidationError,
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
