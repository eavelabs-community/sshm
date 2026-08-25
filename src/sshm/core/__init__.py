"""SSHKeyManager core 业务逻辑层。

包含：
- errors：统一业务异常体系（SSHMError / 错误码注册表）
- manager：SSHKeyManager 门面类
- services.ssh.config：SSHConfigManager
- services.storage.state：StateManager
- utils：工具函数（parse、cache、git 等）
"""
from __future__ import annotations

# 显式导出 errors 模块，避免依赖隐式导入（Python 动态路径解析不稳定且 IDE 无法静态验证）
from .errors import (  # noqa: F401
    ERROR_REGISTRY,
    ErrCode,
    ErrorSpec,
    SSHMError,
    ValidationError,
    convert_error_code,
    register_error_code_converter,
    resolve_error,
)
from .manager import SSHKeyManager  # noqa: F401

# 显式导出常用服务类
from .services.ssh.config import SSHConfigManager  # noqa: F401
from .services.storage.state import StateManager  # noqa: F401

__all__ = [
    "SSHMError",
    "ValidationError",
    "ErrCode",
    "ErrorSpec",
    "ERROR_REGISTRY",
    "convert_error_code",
    "register_error_code_converter",
    "resolve_error",
    "SSHKeyManager",
    "SSHConfigManager",
    "StateManager",
]
