#!/usr/bin/env python3
"""
Typer CLI 应用 - sshm 命令行入口

基于 Typer 框架声明式定义命令，自动生成帮助/参数校验/补全。
命令按关注点分为 6 组（key/repo/backup/author/history/config），分组结构与
同组关联由 `cli/registry.py` 注册表单一事实来源驱动；各命令执行末尾自动
输出"本组相关命令" tip（从注册表推导，不手写硬编码）。

命令函数体委托业务逻辑给 SSHKeyManager。
"""

import platform
import sys
from enum import Enum
from pathlib import Path

import click
import typer

from ..constants import SUPPORTED_KEY_TYPES
from ..core import SSHKeyManager
from ..core.utils.parse import split_pair
from ..i18n import _, get_lang, language_display_name
from ..language import LANGUAGES, K
from ..ui.console import format_timestamp
from ..ui.output import print
from . import registry as _registry
from .registry import GROUP_ORDER, related_commands
from ..core.errors import ErrCode


class KeyType(str, Enum):
    """SSH 密钥类型（与 constants.SUPPORTED_KEY_TYPES 保持一致）。"""

    ed25519 = "ed25519"
    rsa = "rsa"
    ecdsa = "ecdsa"
    dsa = "dsa"


class Lang(str, Enum):
    """输出语言（与 language.LANGUAGES 保持一致）。"""

    en = "en"
    zh = "zh"


# 防御性校验：枚举成员与单一来源常量一致，避免未来 drift
assert {m.value for m in KeyType} == set(SUPPORTED_KEY_TYPES), "KeyType 与 SUPPORTED_KEY_TYPES 不一致"
assert {m.value for m in Lang} == set(LANGUAGES), "Lang 与 LANGUAGES 不一致"


class OnOff(str, Enum):
    """开关参数（on/off）。"""

    on = "on"
    off = "off"


# ===========================================================================
# 顶层应用
# ===========================================================================

app = typer.Typer(
    name="sshm",
    help=_(K.cmd.app_help),
    add_completion=True,
    no_args_is_help=True,
    rich_markup_mode="rich",
    # 允许 -h 作为 --help 的简写
    context_settings={"help_option_names": ["-h", "--help"]},
)


# ===========================================================================
# 通用辅助
# ===========================================================================


def _manager() -> SSHKeyManager:
    return SSHKeyManager()


def _fail_exit(manager: SSHKeyManager) -> None:
    """业务层报错时以非零码退出。

    用 SystemExit 而非 typer.Exit：在 `app(standalone_mode=False)` 下 typer.Exit 会被
    Click 内部吞掉导致错误场景退出码仍为 0，SystemExit 能正确传播并置退出码 1。
    """
    if getattr(manager, "_had_error", False):
        raise SystemExit(1)


def _show_tip(group: str | None = None, name: str | None = None) -> None:
    """输出"本组相关命令" tip（从注册表推导，dim 淡色突出主次）。

    Args:
        group: 可选。显式指定分组。命令函数内无需传（自动从 `_cmd`
            装饰器记录的 `__sshm_command__` 反查）；仅 callback（如
            backup_default）因无 `__sshm_command__` 需显式传入 group+name。
        name: 可选。显式指定命令名。与 group 必须成对传；命令名跨分组
            可能重名（如 key/backup/author 都有 list），**禁止只传 name**
            由本函数反查分组（有歧义），必须同时传 group。
    """
    from ..ui.tip import related_command_blocks, render_tip_block

    if group is not None and name is not None:
        cmd_group: str = group
        current: str = name
    else:
        frame = sys._getframe(1)
        fn = frame.f_globals.get(frame.f_code.co_name)
        cmd = getattr(fn, "__sshm_command__", None)
        if not cmd:
            return
        cmd_group, current = cmd
    cmds = related_commands(cmd_group, current)
    if not cmds:
        return
    for block in related_command_blocks(cmd_group, cmds):
        render_tip_block(block, style="dim")


def _cmd(app: typer.Typer, group: str, name: str):
    """按注册表驱动注册 Typer 命令。

    从 registry.GROUPS 取该命令的 help_key（单一事实来源），避免在装饰器里
    重复写 `K.cmd.xxx`；并把 (group, name) 记录到函数 `__sshm_command__`，
    供 `_show_tip()` 自动反查，消除 `_show_tip("key", "list")` 的手写重复。

    Args:
        app: 所属分组的 Typer 子应用（如 key_app）
        group: 分组名（'key' / 'repo' / ...）
        name: 命令名（与 registry GROUPS 中一致）
    """
    meta = next(m for m in _registry.GROUPS.get(group, []) if m.name == name)

    def deco(fn):
        fn.__sshm_command__ = (group, name)
        app.command(name, help=_(meta.help_key))(fn)
        return fn

    return deco


def _print_version_rows(rows) -> None:
    """以对齐表格渲染版本信息（en/zh、管道/终端均一致）。

    不采用 rich Table：rich 的 cell_len 会把带变体选择符的 emoji（🖥️/⚙️）
    判为单宽，而项目统一按 wcwidth 判为双宽，两套测量不一致会导致标签列参差。
    这里改用项目统一的 wcwidth 测量（get_display_width / pad_cell）手动对齐。
    """
    from ..ui.console import get_display_width, pad_cell
    from ..ui.output import print as _print

    label_hdr = _(K.ver.label)
    labels = [label_hdr] + [r[1] for r in rows]
    label_w = max(get_display_width(l) for l in labels)
    lead = " " * 2  # 行首缩进
    emoji_cell = " " * 4  # emoji(双宽) + 2 空格的固定位
    gap = " " * 2  # 标签列与值列之间
    _print(f"{lead}{emoji_cell}{pad_cell(label_hdr, label_w)}{gap}{_(K.ver.value)}")
    for emoji, label, value in rows:
        _print(f"{lead}{emoji}  {pad_cell(label, label_w)}{gap}{value}")


def _print_version_details() -> None:
    """渲染详细的版本与环境信息（sshm --version 与 sshm version 共用）。"""
    frozen = getattr(sys, "frozen", False)
    mode = _(K.ver.mode_packaged) if frozen else _(K.ver.mode_source)
    system = platform.system()
    arch = platform.machine()
    python_ver = platform.python_version()
    from ..constants import VERSION

    rows = [
        ["📦", _(K.ver.version), f"v{VERSION}"],
        ["🖥️", _(K.ver.platform), f"{system} {arch}"],
        ["🐍", _(K.ver.python), python_ver],
        ["⚙️", _(K.ver.mode), mode],
    ]
    if frozen:
        rows.append(["🏷️", _(K.ver.build), _build_source()])
        btime = _build_time()
        if btime:
            rows.append(["🕐", _(K.ver.build_time), btime])
    _print_version_rows(rows)


def _version_callback(value: bool) -> None:
    if value:
        _print_version_details()
        raise typer.Exit()


def _build_source() -> str:
    """判断当前 exe 是本地编译版还是线上（发布）版。"""
    exe_dir = Path(sys.executable).parent
    if (exe_dir / ".source_local").exists():
        return _(K.ver.build_local)
    if (exe_dir / ".source_release").exists():
        return _(K.ver.build_release)
    return _(K.ver.build_unknown)


def _build_time() -> str:
    """返回 exe 的构建时间（exe 文件修改时间戳）。"""
    try:
        import os
        import datetime

        ts = datetime.datetime.fromtimestamp(os.path.getmtime(sys.executable), tz=datetime.timezone.utc)
        return format_timestamp(ts)
    except Exception:
        return ""


# ===========================================================================
# key 组 - 密钥管理
# ===========================================================================

key_app = typer.Typer(
    name="key",
    help=_(K.cmd.group_key),
    rich_markup_mode="rich",
)


@key_app.callback(invoke_without_command=True)
def key_default(
    ctx: typer.Context,
    path: Path = typer.Option(Path("."), "--path", "-p", help=_(K.opt.path)),
) -> None:
    """未指定子命令时，默认显示当前正在使用的密钥（仓库级 > 全局默认）。"""
    if ctx.invoked_subcommand is None:
        manager = _manager()
        manager.key.current(path)
        _fail_exit(manager)


@_cmd(key_app, "key", "list")
def key_list(
    all: bool = typer.Option(False, "--all", "-a", help=_(K.opt.all)),
    current: bool = typer.Option(False, "--current", "-c", help=_(K.opt.current)),
    path: Path = typer.Option(Path("."), "--path", "-p", help=_(K.opt.path_with_c)),
):
    manager = _manager()
    manager.key.list(show_content=all, repo_path=path, current_only=current)
    _fail_exit(manager)
    _show_tip()


@_cmd(key_app, "key", "create")
def key_create(
    label: str = typer.Argument(..., help=_(K.opt.label)),
    email: str = typer.Argument(..., help=_(K.opt.email)),
    type: KeyType = typer.Option(KeyType.ed25519, "--type", "-t", help=_(K.opt.type)),
    host: str = typer.Option(None, "--host", "-H", help=_(K.opt.host)),
    name: str = typer.Option(None, "--name", "-n", help=_(K.opt.name)),
):
    manager = _manager()
    manager.key.create(label, email, type.value, host, name)
    _fail_exit(manager)
    _show_tip()


@_cmd(key_app, "key", "remove")
def key_remove(
    label: str = typer.Argument(..., help=_(K.opt.label)),
    type: KeyType | None = typer.Option(None, "--type", "-t", help=_(K.opt.type_all)),
):
    manager = _manager()
    manager.key.remove(label, type.value if type else None)
    _fail_exit(manager)
    _show_tip()


@_cmd(key_app, "key", "rename")
def key_rename(
    old_label: str = typer.Argument(..., help=_(K.opt.old_label)),
    new_label: str = typer.Argument(..., help=_(K.opt.new_label_name)),
    type: KeyType = typer.Option(KeyType.ed25519, "--type", "-t", help=_(K.opt.type)),
):
    manager = _manager()
    manager.key.rename(old_label, new_label, type.value)
    _fail_exit(manager)
    _show_tip()


@_cmd(key_app, "key", "label")
def key_label(
    label: str = typer.Argument(..., help=_(K.opt.new_label)),
    type: KeyType | None = typer.Option(None, "--type", "-t", help=_(K.opt.type_auto)),
    switch: bool = typer.Option(False, "--switch", "-s", help=_(K.opt.switch_after)),
):
    manager = _manager()
    manager.key.label(type.value if type else None, label, switch)
    _fail_exit(manager)
    _show_tip()


@_cmd(key_app, "key", "switch")
def key_switch(
    label: str = typer.Argument(..., help=_(K.opt.label)),
    type: KeyType | None = typer.Option(None, "--type", "-t", help=_(K.opt.type_auto)),
):
    manager = _manager()
    manager.key.switch(label, type.value if type else None)
    _fail_exit(manager)
    _show_tip()


@_cmd(key_app, "key", "current")
def key_current(
    path: Path = typer.Option(Path("."), "--path", "-p", help=_(K.opt.path)),
):
    manager = _manager()
    manager.key.current(path)
    _fail_exit(manager)
    _show_tip()


# ===========================================================================
# repo 组 - 仓库密钥绑定
# ===========================================================================

repo_app = typer.Typer(
    name="repo",
    help=_(K.cmd.group_repo),
    rich_markup_mode="rich",
)


@repo_app.callback(invoke_without_command=True)
def repo_default(
    ctx: typer.Context,
    path: Path = typer.Option(Path("."), "--path", "-p", help=_(K.opt.path)),
) -> None:
    """未指定子命令时，默认显示当前仓库配置。"""
    if ctx.invoked_subcommand is None:
        manager = _manager()
        manager.repo.info(path)
        _fail_exit(manager)


@_cmd(repo_app, "repo", "use")
def repo_use(
    label: str = typer.Argument(..., help=_(K.opt.label)),
    path: Path = typer.Option(Path("."), "--path", "-p", help=_(K.opt.path)),
    global_: bool = typer.Option(False, "--global", "-g", help=_("opt.global")),
    yes: bool = typer.Option(False, "--yes", "-y", help=_(K.opt.yes)),
    author: bool = typer.Option(False, "--author", "-a", help=_(K.opt.author_same)),
):
    manager = _manager()
    if global_:
        manager.key.switch(label)
        if author:
            print()
            manager.author.use(label, path, scope="global", skip_confirm=yes)
    else:
        manager.repo.use(label, path, yes)
        if author:
            print()
            manager.author.use(label, path, skip_confirm=yes)
    _fail_exit(manager)
    _show_tip()


@_cmd(repo_app, "repo", "clone")
def repo_clone(
    label: str = typer.Argument(..., help=_(K.opt.clone_label)),
    url: str = typer.Argument(..., help=_(K.opt.url)),
    target: str = typer.Argument(None, help=_(K.opt.target)),
    yes: bool = typer.Option(False, "--yes", "-y", help=_(K.opt.yes)),
):
    manager = _manager()
    manager.repo.clone(label, url, target, yes)
    _fail_exit(manager)
    _show_tip()


@_cmd(repo_app, "repo", "info")
def repo_info(
    path: Path = typer.Option(Path("."), "--path", "-p", help=_(K.opt.path)),
):
    manager = _manager()
    manager.repo.info(path)
    _fail_exit(manager)
    _show_tip()


@_cmd(repo_app, "repo", "test")
def repo_test(
    label: str = typer.Argument(None, help=_(K.opt.test_label)),
    path: Path = typer.Option(Path("."), "--path", "-p", help=_(K.opt.path)),
    all: bool = typer.Option(False, "--all", "-a", help=_(K.opt.test_all)),
):
    manager = _manager()
    manager.repo.test(label, all, path)
    _fail_exit(manager)
    _show_tip()


# ===========================================================================
# backup 组 - 备份恢复
# ===========================================================================

backup_app = typer.Typer(
    name="backup",
    help=_(K.cmd.group_backup),
    rich_markup_mode="rich",
)


@backup_app.callback(invoke_without_command=True)
def backup_default(
    ctx: typer.Context,
) -> None:
    """未指定子命令时，默认列出备份归档。"""
    if ctx.invoked_subcommand is None:
        manager = _manager()
        manager.backup.list()
        _fail_exit(manager)
        _show_tip("backup", "list")


@_cmd(backup_app, "backup", "create")
def backup_create() -> None:
    manager = _manager()
    manager.backup.create()
    _fail_exit(manager)
    _show_tip()


@_cmd(backup_app, "backup", "list")
def backup_list() -> None:
    manager = _manager()
    manager.backup.list()
    _fail_exit(manager)
    _show_tip()


@_cmd(backup_app, "backup", "restore")
def backup_restore(
    backup: str = typer.Argument(None, help=_(K.opt.backup_name)),
    type: KeyType | None = typer.Option(None, "--type", "-t", help=_(K.opt.type_only)),
    yes: bool = typer.Option(False, "--yes", "-y", help=_(K.opt.yes_prompts)),
):
    manager = _manager()
    manager.backup.restore(backup, type.value if type else None, yes)
    _fail_exit(manager)
    _show_tip()


# ===========================================================================
# author 组 - 作者管理
# ===========================================================================

author_app = typer.Typer(
    name="author",
    help=_(K.cmd.group_author),
    rich_markup_mode="rich",
)


@author_app.callback(invoke_without_command=True)
def author_default(
    ctx: typer.Context,
    path: Path = typer.Option(Path("."), "--path", "-p", help=_(K.opt.path)),
) -> None:
    """未指定子命令时，默认显示当前仓库的 git 作者配置。"""
    if ctx.invoked_subcommand is None:
        manager = _manager()
        manager.author.show(path)
        _fail_exit(manager)


@_cmd(author_app, "author", "list")
def author_list() -> None:
    manager = _manager()
    manager.author.list()
    _fail_exit(manager)
    _show_tip()


@_cmd(author_app, "author", "add")
def author_add(
    label: str = typer.Argument(..., help=_(K.opt.author_label)),
    name: str = typer.Option(None, "--name", "-n", help=_(K.opt.author_name)),
    email: str = typer.Option(None, "--email", "-e", help=_(K.opt.author_email)),
):
    manager = _manager()
    manager.author.add(label, name, email)
    _fail_exit(manager)
    _show_tip()


@_cmd(author_app, "author", "update")
def author_update(
    label: str = typer.Argument(..., help=_(K.opt.author_label)),
    name: str = typer.Option(None, "--name", "-n", help=_(K.opt.author_name)),
    email: str = typer.Option(None, "--email", "-e", help=_(K.opt.author_email_update)),
):
    # 至少提供 --name 或 --email 之一：纯参数校验，前置以渲染统一 tip 模板 + 非零退出
    if not name and not email:
        raise click.UsageError(_(K.msg.update_author_need))
    manager = _manager()
    manager.author.update(label, name, email)
    _fail_exit(manager)
    _show_tip()


@_cmd(author_app, "author", "remove")
def author_remove(
    label: str = typer.Argument(..., help=_(K.opt.author_label)),
    yes: bool = typer.Option(False, "--yes", "-y", help=_(K.opt.yes)),
):
    manager = _manager()
    manager.author.remove(label, yes)
    _fail_exit(manager)
    _show_tip()


@_cmd(author_app, "author", "use")
def author_use(
    label: str = typer.Argument(..., help=_(K.opt.author_label)),
    path: Path = typer.Option(Path("."), "--path", "-p", help=_(K.opt.path)),
    name: str = typer.Option(None, "--name", "-n", help=_(K.opt.override_name)),
    email: str = typer.Option(None, "--email", "-e", help=_(K.opt.override_email)),
    global_: bool = typer.Option(False, "--global", "-g", help=_(K.opt.global_author)),
    yes: bool = typer.Option(False, "--yes", "-y", help=_(K.opt.yes)),
):
    manager = _manager()
    scope = "global" if global_ else "local"
    manager.author.use(label, path, name, email, scope, yes)
    _fail_exit(manager)
    _show_tip()


@_cmd(author_app, "author", "unset")
def author_unset(
    path: Path = typer.Option(Path("."), "--path", "-p", help=_(K.opt.path)),
    global_: bool = typer.Option(False, "--global", "-g", help=_(K.opt.clear_global)),
):
    manager = _manager()
    scope = "global" if global_ else "local"
    manager.author.unset(path, scope)
    _fail_exit(manager)
    _show_tip()


# ===========================================================================
# history 组 - 历史重写
# ===========================================================================

history_app = typer.Typer(
    name="history",
    help=_(K.cmd.group_history),
    rich_markup_mode="rich",
)


@history_app.callback(invoke_without_command=True)
def history_default(ctx: typer.Context) -> None:
    """无子命令时显示帮助（退出码 0，区别于 no_args_is_help 的 exit 2）。"""
    if ctx.invoked_subcommand is None:
        import click

        click.echo(ctx.get_help())
        raise typer.Exit(0)


@_cmd(history_app, "history", "rewrite")
def history_rewrite(
    path: Path = typer.Option(Path("."), "--path", "-p", help=_(K.opt.path)),
    name: str = typer.Option(None, "--name", "-n", help=_(K.opt.name_arg)),
    email: str = typer.Option(None, "--email", "-e", help=_(K.opt.email_arg)),
    author: str = typer.Option(None, "--author", "-a", help=_(K.opt.author)),
    yes: bool = typer.Option(False, "--yes", "-y", help=_(K.opt.yes)),
):
    # —— 用法/参数校验（判定与 manager 层一致，前置到 CLI 层）——
    # 失败时经 manager._fail 渲染统一 ❌ + 💡 引导模板，再用 SystemExit(1) 退出，
    # 取代 click.UsageError（其默认渲染无 hint，会产生裸 ❌）。
    manager = _manager()

    old_name, new_name = split_pair(name)
    old_email, new_email = split_pair(email)
    precise = bool(old_name or old_email)
    full_name = bool(new_name and not old_name)
    full_email = bool(new_email and not old_email)
    full_author = bool(author)
    if precise and (full_author or full_name or full_email):
        manager._fail(ErrCode.REWRITE_USAGE)
        raise SystemExit(1)
    if full_author and (full_name or full_email):
        manager._fail(ErrCode.REWRITE_USAGE)
        raise SystemExit(1)
    if not (full_author or full_name or full_email):
        if not old_name and not old_email:
            manager._fail(ErrCode.NEED_OLD)
            raise SystemExit(1)
        if not new_name and not new_email:
            manager._fail(ErrCode.NEED_NEW)
            raise SystemExit(1)
    # —— 结束参数校验 ——
    manager.history.rewrite(path, name, email, author, yes)
    _fail_exit(manager)
    _show_tip()


# ===========================================================================
# config 组 - 系统配置（语言 / 自动作者联动 / 配置总览）
# 注：软件更新与重新安装不在此组，见下方 version 组（self-update 语义归属版本管理）
# ===========================================================================

config_app = typer.Typer(
    name="config",
    help=_(K.cmd.group_config),
    rich_markup_mode="rich",
)


@config_app.callback(invoke_without_command=True)
def config_default(
    ctx: typer.Context,
) -> None:
    """未指定子命令时，默认显示当前系统配置总览。"""
    if ctx.invoked_subcommand is None:
        manager = _manager()
        manager.config.show()
        _fail_exit(manager)


@_cmd(config_app, "config", "auto-author")
def config_auto_author(
    on: OnOff | None = typer.Argument(None, help=_(K.opt.on_off), metavar="on|off"),
):
    manager = _manager()
    if on is None:
        manager.author.auto_author()
    else:
        manager.author.auto_author(on == OnOff.on)
    _fail_exit(manager)
    _show_tip()


@_cmd(config_app, "config", "language")
def config_lang(
    lang: Lang | None = typer.Argument(None, help=_(K.opt.lang_value), metavar="en|zh"),
):
    manager = _manager()
    if lang is None:
        cur = get_lang()
        print(_(K.lbl.current_language) + f" {language_display_name(cur)} ({cur})")
        print(_(K.lbl.available_languages))
        _show_tip()
        return
    lang_value = lang.value
    manager.config.language(lang_value)
    if lang_value == "zh":
        print(_(K.msg.lang_zh))
    else:
        print(_(K.msg.lang_en))
    _fail_exit(manager)
    _show_tip()


# ===========================================================================
# version 组 - 版本与自更新（sshm --version 为顶层 flag，sshm version 子命令组）
#   - sshm -v / --version    详细版本信息（独立 flag，不走本组）
#   - sshm version           显示版本组帮助（等价于 sshm version -h）
#   - sshm version update    检查/更新到最新（支持 -f 强制 -y 跳过确认）
#   - sshm version reinstall 重新安装（默认最新，--version X 指定版本覆盖）
# ===========================================================================

version_app = typer.Typer(
    name="version",
    help=_(K.cmd.group_version),
    rich_markup_mode="rich",
)


@version_app.callback(invoke_without_command=True)
def version_default(
    ctx: typer.Context,
) -> None:
    """未指定子命令时，显示版本组帮助（等价于 sshm version -h）。"""
    if ctx.invoked_subcommand is None:
        # 用 click.echo 原样输出帮助（rich 会把 [xxx] 当 markup 误渲染），
        # 且显式退出码 0，避免触发 UsageError 被全局异常处理器渲染为 ❌
        import click

        click.echo(ctx.get_help())
        raise typer.Exit(0)


@_cmd(version_app, "version", "update")
def version_update(
    check: bool = typer.Option(False, "--check", "-c", help=_(K.opt.check_only)),
    force: bool = typer.Option(False, "--force", "-f", help=_(K.opt.force_check)),
    yes: bool = typer.Option(False, "--yes", "-y", help=_(K.opt.yes_prompts)),
):
    """检查并更新到最新版本。"""
    manager = _manager()
    code = manager.system.update(check=check, force=force, yes=yes)
    if code is not None:
        raise typer.Exit(code=code)


@_cmd(version_app, "version", "reinstall")
def version_reinstall(
    target_version: str = typer.Option(
        None,
        "--version",
        "-V",
        help=_(K.opt.version_target),
        show_default=False,
    ),
    force: bool = typer.Option(False, "--force", "-f", help=_(K.opt.force_check)),
    yes: bool = typer.Option(False, "--yes", "-y", help=_(K.opt.yes_prompts)),
):
    """重新安装（覆盖当前可执行文件）。默认升级到最新；--version X 指定版本。"""
    manager = _manager()
    code = manager.system.reinstall(target_version=target_version, force=force, yes=yes)
    if code is not None:
        raise typer.Exit(code=code)


# ===========================================================================
# 组装：注册分组到顶层
# ===========================================================================

for _grp in GROUP_ORDER:
    _target = {
        "key": key_app,
        "repo": repo_app,
        "backup": backup_app,
        "author": author_app,
        "history": history_app,
        "config": config_app,
        "version": version_app,
    }[_grp]
    app.add_typer(_target)


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help=_(K.cmd.version),
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """sshm 顶层入口。帮助文案由 app.help（K.cmd.app_help）提供，此处不重复。"""
