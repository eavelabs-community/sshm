# 🔄 更新功能说明

SSH Manager 内置自动检查更新与一键更新能力，更新相关命令统一归入 `sshm version` 子命令组。

## 命令一览

| 命令 | 说明 |
| --- | --- |
| `sshm --version` / `sshm -v` | 顶层 flag，仅打印版本号 |
| `sshm version` | 版本总览（版本号 + 平台） |
| `sshm version update` | 检查并更新到最新版本 |
| `sshm version reinstall` | 重新安装（覆盖当前可执行文件） |

## 功能特性

### ✅ 已实现

1. **静默版本检查**
   - 运行普通命令时自动在后台检查更新（`sshm version update` / `sshm version reinstall` 自身会处理，已跳过静默检查）
   - 24 小时缓存，避免频繁请求
   - 发现新版本时在命令执行前友好提示
   - 不干扰正常使用

2. **手动更新命令**（归属 `version` 组）
   - `sshm version update`：检查并更新到最新版本
   - `sshm version update --check` / `-c`：仅检查更新，不执行更新
   - `sshm version update --force` / `-f`：强制检查，忽略缓存
   - `sshm version update --yes` / `-y`：跳过确认直接更新
   - `sshm version reinstall`：重新安装，默认升级到最新版本（覆盖当前可执行文件）
   - `sshm version reinstall --version v0.0.6` / `-V v0.0.6`：指定版本重装（修复损坏 / 回滚）
   - `sshm version reinstall --force` / `-f`、`--yes` / `-y`：同上含义

3. **版本比较**
   - 自动解析语义化版本号
   - 准确判断版本新旧

4. **自动下载与替换**
   - 下载当前平台对应的可执行资产（按平台关键词模糊匹配，排除源码包）
   - 跨平台替换：`Windows` 自动替换可执行文件；`Linux/macOS` 直接替换或提示使用 `sudo`

## 使用方法

### 1. 查看当前版本

```bash
sshm --version          # 仅版本号
sshm version            # 版本号 + 平台信息
```

### 2. 仅检查更新

```bash
sshm version update --check

# 强制检查（忽略缓存）
sshm version update --check --force
```

### 3. 更新到最新版本

```bash
sshm version update                 # 检查 → 确认 → 下载 → 替换
sshm version update --yes           # 跳过确认直接更新
```

**执行流程：**

1. 检查是否有新版本（可 `--check` 仅检查、`--force` 忽略缓存）
2. 显示更新内容（版本号、发布时间、更新说明）
3. 询问确认（除非 `--yes`）
4. 下载新版本
5. 自动替换可执行文件

### 4. 重新安装 / 指定版本

```bash
sshm version reinstall              # 默认升级到最新版本并覆盖
sshm version reinstall --version v0.0.6   # 指定版本（回滚 / 修复损坏）
sshm version reinstall --yes --force      # 跳过确认 + 强制检查
```

> 说明：`reinstall` 未指定 `--version` 时与 `update` 行为一致（升级到最新版），
> 区别在语义——`reinstall` 强调"覆盖当前可执行文件"，适合修复损坏或锁定某版本。

### 5. 静默检查（自动）

每次运行普通命令时，程序会自动在后台检查更新：

```bash
sshm key list

# 如果有新版本，会在输出前显示提示：
# 💡 有新版本可用: v0.0.7 (当前: v0.0.6)
#    运行 'sshm version update' 更新到最新版本
```

## 注意事项

- 更新 / 重新安装过程会替换当前正在运行的可执行文件，请确保在非关键任务时执行
- 如果网络受限无法访问 GitHub，可手动前往 Releases 页面下载
- 更新不会影响 `~/.ssh` 目录下的密钥与配置文件
- 源码运行模式（`python -m sshm`）无法自更新，会提示改用 `git pull` 或从 Releases 下载
