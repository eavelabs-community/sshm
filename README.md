<div align="center">

# 🔑 sshm

[![Windows](https://img.shields.io/badge/Windows-0078D6?logo=windows&logoColor=white)](https://github.com/eavelabs-community/sshm/releases/latest)
[![Linux](https://img.shields.io/badge/Linux-FCC624?logo=linux&logoColor=black)](https://github.com/eavelabs-community/sshm/releases/latest)
[![macOS](https://img.shields.io/badge/macOS-000000?logo=apple&logoColor=white)](https://github.com/eavelabs-community/sshm/releases/latest)

**企业级多账号 SSH 密钥管理工具 · 中英双语 · 跨平台**

[![Python Version](https://img.shields.io/badge/python-3.14%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Release](https://img.shields.io/github/v/release/eavelabs-community/sshm)](https://github.com/eavelabs-community/sshm/releases)
[![Build](https://img.shields.io/github/actions/workflow/status/eavelabs-community/sshm/build-release.yml)](https://github.com/eavelabs-community/sshm/actions)

[![Stars](https://img.shields.io/github/stars/eavelabs-community/sshm?style=social)](https://github.com/eavelabs-community/sshm/stargazers)
[![Downloads](https://img.shields.io/github/downloads/eavelabs-community/sshm/total?label=Downloads)](https://github.com/eavelabs-community/sshm/releases)
[![Last Commit](https://img.shields.io/github/last-commit/eavelabs-community/sshm)](https://github.com/eavelabs-community/sshm/commits)
[![Language](https://img.shields.io/github/languages/top/eavelabs-community/sshm?label=Python)](https://github.com/eavelabs-community/sshm)

[快速开始](#-快速开始) • [功能特性](#-功能特性) • [使用文档](#-使用文档) • [常见问题](docs/FAQ.md) • [开发者文档](docs/DEVELOPER.md)

</div>

---

## 📖 简介

**sshm** 是一款专业的多账号 SSH 密钥管理工具，专为需要同时管理多个 Git 账号（个人 GitHub、公司 GitLab、自建 GitLab 等）的开发者设计。

通过**标签化管理**与**自动配置**，它彻底解决了多账号场景下密钥混乱、配置繁琐、误切账号等痛点，让开发者的日常工作更安全、更高效。

### 🎯 核心价值

- ✅ **告别混乱**：用语义化标签清晰管理个人、公司等多个账号的密钥
- ✅ **自动配置**：自动生成并维护 `~/.ssh/config`，无需手动编辑
- ✅ **安全无忧**：所有操作前自动备份，支持一键恢复
- ✅ **无缝切换**：智能识别 Git 仓库，自动匹配正确的 SSH 密钥
- ✅ **中英双语**：内置 i18n，支持 `en` / `zh` 一键切换
- ✅ **跨平台**：Windows（自动修复编码）、Linux、macOS 一致体验

---

## ✨ 功能特性

| 功能模块 | 特性说明 | 核心优势 |
| :------- | :------- | :------- |
| **🏷️ 标签系统** | 每个密钥拥有独立语义化标签 | 一目了然，避免文件名混淆 |
| **🧠 智能配置** | 自动生成 SSH Config + 别名 URL | 复杂配置全自动化 |
| **🛡️ 安全机制** | 操作前自动备份、危险操作二次确认、`restore` 一键恢复 | 数据零丢失风险 |
| **🔌 仓库集成** | `sshm repo use` 自动识别 Git 仓库并配置专用密钥 | 深度融入开发工作流 |
| **👤 作者管理** | `sshm author` 管理并自动设置仓库/全局 Git 作者 | 多账号提交信息不乱 |
| **🌐 国际化** | 内置 i18n，`sshm config language` 切换中英文 | 双语输出体验 |
| **🔄 自动更新** | 启动静默检查，`sshm version update` 一键升级 | 始终保持最新版本 |
| **💻 跨平台** | Windows / macOS / Linux | 统一一致性体验 |

---

## 🛠️ 系统要求

- **操作系统**: Windows / macOS / Linux
- **依赖环境**:
  - 使用可执行文件版本：**无**（无需安装 Python）
  - 使用源码/Pip 版本：**Python 3.14+**
- **工具依赖**: 系统需预装 `ssh-keygen`（通常系统自带）

---

## 🚀 快速开始

### 1. 安装

建议直接使用预编译的可执行文件，无需配置 Python 环境。

#### 方式 A：一键安装（推荐）

**Windows (PowerShell)**

```powershell
irm https://raw.githubusercontent.com/eavelabs-community/sshm/main/scripts/install.ps1 | iex
```

**Linux / macOS**

```bash
curl -fsSL https://raw.githubusercontent.com/eavelabs-community/sshm/main/scripts/install.sh | bash
```

> 💡 **`sshm` 显示旧版本 / 运行报错？** 通常是 PATH 中残留了旧的 sshm 目录（如本地构建产物）抢先命中。重新运行安装脚本并加清理参数即可：
> 
> **Windows**
> 
> ```powershell
> irm https://raw.githubusercontent.com/eavelabs-community/sshm/main/scripts/install.ps1 -OutFile install.ps1
> powershell -ExecutionPolicy Bypass -File .\install.ps1 -CleanPath
> ```
> 
> **Linux / macOS**
> 
> ```bash
> curl -fsSL https://raw.githubusercontent.com/eavelabs-community/sshm/main/scripts/install.sh -o install.sh
> bash install.sh --clean-path
> ```
> 
> 清理后请**重新打开终端**再运行 `sshm`。

#### 方式 B：手动下载

前往 [Releases 页面](https://github.com/eavelabs-community/sshm/releases) 下载对应平台文件，重命名为 `sshm` 后放入 PATH 路径即可。

#### 方式 C：源码运行

```bash
git clone https://github.com/eavelabs-community/sshm.git
cd sshm
python -m sshm --version
python -m sshm key list
```

### 2. ⚡ 30 秒上手指南

假设你需要同时使用**个人 GitHub** 和**公司 GitLab**：

```bash
# 1️⃣ 创建密钥
sshm key create personal my@email.com --name "Personal"
sshm key create work work@company.com --name "Work Dev"

# 2️⃣ 查看状态
sshm key list

# 3️⃣ 设为全局默认
sshm key switch personal

# 4️⃣ 在项目中按仓库绑定密钥与作者
cd ~/my-project
sshm repo use personal        # 为当前仓库配置 personal 密钥
sshm author use personal      # 为当前仓库设置对应 Git 作者
```

✅ **搞定！** 以后推送代码时，系统会自动选择正确的密钥，无需手动切换。

---

## 📚 使用文档

### 目录结构

sshm 遵循标准且安全的目录结构：

```text
~/.ssh/
├── config                      # ⚙️ 自动维护的 SSH 配置文件
├── id_ed25519.personal         # 🔑 托管的私钥
├── id_ed25519.personal.pub     # 🔓 对应的公钥
├── .sshm_state                 # 📊 状态文件（当前激活的密钥）
└── key_backups/                # 💾 自动备份目录（按时间戳归档）
```

### 命令总览

| 命令 | 说明 |
| :--- | :--- |
| `sshm key list [-a]` | 查看所有密钥（`-a` 显示公钥内容） |
| `sshm key create <标签> <邮箱> [--name ..] [--host ..] [-t 类型]` | 创建新密钥（`--name` 记录作者名，`--host` 配置 SSH 主机） |
| `sshm key switch <标签>` | 切换全局默认密钥（默认开启 `auto-author` 时会同步对应作者） |
| `sshm key current` | 查看当前使用的密钥 |
| `sshm key rename <旧> <新>` / `sshm key remove <标签>` / `sshm key label <标签>` | 重命名 / 删除 / 保存当前默认密钥为标签 |
| `sshm repo use <标签> [-p 路径]` | 为 Git 仓库配置专用密钥 |
| `sshm repo clone <标签> <git-url> [目录]` | 用指定密钥克隆仓库，克隆后仓库直接使用该密钥 |
| `sshm repo info` | 查看当前仓库配置详情 |
| `sshm repo test [--all]` | 测试 SSH 连接 |
| `sshm author list / add / update / remove / use / unset` | 管理并应用仓库/全局 Git 作者 |
| `sshm history rewrite [--author <标签>]` / `[--name OLD:NEW]` / `[--email OLD:NEW]` | 重写历史中的作者名/邮箱（破坏性，需强制推送） |
| `sshm backup create / list / restore` | 备份、列出、恢复密钥 |
| `sshm config auto-author [on/off]` | 开关"密钥-作者"自动联动（默认开启；省略参数可查看当前状态） |
| `sshm config language [en/zh]` | 切换中英文输出（省略参数可查看当前语言） |
| `sshm version update [-f -y]` | 检查并更新到最新版本（`-y` 跳过确认） |
| `sshm version reinstall [--version X]` | 重新安装/回滚到指定版本 |
| `sshm --help` | 查看完整帮助 |

> 📖 完整命令详解与实战案例请见 [使用指南](docs/USAGE.md)

---

## 📁 项目文档

| 文档 | 说明 |
| :--- | :--- |
| [使用指南](docs/USAGE.md) | 完整命令参考与实战案例 |
| [安装脚本说明](docs/INSTALL.md) | 一键安装脚本详细用法 |
| [自动更新说明](docs/UPDATE.md) | 更新机制与用法 |
| [常见问题 FAQ](docs/FAQ.md) | 高频问题解答 |
| [开发者文档](docs/DEVELOPER.md) | 架构设计、开发与构建指南 |
| [更新日志](docs/CHANGELOG.md) | 版本变更记录 |

---

## 📄 许可证

本项目基于 [MIT](LICENSE) 许可证开源。
