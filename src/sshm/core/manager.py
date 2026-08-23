#!/usr/bin/env python3
"""
SSH 密钥管理器 - 门面（Facade）

只负责组合底层服务与命令编排组，并把公开 API 委托出去，自身不做业务逻辑。
- 服务层：KeyStore / SSHTester / GitRepoService / BackupService / AuthorService
- 命令编排层（core/commands/）：KeyCommands / RepoCommands / AuthorCommands /
  SystemCommands（按指令分包，每模块单一职责）
- 状态：_had_error（软错误标志）与 _fail（软错误上报）
"""

from pathlib import Path

from sshm.i18n import _

from ..constants import (
    BACKUP_DIR_NAME,
    DEFAULT_SSH_DIR,
    SSH_CONFIG_NAME,
    STATE_FILE_NAME,
)
from ..ui.output import ICON_ERR, ICON_WARN
from ..ui.tip import render_business_error
from .commands import (
    AuthorCommands,
    ConfigCommands,
    HistoryCommands,
    KeyCommands,
    RepoCommands,
    SystemCommands,
)
from .services.git.author import AuthorService
from .services.git.gitrepo import GitRepoService
from .services.net.sshtest import SSHTester
from .services.ssh.config import SSHConfigManager
from .services.ssh.keystore import KeyStore
from .services.storage.backup import BackupService
from .services.storage.state import StateManager


class SSHKeyManager:
    """SSH 密钥管理器 - 门面，组合服务与命令编排，公开 API 委托。"""

    # 保留标签：original 为 use -g 切换时的系统备份，default 为默认密钥
    RESERVED_LABELS = ("default", "original")

    def __init__(self, ssh_dir: Path | None = None):
        """初始化管理器

        Args:
            ssh_dir: SSH 目录路径，默认为 ~/.ssh
        """
        self.ssh_dir = ssh_dir or DEFAULT_SSH_DIR
        self.backup_dir = self.ssh_dir / BACKUP_DIR_NAME
        self.config_file = self.ssh_dir / SSH_CONFIG_NAME
        self.state_file = self.ssh_dir / STATE_FILE_NAME

        # 初始化子管理器
        self.config_manager = SSHConfigManager(self.config_file)
        self.state_manager = StateManager(self.state_file)

        # 应用输出语言（环境变量优先于状态文件）
        from ..i18n import load_from_state

        load_from_state(self.state_manager.read_lang())

        # 本次命令是否发生业务失败（供 CLI 层决定退出码）
        self._had_error = False

        # 组合服务（门面委托给聚焦服务）
        self.keystore = KeyStore(self.ssh_dir)
        self.gitrepo = GitRepoService(
            self.ssh_dir,
            self.config_manager,
            self.state_manager,
            self.keystore,
            self._fail,
        )
        self.backup = BackupService(self.ssh_dir, self.backup_dir, self.state_file, self.config_file, self._fail)
        self.tester = SSHTester()
        self.author_service = AuthorService(self.state_manager, self.keystore, self.gitrepo, self._fail)

        # 命令编排组
        # - 业务组（与 CLI 分组一一对应）：key/repo/backup/author/history/config
        # - system 组承载系统级命令（语言/更新/重新安装），单独命名避免与
        #   config（系统配置：语言、自动作者）语义混淆
        self.key = KeyCommands(self)
        self.repo = RepoCommands(self)
        self.author = AuthorCommands(self)
        self.history = HistoryCommands(self)
        self.config = ConfigCommands(self)
        self.system = SystemCommands(self)
        # CLI 顶层命令组为 `version`（version update/reinstall），与
        # system 组（更新/重装/PATH）承载同一编排逻辑，此处暴露别名以
        # 满足「CLI 分组名 = manager 属性」的一致性契约。
        self.version = self.system

        # 确保必要目录存在
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """确保必要的目录存在（委托 KeyStore，另确保备份目录）"""
        self.keystore.ensure_directories()
        self.backup_dir.mkdir(mode=0o700, exist_ok=True)

    def _fail(self, msg_or_code, *, icon: str = ICON_ERR, hint: str | None = None, **params):
        """记录业务失败并渲染统一错误（不抛异常，保持原有控制流）。

        支持两种调用形式（与 SSHMError 对齐，逐步迁移到错误码）：
        1. 错误码：_fail(ErrCode.KEY_NOT_FOUND, label="x")
           - 从 ERROR_REGISTRY 解析 msg_key + 默认 hint_key，自动 i18n + 格式化；
           - 默认 hint 自动注入，调用点无需手写 hint 字符串。
        2. 纯消息（遗留兼容）：_fail("some message", hint=...)
           - 直接走 render_business_error，行为与旧版一致。

        Args:
            msg_or_code: 错误消息（不含图标前缀）、ErrCode 枚举成员，
                或 ERROR_REGISTRY 中的错误码字符串。
            icon: 状态图标，默认 ❌（硬错误）；软告警传 ⚠️。错误码形式为 False 时忽略。
            hint: 可选建议行，覆盖错误码默认值。
            **params: 错误码消息模板所需的格式化参数。
        """
        from .errors import ERROR_REGISTRY, convert_error_code

        conv = convert_error_code(msg_or_code)
        if conv.known:
            spec = ERROR_REGISTRY[conv.key]
            msg = _(spec.msg_key).format(**params)
            hint = hint or (_(spec.hint_key).format(**params) if spec.hint_key else None)
            icon = ICON_WARN if spec.warn else ICON_ERR
        else:
            msg = conv.key  # 兼容纯消息（文本式透传）

        self._had_error = True
        render_business_error(msg, icon=icon, hint=hint)

    def _warn(self, msg: str, *, hint: str | None = None) -> None:
        """渲染统一软告警（⚠️ + 可选 💡 建议）。

        与 `_fail` 的区别：**不置 `_had_error`**，命令仍按成功退出。
        用于"提示但命令正常完成"的告警场景，避免误报非零退出码。
        """
        render_business_error(msg, icon=ICON_WARN, hint=hint)

    def _mark_error(self) -> None:
        """仅标记业务失败（不打印）。

        用于"已打印过详细错误提示、仅需置位退出码"的场景，避免与 `_fail`
        重复输出。命令层不应直接改 `_had_error`，统一走本方法或 `_fail`。
        """
        self._had_error = True
