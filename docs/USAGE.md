# 💼 使用指南

完整的 sshm 使用文档。

---

## 📋 目录

- [命令参考](#-命令参考)
- [实战案例](#-实战案例)
- [两种使用方式](#-两种使用方式)
- [国际化 (i18n)](#-国际化-i18n)
- [安全性](#-安全性)

---

## 🛠️ 命令参考

### 基础命令

#### `list` - 查看所有密钥

```bash
sshm key list           # 查看密钥列表
sshm key list -a        # 显示公钥内容（方便复制）
```

**输出示例**：

```text
✨ [当前使用] PERSONAL
----------------------------------------------------------------------
  类型: ed25519
  私钥: id_ed25519.personal
  公钥: ✅ id_ed25519.personal.pub
  别名: git@personal:user/repo.git
  大小: 419 bytes
  修改: 2026-08-14 10:00:00
  状态: ⭐ 正在使用（当前默认 ed25519 密钥）
```

---

#### `key current` - 查看当前默认密钥

```bash
sshm key current [-p 路径]   # 查看当前生效的密钥（含仓库局部/全局覆盖）
```

显示当前正在使用的密钥标签、类型与全局/仓库层级的生效情况，带操作提示。

---

#### `key create` - 创建新密钥

```bash
sshm key create <标签> <邮箱> [选项]

选项:
  -H, --host <域名>    自动配置 SSH config Host 别名（推荐）
  -t, --type <类型>    密钥类型：ed25519（默认）| rsa | ecdsa | dsa
  -n, --name <姓名>    作者姓名（自动记录，供 sshm author 使用）

示例:
  sshm key create personal me@example.com -H github.com
  sshm key create work me@company.com -H gitlab.com -t rsa
  sshm key create project dev@gmail.com -H github.com -n "My Name"
```

---

#### `use <标签> --global` - 切换全局默认密钥

```bash
sshm key switch <标签>

# 自动检测密钥类型并切换为全局默认
sshm key switch personal
```

---

#### `use` - 为 Git 仓库配置专用密钥

```bash
sshm repo use <标签> [选项]

选项:
  -p, --path <路径>    仓库路径（默认当前目录）
  -g, --global         配置为全局默认密钥
  -y, --yes            跳过确认直接执行
  -a, --author         同时设置 Git 作者信息

示例:
  cd ~/my-project
  sshm repo use personal              # 为当前仓库配置 personal 密钥
  sshm repo use work -p ~/work/repo   # 为指定仓库配置 work 密钥
  sshm repo use personal -g           # 配置为全局默认
```

`use` 会自动完成：解析仓库 remote URL → 生成别名 → 更新 SSH Config → 测试连接。

> 💡 **凭据-作者自动联动**：若开启 `auto-author`（默认开启），`use`/`use --global` 切换凭据时，
> 会自动把该凭据绑定的作者应用到当前仓库（局部）或全局（`--global`），无需再手动 `sshm author use`。

---

#### `clone` - 用指定密钥克隆仓库

```bash
sshm repo clone <标签> <git-url> [目标目录] [选项]

选项:
  -y, --yes   跳过确认直接执行

示例:
  # 本机默认用 A 账号，但想用 work 密钥克隆 B 仓库
  sshm repo clone work git@github.com:company/repo.git

  # 克隆到指定目录，跳过确认
  sshm repo clone work git@github.com:company/repo.git myrepo -y
```

`clone` 会用指定凭据克隆，**克隆后仓库的 origin 直接就是 sshm 别名**，即该仓库自动使用该凭据，无需再手动 `sshm repo use`。若该凭据绑定了作者，也会一并设置。

---

#### `auto-author` - 凭据与作者自动联动开关

```bash
sshm config auto-author          # 查看当前状态
sshm config auto-author on       # 开启（默认）
sshm config auto-author off      # 关闭：切换凭据不再自动改作者
```

开启后，`use`、`use --global`、`clone` 切换凭据时，会**自动应用该凭据绑定的作者**，实现"换凭据即换人"。关闭后需手动 `sshm author use`。

---

#### `author` - 管理 Git 作者信息

```bash
# 查看所有已保存的作者
sshm author list

# 添加作者（邮箱省略时自动从公钥注释填充）
sshm author add <标签> [-n 姓名] [-e 邮箱]
sshm author add work -n "Zhang San" -e work@company.com

# 更新已有作者（name/email 至少一项）
sshm author update <标签> [-n 姓名] [-e 邮箱]
sshm author update work -e new@company.com

# 为当前仓库/全局设置作者
sshm author use <标签> [-p 路径] [-n 覆盖姓名] [-e 覆盖邮箱] [--global] [-y]

# 清除作者配置（回退到上级配置）
sshm author unset [-p 路径] [--global]

# 移除作者
sshm author remove <标签> [-y]

# 重写历史中的作者名/邮箱（改名/改邮箱）
sshm history rewrite [-p 路径] [--name 新名|旧名:新名] [--email 新邮箱|旧邮箱:新邮箱] [--author 标签] [-y]
```

> ⚠️ **`history rewrite` 是破坏性操作**：会改写 Git 历史（提交哈希改变），所有匹配旧作者/邮箱的提交都会被替换。
> 原 refs 会备份到 `refs/original/`，执行后需强制推送 `git push --force --all`。
> `--name` / `--email` 支持两种写法：传单值 `NEW` 表示**全量刷新**该字段（所有历史统一为新值），
> 传 `OLD:NEW` 表示**精确替换**（仅把 `OLD` 替换为 `NEW`）。
> 三种模式互斥：`--author` 全量刷某标签、`--name`/`--email` 单值全量刷字段、`OLD:NEW` 精确替换。

```bash
# 全量刷新：把历史所有作者统一为 saved 标签下的姓名/邮箱
sshm history rewrite --author saved -y

# 全量刷新姓名（邮箱不变）
sshm history rewrite --name "Carol"

# 全量刷新邮箱（姓名不变）
sshm history rewrite --email "carol@z.com"

# 精确替换：把历史中 Alice 的名字替换为 Carol
sshm history rewrite --name "Alice:Carol"

# 精确替换：同时替换名字和邮箱
sshm history rewrite --name "Alice:Carol" --email "alice@x.com:carol@z.com"

# 指定仓库 + 跳过确认
sshm history rewrite -p ~/repo --name "旧名:新名" -y
```

---

#### `info` - 查看当前仓库配置

```bash
sshm repo info [-p 路径]
```

显示：仓库路径、remote URL、平台/用户解析、当前使用的别名、密钥详情、SSH Config 内容。

---

#### `test` - 测试 SSH 连接

```bash
sshm repo test                # 测试当前仓库连接
sshm repo test <标签>         # 测试指定密钥连接
sshm repo test --all          # 批量测试所有密钥
sshm repo test -p ~/repo      # 指定仓库路径
```

---

#### `backup / backups / restore` - 安全备份

```bash
sshm backup create              # 备份所有密钥到归档（时间戳目录）
sshm backup list             # 列出所有备份归档
sshm backup restore             # 从最近的备份恢复
sshm backup restore -t rsa      # 按类型恢复
```

所有变更操作前都会自动备份，误删可通过 `restore` 找回。

---

#### `key label` - 保存标签

```bash
sshm key label <新标签> [-t 类型] [-s]
# -s 打标签后立即切换
```

---

#### `rename` - 重命名标签

```bash
sshm key rename <旧标签> <新标签> [-t 类型]
# 自动同步更新 SSH Config 别名与状态文件
```

---

#### `remove` - 删除密钥

```bash
sshm key remove <标签> [-t 类型]
# 默认删除该标签所有类型的密钥；指定 -t 仅删除对应类型
```

---

#### `language` - 切换语言

```bash
sshm config language            # 查看当前语言
sshm config language zh         # 切换为中文
sshm config language en         # 切换为英文
```

---

#### `version update` - 检查并更新

```bash
sshm version update                 # 检查并更新到最新版本
sshm version update --check         # 仅检查更新
sshm version update --check --force # 强制检查（忽略缓存）
sshm version update --yes           # 跳过确认直接更新
```

#### `version reinstall` - 重新安装（覆盖当前可执行文件）

```bash
sshm version reinstall                      # 默认升级到最新版本并覆盖
sshm version reinstall --version v0.0.5     # 指定版本（回滚 / 修复损坏）
sshm version reinstall --yes --force        # 跳过确认 + 强制检查
```

---

## 🧩 实战案例

### 案例一：同时管理个人 GitHub 与公司 GitLab

```bash
# 1. 创建两个密钥
sshm key create personal me@gmail.com -H github.com
sshm key create work me@company.com -H gitlab.com

# 2. 个人项目
cd ~/personal-project
sshm repo use personal

# 3. 公司项目
cd ~/work-project
sshm repo use work

# 4. 测试
sshm repo test
```

### 案例一补充：用指定凭据克隆（无需先配密钥）

```bash
# 本机默认用 personal 账号，但现在想拉取 work 账号权限的仓库
# 直接 git clone 会因权限不足报错，用 sshm repo clone 指定 work 凭据即可
sshm repo clone work git@github.com:company/repo.git

# 完成后：
#   - 仓库已克隆到 ./repo
#   - 该仓库 origin 是 sshm 别名，自动使用 work 密钥
#   - 若 work 绑定了作者，也已自动设置
cd repo
git push   # 直接可推
```

### 案例二：为历史项目配置密钥

```bash
# 查看当前 remote URL
git remote -v

# 一键配置（自动改写 remote URL 为别名并更新 SSH Config）
cd ~/old-project
sshm repo use work

# 验证
sshm repo info
sshm repo test
```

### 案例三：多账号提交信息管理

```bash
# 保存作者信息
sshm author add personal -n "Me" -e me@gmail.com
sshm author add work -n "Zhang San" -e work@company.com

# 切换项目作者
cd ~/work-project
sshm author use work

# 查看当前生效的配置
sshm author list
```

---

## 🔀 两种使用方式

### 方式一：别名方式（推荐）

通过 `sshm repo use` 为每个仓库配置专属别名，多账号**同时使用**，互不干扰：

```bash
cd ~/personal-project
sshm repo use personal
git push    # 自动使用 personal 密钥

cd ~/work-project
sshm repo use work
git push    # 自动使用 work 密钥
```

### 方式二：全局默认切换

通过 `sshm key switch <标签>` 切换全局默认密钥，适合单账号为主的场景：

```bash
sshm key switch personal
# 所有未配置别名的仓库都使用 personal 密钥
```

> 💡 **建议**：多账号场景优先使用别名方式，避免"忘记切换推错账号"。

---

---

## 🌐 国际化 (i18n)

SSH Manager 内置中英双语支持：

- 默认语言：英文（`en`）
- 切换命令：`sshm config language zh` / `sshm config language en`
- 环境变量优先：`SSHM_LANG=zh sshm key list` 可临时指定语言

语言优先级：`SSHM_LANG` 环境变量 > 状态文件 `lang` 字段 > 默认 `en`

---

## 🛡️ 安全性

- **自动备份**：所有变更操作前自动备份到 `~/.ssh/key_backups/`
- **二次确认**：删除、覆盖等危险操作默认需要确认（`-y` 跳过）
- **目录权限**：`~/.ssh` 目录以 700 权限创建
- **隐私保护**：仅操作 `~/.ssh` 目录，不触碰其他系统配置
