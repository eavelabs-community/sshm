# 📋 更新日志

本项目的所有重要变更都会记录在此文件中。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [未发布]

### 规划中

- [ ] SSH Agent 管理
- [ ] 密钥导入/导出
- [ ] 远程备份与云同步
- [ ] 团队协作与密钥安全扫描

---

## [0.0.5] - 2026-08-23

### ✨ 重构与改进

- **错误码枚举化（单一事实来源）**：新增 `ErrCode(str, Enum)` 枚举，值即错误码字符串；继承 `str` 使 `ErrCode.X == "X"` 为真，向后兼容任何遗留字符串比较。注册表 `_RAW_SPECS: dict[ErrCode, ErrorSpec]` 的 key 与 `ErrorSpec` 首参均引用枚举成员，彻底消除调用点与注册表的双重硬编码；`ERROR_REGISTRY` 由枚举严格推导为 `str` key（`ErrCode` 哈希与裸字符串不等，故保持查表用 str key）
- **可扩展错误码转换器分派**：新增 `convert_error_code(raw)` 按输入类型分派到已注册的转换器，返回 `_CodeConversion(key, known)`；内置 `ErrCode` / `str` 两个转换器（枚举走枚举转换器、字符串走字符串转换器），未知类型抛 `TypeError` 并提示 `register_error_code_converter` 扩展点，未来新增类型无需改动 `SSHMError` / `manager._fail`；`SSHMError` / `manager._fail` 利用 `known` 判断走错误码路径还是文本式透传
- **i18n 命名空间统一**：git 错误码 `NO_ORIGIN_REMOTE` / `SSH_TEST_TIMEOUT` 误用的 `msg.*` 前缀统一改为 `err.*`，与全局错误码命名空间一致；旧 `msg.*` key 全项目零残留
- **i18n 清单分组整理**：`templates.py` 的 `KEYS`（458 个 key）从半有序扁平列表整理为按 prefix 严格分块（misc/suggest/cmd/opt/hdr/lbl/prompt/menu/msg/err/sys/upd/ver），每块加 `# ---- prefix 说明 ----` 注释，组内按字母序；修正此前因命名空间改名错位、夹在 `msg.` 段的 3 个 `err.*` key，归位到 `err.` 块
- **校验**：i18n 三表（templates / zh / en）key 完全一致（458/458/458）；全量 113 测试通过，cli-report 60 场景全绿，deadcode 零冗余，pyright 0 警告

### 📝 文档

- 文档与版本号同步至 v0.0.5（INSTALL / UPDATE 安装示例）

---

## [0.0.4] - 2026-08-21

### ✨ 新功能

- **`-h` 帮助简写**：`--help` 现在可用 `-h` 触发，顶层与所有子命令均生效
- **`-v` 版本信息增强**：`-v`/`--version` 除版本号外，同时显示平台、Python 版本与运行模式（打包可执行文件 / 源码）
- **`-v` 构建来源标识**：打包可执行文件运行时，额外显示「本地编译 / 线上发布 / 未知」，依据部署脚本在 exe 旁写入的来源标记文件判断
- **`-v` 表格化渲染**：版本信息改用项目统一的表格样式（图标 + 标签 + 值），带 emoji 图标与 CJK/emoji 对齐，风格与其它命令一致
- **`history rewrite --author <label>` 全量刷新**：把历史所有作者/邮箱统一为指定已保存作者（支持 `-a` 简写）
- **`history rewrite` 成对参数 `--name`/`--email`**：用 `OLD:NEW` 精确替换（`--name Alice:Carol`）或用单值 `NEW` 全量刷新该字段（`--name Carol`，另一字段不变）；`-n`/`-e` 简写随新语法生效
- **`author update <label> [-n name] [-e email]`**：更新已有作者，name/email 至少一项
- **`author remove <label>`**：删除已保存的作者（支持 `-y` 跳过确认）
- **打包体积优化**：exe 从 ~30.8MB 降至 ~12MB（排除 numpy/PIL 等无关重库 + 自动启用 UPX 压缩）
- **rich 输出落地（L2 语义着色 + L3 进度条）**：
  - `ui.output` 默认改用 `RichOutput`（tty 感知）：真实终端显示语义颜色（按 `✅/⚠️/❌/📝` 等 emoji 自动着色，零侵入）+ rich 表格；非 tty（管道/重定向/测试）自动回退 `ConsoleOutput` 的 ASCII 行为，输出可预测、无 ANSI 码
  - 新增 `progress()` / `status()` 上下文管理器：`sshm update` 下载改用真实进度条；`history rewrite` 历史重写显示 spinner；rich 不可用时静默降级，不阻断业务
- **emoji 收敛（UI 规范化）**：移除字段/区块级的纯装饰性 emoji（`📂📁🔗📊🔑🔧🗝️📝🌐👤📧⬇️🧑`），只保留表达状态/结果的语义 emoji（`✅❌⚠️📝💡✨🎉🔀🧪💾`）与表格状态列；统一中英文提示（修复 `hdr.interactive` 中文多出的 `🔑`）；`-v` 表格保留图标列。移除无需改动测试（测试不依赖装饰性 emoji）
- **`config lang` 更名为 `config language`**：全链路同步（CLI 命令、命令注册表、manager 方法 `SystemCommands.language`、i18n key `cmd.config_language`、脚本、测试、文档与 cli-report 快照），不保留旧名、不兼容旧命令
- **错误提示富化与自适应排版**：
  - `Usage` 续行改为基于 rich Console 实际终端宽度自适应折行，缩进用显示宽度精确对齐 `💡 Usage: ` 前缀（修复固定 78 列在窄/宽终端下换行参差的问题）
  - 修复 `[en|zh]` 等含方括号的参数 token 被 rich 当作 markup 吞掉的问题（`_command_params_block` 与错误消息统一转义）；`config language`/`auto-author` 的枚举参数去掉易出错的方括号 metavar，非法值提示从 `Invalid value for ''` 修正为 `Invalid value for 'en|zh'`
  - 枚举参数（如 `--type`）在用法提示中直接展示支持值 `ed25519|rsa|ecdsa|dsa`
- **分组默认视图 tip 段统一**：`sshm repo`/`sshm author` 底部裸 `print("💡 ...")` 收尾改为统一 `render_tip_block` 模板；`sshm config`/`sshm backup` 默认视图补齐「相关命令」提示段，6 个分组默认视图（key/repo/author/backup/config）输出格式完全一致
- **cli-report 覆盖增强**：校验升级为格式断言（`--help` 必有 `Usage:` 行、失败场景必有统一 `❌` 标记）；补齐 `config auto-author` 非法值、`--type` 选项缺值等快照场景
- **core 服务层按业务域分组**：将 `core/` 扁平服务拆为 `services/` 子包并按域分组——`ssh/`（KeyStore / SSHConfigManager / path）、`git/`（GitRepoService / AuthorService / rewrite）、`storage/`（StateManager / BackupService）、`net/`（SSHTester / UpdateManager）；门面 `manager.py`、异常 `errors.py`、命令编排 `commands/` 留在 `core/` 顶层；同步更新全部 import（源码 / 测试 / 文档 / 架构图），对外导出路径（`sshm.core.*`）经 `core/__init__.py` 重新导出保持不变
- **业务错误全局统一渲染**：收敛此前"各处自行拼 `❌` 并裸 print"的 DIY 散落——新增统一渲染 `ui.tip.render_business_error(msg, *, icon, hint)`（空行 + ❌/⚠️ + 分隔线 + 💡 建议）；`manager._fail` 改为调用它并支持 `icon`/`hint`，新增不置退出码的 `manager._warn` 供软告警；commands 层 55+ 处 `_fail` 调用点去掉 `❌`/`⚠️`/`\n` 前缀，带建议行的场景并入 `hint`；services 辅助函数（updater/path/gitrepo）的错误统一走 `render_business_error`。视图内联提示与交互流程警告保留原样（属展示/交互内容，非错误机制）。新增命令报错只需 `self.m._fail(_('err.xxx'))` 或 `raise ValidationError(...)`，无需定制化格式
- **相关命令跨组关联（声明式）**：`related_commands` 支持跨分组 related——`key switch` 声明关联 `repo use`（为仓库配置密钥），缺参/用法错误与正常 tip 共用同一推导逻辑，不再出现 `sshm key use` 的错组拼接；`command_list_lines` 用命令自身分组渲染
- **相关命令分块展示**：tip 的"相关命令"拆分为「本组命令」与「跨组 related 命令」两块，各自带独立标题（`More commands in this group` / `More related commands`，新增 `misc.related_tip_cross`），跨组关联一目了然；无跨组关联的命令只显示本组块
- **版本机制修复（CI 构建）**：动态版本由 `attr = "sshm.__version__"`（构建期 import 整个包触发 `rich` 未装而崩溃）改为 `version = { file = "src/sshm/_version.txt" }`（构建只读文件、不 import 包）；新增 `src/sshm/_version.txt` 作为版本单一来源，`constants.VERSION` 优先级改为 `_version.txt` > CHANGELOG > 元数据；`sshm.spec` 与 `pyproject` package-data 打入 `_version.txt`，CI 打包改用 `sshm.spec` 保证 exe 版本正确（不再回落 0.0.0）

---

## [0.0.3] - 2026-08-16

### ✨ 新功能

- **🔧 CLI 全面重构为 Typer 框架**：告别手写 argparse，改用声明式 `@app.command()` 定义命令。自动生成 `--help`（含参数说明/必填标记/默认值）、自动参数校验、自动 Shell 补全（`--install-completion`）、rich 彩色帮助
- **📦 新增 `sshm -v` / `--version`**：一键查看当前版本
- **🔄 版本自动同步**：`VERSION` 改为从 `docs/CHANGELOG.md` 自动解析最新版本，发布新版本无需改动代码，杜绝版本号不同步
- **🌐 i18n 重构为「稳定 key + 双语字典」架构**：翻译键从"英文句子"改为稳定 key（如 `cmd.list`），英文（EN）与中文（ZH）两套字典独立维护且完全对称。新增 `sshm lang` 命令行切换、`SSHM_LANG` 环境变量，彻底解决旧版"改描述要改两处"与废弃/重复翻译键冗余问题
- **📦 新增 `language` 包**：拆分为 `i18n_language.py`（通用 key 模版 + 权威 key 清单）、`i18n_en.py`（英文实现）、`i18n_zh.py`（中文实现）、`i18n.py`（组装层，只负责翻译函数与语言状态）。新增语言只需在 `language/` 加一个字典文件
- **🧪 新增 i18n 一致性守门测试**：自动校验 key 模版 / EN / ZH 三方同步、翻译非空、占位符一致（防 `format` 抛 `KeyError`）、命名前缀规范。新增/修改翻译 key 时 `pytest` 立即拦截遗漏
- **🔍 新增提交前检查（pre-commit hook）**：`scripts/check_all.py` 统一调度 compile / i18n / pytest / pyright，任一失败阻断提交。设计可扩展，新增检查只需注册一行。`scripts/hooks/install.py` 一键安装到 `.git/hooks/pre-commit`，支持快速模式与 `--skip` 跳过
- **⚡ pytest 并行加速（pytest-xdist）**：完整测试默认 `-n 3` 并行，实测提速约 25%（串行 ~7.4s → 并行 ~5.6s）。支持 `SSHM_TEST_JOBS` 调整并行度，未安装 xdist 时自动回退串行
- **🔢 版本号全链路自动化**：彻底消除硬编码发布号。`VERSION` 多级自动解析（CHANGELOG → 包元数据 → `0.0.0` 开发版兜底）；更新下载改为按平台关键词模糊匹配 Release 资产（不再依赖固定的资产文件名）；README 静态版本徽章改为动态 `github/v/release` 徽章（自动显示最新 tag）。打 tag 即可全自动同步版本，无需改任何代码

### 🛠 架构改进

- **命令注册机制升级**：将手写 `parser.py`（282 行）/ `commands.py`（245 行）/ `commands/` 注册表全部替换为 Typer 装饰器注册制，新增命令只需 `@app.command()` 一处声明，自动出现在帮助与交互菜单，不再遗漏
- **基于 pyright 类型检查**：统一在 `pyproject.toml` 配置，全项目类型修复后达到 **0 error / 0 warning / 0 note**，无任何 `type: ignore` 强行抑制
- **依赖规范化**：统一用 `pyproject.toml` 管理依赖（`[project]` 运行时 + `[project.optional-dependencies] dev`），`wcwidth` 转为正式依赖（中文表格对齐核心功能），移除缺失时的类型抑制
- **清理 CLI 冗余**：移除 `__main__.py` 未使用的 `_NON_UPDATE_ARGS` 死代码、`cmd_list` 未使用的 `ctx` 参数；交互菜单 `show_help` 改用 Click 命令对象渲染帮助，不再依赖 `typer.testing` 测试工具进生产代码；补齐 `build_local.py` 等所有未标注返回类型的函数

### 🐛 修复

- **`history rewrite` 重写后无法推送**：修复历史重写后 HEAD 停留在 detached 状态的问题，重写后自动切回分支，可正常 `git push`
- **`pad_cell` 未导入**：`sshm test --all` 会 `NameError` 崩溃，已补导入
- **`_` 被 `winreg.QueryValueEx` 覆盖**：`system.py` 中解包把 i18n 的 `_` 翻译函数覆盖为 int，导致后续所有提示文案崩溃，已修复
- **`temp_fd` 文件句柄泄漏**：`updater.py` 中 `mkstemp` 返回的文件描述符未关闭，Windows 上更新后无法删除临时文件，已补 `os.close`
- **`print_table` 参数类型**：`truncatable`/`center_cols` 标注修正为 `Iterable[int]`（适配传入 list）
- **i18n 占位符缺失**：`msg.files_backed_up` 英文翻译缺 `{count}` 占位符，导致英文下数量信息静默丢失（由 i18n 守门测试自动发现并修复）
- **`sys.stdout.reconfigure` 类型告警**：基于 pyright 对 `TextIO` 未声明该方法报错，改用 `getattr` 动态访问规避
- **版本号不同步**：`constants.py` 兜底版本与 `__init__.py` docstring 从 0.0.2 更新到 0.0.3
- **`sshm test --all` 退出码失效**：测试全部密钥时即使有连接失败也不会返回非零退出码（`_had_error` 未置位），已修复，可在 CI/脚本中通过退出码判断结果
- **`sshm info` SSH config 块解析误匹配**：用子串匹配主机名会误显示其他 Host 块，改为按 `Host` 块语义精确解析（`_extract_ssh_config_block`）
- **交互菜单 Ctrl+C 崩溃**：交互菜单任意输入点按 Ctrl+C 会打印 traceback 退出，改为友好提示并退出
- **更新缓存损坏崩溃**：`~/.sshm_update_cache` 损坏时 `check_update` 抛 `KeyError`，改为校验缓存结构并优雅降级
- **全面 Review 清理**：
  - 删除 `cli_app()` 死代码（无引用）
  - `rename` 冲突提示 `lbl.file_placeholder` 传未定义占位符导致缺文件名，已修正拼接
  - `use --global --author` 时 `--path` 被硬编码 `.` 忽略，改为尊重用户传入路径
  - `test <label>` 别名未配置时不置业务失败标志（与 `--all` 分支不一致），已统一
  - 收窄 `console.py`/`system.py` 的裸 `except:` 为 `except Exception`
  - 发布日兜底值 `'Unknown'` 硬编码改为走 i18n（新增 `msg.unknown`）
  - 显式声明 `click` 运行时依赖（`show_help` 直接使用）
  - `add_key` 与 `remove_key` 之间补空行
  - 新增 i18n 守门测试：校验代码实际使用的 `_()` key 均已登记到 KEYS 模版（防漏翻译）

### 📝 文档

- README 徽章区重构：平台拆分为 Windows / Linux / macOS 独立徽章，新增 Release / Build / Stars / Downloads / Last Commit / Language 等指标
- 新增 `scripts/HOOKS.md`：提交前检查的安装 / 使用 / 扩展指南（含 pytest-xdist 并行说明）
- 测试规模：64 → 75 个（新增 i18n 一致性守门测试）

---

## [0.0.2] - 2026-08-16

### ✨ 新功能

- **🔗 指定凭据克隆**（`sshm clone`）：直接用某个标签的密钥克隆仓库，无需先 `sshm use`。克隆后仓库 origin 自动指向 sshm 别名，即该仓库直接使用对应凭据。支持 `git@host:user/repo.git`（scp）、`ssh://`（ssh2）、`https://` 三种 URL，可指定目标目录与 `-y` 跳过确认
- **👤 凭据-作者自动联动**（`sshm auto-author`）：新增开关（默认开启）。`sshm use`（局部）/ `sshm use --global`（全局）切换凭据时，自动应用该凭据绑定的作者，实现"换凭据即换人"。无绑定则自动跳过，不影响
- **✏️ 历史作者重写**（`sshm author fix`）：重写所有历史中的作者名/邮箱，支持单独改名、改邮箱，或两者同时处理。底层用 git fast-export/import 纯 Python 实现，不依赖外部工具，兼容打包分发。原 refs 备份到 `refs/original/` 便于回滚

### 🐛 修复

- **`tag` 元数据继承**：`sshm tag` 创建的标签现在继承默认密钥的 host 映射与作者信息，避免私有 Git hostname 错乱、作者信息缺失
- **`clone` 作者推断副作用**：克隆后设置作者时不再从别名 remote URL 推断用户名，避免把组织名错设成 `user.name`

### 📝 文档

- 新增完整架构图 `docs/architecture.mmd`，并嵌入开发者文档
- README 与使用指南补充 `clone`、`auto-author` 命令说明及实战案例

---

## [0.0.1] - 2026-08-14

### 🎉 全新发布

自本项目开始以来，所有功能开发与历史迭代已整合为单一发布版本。首个正式发布包含以下能力：

#### ✨ 核心功能

- **🏷️ 标签化管理**：每个 SSH 密钥拥有独立语义化标签，无限账号轻松管理
- **🔑 多类型密钥**：支持 ed25519（默认）/ rsa / ecdsa / dsa 四种类型
- **🧠 智能仓库配置**（`sshm use`）：自动识别 Git 仓库与 remote URL，生成并维护 SSH 别名配置
- **🔄 一键切换**（`sshm use <标签> --global`）：快速切换全局默认身份，支持自动检测密钥类型
- **👤 作者管理**（`sshm author`）：管理多账号 Git 作者信息，自动设置仓库/全局提交身份
- **⚙️ 自动配置**：自动生成并维护 `~/.ssh/config` 与别名 URL
- **🛡️ 安全备份**：所有操作前自动备份，`sshm restore` 一键恢复
- **🌐 国际化**：内置 i18n，`sshm lang` 切换中英文，支持 `SSHM_LANG` 环境变量
- **🖥️ 交互模式**：双击运行进入 TUI 菜单，零命令基础也可使用
- **🔄 自动更新**：启动静默检查 + `sshm update` 一键升级，24 小时缓存

#### 🔧 工程化与稳定性

- **完全模块化架构**：`core`（业务）/ `cli`（命令行）/ `utils`（工具）三层分离
- **跨平台构建**：GitHub Actions 在 Windows / Linux / macOS 三平台自动打包发布
- **Python 3.14 支持**：基于最新稳定版构建，同时兼容 3.11+ 语法
- **PyInstaller 打包**：单文件可执行，开箱即用，无需 Python 环境
- **CI 稳定性修复**：解决 f-string 跨版本兼容与模块静态分析遗漏问题
- **一键安装脚本**：Windows（PowerShell）与 Linux/macOS（Shell）在线安装
- **Windows 编码修复**：自动设置 UTF-8 控制台，中英文与 emoji 显示无乱码

#### 📚 文档

- 全新项目文档体系：使用指南、安装说明、更新说明、FAQ、开发者文档
- 完整命令参考与实战案例

---

## 版本规范

### 语义化版本号（MAJOR.MINOR.PATCH）

- **MAJOR**：不兼容的 API 变更
- **MINOR**：向下兼容的功能新增
- **PATCH**：向下兼容的问题修复

### 变更类型标签

- `Added` 新增功能
- `Changed` 功能变更
- `Deprecated` 即将废弃的功能
- `Removed` 已删除的功能
- `Fixed` 问题修复
- `Security` 安全性修复
