# ❓ 常见问题 (FAQ)

## 使用问题

### Q: 为什么推荐使用别名而不是切换默认密钥？

**A:** 别名方式的优势：

- ✅ 多账号可以同时使用，无需频繁切换
- ✅ 项目配置一次，永久生效
- ✅ 不会因为忘记切换而推送到错误账号
- ✅ 团队成员可以使用不同的密钥

**示例**：

```bash
# 个人项目
cd ~/personal-project
sshm repo use personal
git push   # 自动使用 personal 密钥

# 公司项目
cd ~/work-project
sshm repo use work
git push   # 自动使用 work 密钥
```

---

### Q: 如何将现有项目改用别名方式？

**A:** 使用 `sshm repo use` 一键完成，或手动修改 remote URL：

```bash
# 方式一：一键配置（推荐）
cd ~/project
sshm repo use personal

# 方式二：手动修改 remote URL
git remote -v
git remote set-url origin git@personal:user/repo.git
git remote -v
ssh -T git@personal   # 测试连接
```

---

### Q: 密钥类型如何选择？

**A:** 推荐优先级：

| 密钥类型 | 安全性 | 性能 | 兼容性 | 推荐 |
|----------|--------|------|--------|------|
| **ed25519** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ 默认推荐 |
| **rsa 4096** | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ✅ 兼容旧系统 |
| ecdsa | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⚠️ 不推荐 |
| dsa | ⭐⭐ | ⭐⭐ | ⭐⭐ | ❌ 已弃用 |

---

### Q: 误删了密钥怎么办？

**A:** 所有变更操作前都会自动备份到 `~/.ssh/key_backups/`，执行：

```bash
sshm backup list    # 查看备份列表
sshm backup restore    # 从最近备份恢复
```

---

### Q: 如何切换中英文界面？

**A:**

```bash
sshm config language zh    # 中文
sshm config language en    # 英文
```

也可以通过环境变量临时指定：`SSHM_LANG=zh sshm key list`

---

### Q: 如何查看当前仓库使用的密钥？

**A:**

```bash
sshm repo info       # 查看仓库配置详情
sshm repo test       # 测试当前仓库连接
```

---

### Q: 如何更新到最新版本？

**A:**

```bash
sshm version update          # 检查并更新
sshm version update --check  # 仅检查
```

程序每次运行也会静默检查更新并提示。

---

## 故障排查

### Q: Windows 下中文/emoji 显示乱码？

**A:** 程序已自动修复 Windows 控制台 UTF-8 编码（SetConsoleOutputCP 65001），一般无需手动处理。若仍乱码，请使用 Windows Terminal 或确认代码页：

```powershell
chcp 65001
```

---

### Q: `ssh: Could not resolve hostname` 错误？

**A:** 通常是 SSH Config 别名未生效。检查：

```bash
sshm repo info        # 确认别名配置
cat ~/.ssh/config
sshm repo test        # 测试连接
```

若使用 `sshm repo use` 配置后仍报错，可手动执行 `sshm repo use <标签>` 重新生成配置。

---

### Q: 为什么 `sshm key list` 提示有新版本但不更新？

**A:** 静默检查只会**提示**，不会自动更新。执行 `sshm version update` 并按提示确认即可。

---

### Q: 源码运行时提示 `No module named 'sshm'`？

**A:** 请确保在项目根目录运行，或将 `src` 加入 Python 路径：

```bash
cd SSHManager
PYTHONPATH=src python -m sshm key list
```

---

### Q: 打包后的可执行文件报 `ModuleNotFoundError`？

**A:** 请确保使用 Python 3.14 或以上版本重新构建（旧版本存在 f-string 兼容性问题），详见 [开发者文档](DEVELOPER.md) 的构建章节。
