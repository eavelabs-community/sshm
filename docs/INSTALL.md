# 📦 安装脚本使用说明

SSH Manager 提供跨平台的一键安装/卸载脚本，自动下载预编译可执行文件并配置 PATH。

## 快速安装

### Windows（PowerShell）

**一键在线安装（推荐）**

```powershell
irm https://raw.githubusercontent.com/eavelabs-community/sshm/main/scripts/install.ps1 | iex
```

**下载后安装**

```powershell
Invoke-WebRequest -Uri https://raw.githubusercontent.com/eavelabs-community/sshm/main/scripts/install.ps1 -OutFile install.ps1
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

**⚠️ 执行策略问题**

如果遇到 "禁止运行脚本" 错误：

```powershell
# 临时允许（仅当前会话）
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process
powershell -File .\scripts\install.ps1

# 或者直接带参数执行
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

**自定义安装**

```powershell
# 指定版本安装
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Version v0.0.6

# 指定安装目录
powershell -ExecutionPolicy Bypass -File .\install.ps1 -InstallDir "C:\Tools\sshm"

# 不添加到 PATH
powershell -ExecutionPolicy Bypass -File .\install.ps1 -NoAddPath

# 清理 PATH 中旧的 sshm 残留（旧安装目录/本地构建可能覆盖新版）
powershell -ExecutionPolicy Bypass -File .\install.ps1 -CleanPath

# 卸载
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Uninstall
```

### Linux / macOS

**一键在线安装（推荐）**

```bash
curl -fsSL https://raw.githubusercontent.com/eavelabs-community/sshm/main/scripts/install.sh | bash
```

**自定义安装**

```bash
# 下载安装脚本
curl -O https://raw.githubusercontent.com/eavelabs-community/sshm/main/scripts/install.sh
chmod +x install.sh

# 默认安装（最新版）
./install.sh

# 指定版本安装
./install.sh --version v0.0.6

# 指定安装目录
./install.sh --install-dir ~/.local/bin

# 不添加到 PATH
./install.sh --no-add-path

# 清理 shell 配置中的旧 sshm 残留
./install.sh --clean-path

# 卸载
./install.sh --uninstall
```

## 功能特性

### ✅ 自动化
- 自动下载最新版本（或指定版本）
- 自动重命名为 `sshm.exe` / `sshm`
- 自动创建安装目录
- 显示下载进度

### ✅ 交互式
- 安装前确认
- 询问是否添加到 PATH
- 安装后验证

### ✅ 灵活性
- 支持指定版本
- 支持自定义安装目录
- 支持静默安装
- 支持卸载

### ✅ 安全性
- 使用 HTTPS 下载
- 安装前显示详细信息
- 安装后验证文件完整性

## 安装后验证

```bash
# 查看版本
sshm --help

# 查看密钥列表
sshm key list

# 测试连接
sshm repo test
```
