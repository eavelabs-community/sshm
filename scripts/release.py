#!/usr/bin/env python3
"""sshm 一键发版脚本。

用法:
    python scripts/release.py <新版本>            # 只修改版本相关文件（幂等，可审查）
    python scripts/release.py <新版本> --tag      # 修改文件 + 打 git tag（不 push）
    python scripts/release.py <新版本> --push     # 修改文件 + 打 tag + push 当前分支 + push tag（触发 CI 构建发版）

--push 会先推送当前分支（确保远端 main 拿到全部提交），再推送 tag 触发 CI，
避免只推 tag 而远端主干仍落后于本地。

版本事实来源：
    src/sshm/_version.txt 是 VERSION 的唯一来源（pyproject.toml 的
    version={file=...} 读取它，sshm.spec 打包打入，constants.VERSION 运行期解析）。
    因此改版本只需改此文件，pyproject / 打包 / 运行期自动跟随。

脚本同时：
    - 更新 docs/CHANGELOG.md：把「未发布」的重构内容提升为「## [新版本] - <今天>」章节，
      并重置「未发布」区块（Keep a Changelog 惯例，Release 正文从此章节生成）
    - 同步 docs/INSTALL.md / UPDATE.md / USAGE.md 里安装/重装命令的示例版本号
      （`--version vX` / `-Version vX` / `reinstall --version vX`）
    - 提示需要手动核对的展示性示例（如 UPDATE.md 的「有新版本可用」对比行）

版本号必须符合语义化版本 X.Y.Z（可选 prerelease 如 0.0.6-rc.1）。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import NoReturn

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "src" / "sshm" / "_version.txt"
CHANGELOG = ROOT / "docs" / "CHANGELOG.md"
# 需同步命令示例版本号的文档（install / reinstall 的 --version vX）
DOCS_VERSIONED = [
    ROOT / "docs" / "INSTALL.md",
    ROOT / "docs" / "UPDATE.md",
    ROOT / "docs" / "USAGE.md",
]

# 命令示例中的版本号写法：--version v0.0.5 / -V v0.0.5 / -Version v0.0.5
_VERSION_RE = re.compile(r"((?:--version|-V|-Version)\s*)v\d+\.\d+\.\d+(?:[-+][\w.]+)?")
# 语义化版本
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def fail(msg: str) -> "NoReturn":
    print(f"❌ {msg}", file=sys.stderr)
    sys.exit(1)


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, text=True, capture_output=True)


def current_version() -> str:
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def set_version_file(new_ver: str) -> None:
    VERSION_FILE.write_text(f"{new_ver}\n", encoding="utf-8")
    print(f"✅ src/sshm/_version.txt → {new_ver}")


def update_changelog(new_ver: str, old_ver: str) -> None:
    """把「未发布」的重构内容提升为新版本章节，并重置「未发布」区块。"""
    text = CHANGELOG.read_text(encoding="utf-8")
    lines = text.splitlines()

    # 定位「## [未发布]」区块边界（下一个 `## [` 之前的全部行）
    try:
        unrel_idx = lines.index("## [未发布]")
    except ValueError:
        fail("CHANGELOG 中找不到「## [未发布]」区块")

    next_idx = None
    for i in range(unrel_idx + 1, len(lines)):
        if lines[i].startswith("## [") and not lines[i].startswith("## [未发布]"):
            next_idx = i
            break
    if next_idx is None:
        fail("「未发布」区块后找不到下一个版本章节（无法确定边界）")

    unrel_body = "\n".join(lines[unrel_idx + 1 : next_idx]).rstrip()
    # 移除未发布正文末尾的「### 规划中 ...」计划项，只保留已实现内容
    plan_pos = unrel_body.find("### 规划中")
    if plan_pos != -1:
        unrel_body = unrel_body[:plan_pos].rstrip()

    today = date.today().isoformat()
    new_section = (
        f"## [{new_ver}] - {today}\n"
        f"\n"
        f"{unrel_body}\n"
        f"\n"
        f"### 📝 文档\n"
        f"\n"
        f"- 文档与版本号同步至 v{new_ver}（INSTALL / UPDATE 安装示例）"
    )
    # 重置未发布区块（保留规划中）
    reset_unrel = (
        f"## [未发布]\n"
        f"\n"
        f"### 规划中\n"
        f"\n"
        f"- [ ] SSH Agent 管理\n"
        f"- [ ] 密钥导入/导出\n"
        f"- [ ] 远程备份与云同步\n"
        f"- [ ] 团队协作与密钥安全扫描"
    )

    new_text = (
        "\n".join(lines[:unrel_idx]).rstrip()
        + "\n\n"
        + reset_unrel
        + "\n\n---\n\n"
        + new_section
        + "\n\n---\n\n"
        + "\n".join(lines[next_idx:]).lstrip("\n")
        + "\n"
    )
    CHANGELOG.write_text(new_text, encoding="utf-8")
    print(f"✅ docs/CHANGELOG.md 新增章节 [{new_ver}]（移动「未发布」重构内容）")


def sync_doc_versions(new_ver: str, old_ver: str) -> None:
    """同步文档中命令示例的版本号 v{old} → v{new}。"""
    for path in DOCS_VERSIONED:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        replaced = _VERSION_RE.sub(lambda m: f"{m.group(1)}v{new_ver}", text)
        count = text.count(f"v{old_ver}") - replaced.count(f"v{old_ver}")
        if replaced != text:
            path.write_text(replaced, encoding="utf-8")
            print(f"✅ {path.relative_to(ROOT)} 同步命令示例版本 v{new_ver}")
        elif text.count(f"v{old_ver}") == 0:
            # 无旧版本命令示例（可能已是最新）
            pass


def manual_review_hints(old_ver: str, new_ver: str) -> None:
    """提示需要手动核对的展示性版本号（非命令示例，脚本不自动改）。"""
    hints = []
    # UPDATE.md 的「有新版本可用: vX (当前: vY)」对比展示
    upd = ROOT / "docs" / "UPDATE.md"
    if upd.exists():
        text = upd.read_text(encoding="utf-8")
        m = re.search(r"有新版本可用:\s*v[\d.]+.*?当前:\s*v([\d.]+)", text)
        if m and m.group(1) == old_ver:
            hints.append(
                f"docs/UPDATE.md 的「有新版本可用 (当前: v{old_ver})」展示示例需手动核对，"
                f"建议将「当前」更新为 v{new_ver} 并设定新的未来版本占位。"
            )
    if hints:
        print("\n⚠️  请手动核对：")
        for h in hints:
            print(f"   - {h}")


def _tag_exists(tag: str) -> bool:
    """本地 tag 是否已存在。"""
    proc = run(["git", "rev-parse", "--verify", f"refs/tags/{tag}"], check=False)
    return proc.returncode == 0


def _delete_local_tag(tag: str) -> None:
    run(["git", "tag", "-d", tag], check=True)
    print(f"   🗑️  已删除本地 tag {tag}")


def _delete_remote_tag(tag: str) -> None:
    """删除远端 tag（幂等：远端 tag 不存在时 `--delete` 会报错，忽略）。"""
    proc = run(["git", "push", "origin", f":refs/tags/{tag}"], check=False)
    if proc.returncode == 0:
        print(f"   🗑️  已删除远端 tag {tag}")
    else:
        # 远端本就没有该 tag（如从未推送过）属正常，不当作错误
        print(f"   ℹ️  远端无 tag {tag} 或删除跳过：{proc.stderr.strip()[:80]}")


def git_tag(new_ver: str, push: bool) -> None:
    tag = f"v{new_ver}"
    # 校验当前 git 状态（不应有未提交改动）
    status = run(["git", "status", "--porcelain"], check=False).stdout.strip()
    if status:
        print(f"\n⚠️  存在未提交改动，先提交后再打 tag：\n{status}")
        sys.exit(1)

    if _tag_exists(tag):
        # tag 已存在：询问是否重新打（删除本地 + 远端旧 tag 再打新）
        print(f"\n⚠️  本地已存在 tag {tag}（指向 {_tag_commit(tag)}）")
        answer = input(f"   是否重新打该 tag（删除本地+远端旧 tag，指向当前提交）？[y/N]: ").strip().lower()
        if answer not in ("y", "yes"):
            print(f"ℹ️  保留现有 tag {tag}，不重新打。")
            if push:
                _push_branch()
                _push_tag(tag)
            return
        _delete_local_tag(tag)
        if push:
            _delete_remote_tag(tag)
        elif input("   是否同时删除远端旧 tag？[y/N]: ").strip().lower() in ("y", "yes"):
            _delete_remote_tag(tag)

    run(["git", "tag", tag], check=True)
    print(f"✅ 已打 git tag {tag}")
    if push:
        # 先推送当前分支（确保远端主干拿到全部提交），再推送 tag 触发 CI，
        # 避免只推 tag 而远端 main 仍落后于本地
        _push_branch()
        _push_tag(tag)


def _tag_commit(tag: str) -> str:
    proc = run(["git", "rev-list", "-n", "1", tag], check=False)
    return proc.stdout.strip()[:12] if proc.returncode == 0 else "?"


def _current_branch() -> str:
    proc = run(["git", "branch", "--show-current"], check=True)
    return proc.stdout.strip()


def _push_branch() -> None:
    """推送当前分支到远端（确保远端主干拿到全部提交）。"""
    branch = _current_branch()
    if not branch:
        print("⚠️  无法确定当前分支，跳过分支推送。")
        return
    run(["git", "push", "origin", branch], check=True)
    print(f"✅ 已推送分支 {branch} 到远端")


def _push_tag(tag: str) -> None:
    run(["git", "push", "origin", tag], check=True)
    print(f"✅ 已推送 tag {tag}（触发 CI 构建发版）")


def _setup_console() -> None:
    """Windows 下重配 stdout/stderr 为 UTF-8，避免 GBK 无法编码 emoji/中文。"""
    for stream in (sys.stdout, sys.stderr):
        # sys.stdout 类型为 TextIO，reconfigure 是 io.TextIOWrapper 的实例方法，
        # 用 getattr 规避类型标注差异（非 TextIOWrapper 的流会抛 AttributeError）
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def main() -> None:
    _setup_console()
    parser = argparse.ArgumentParser(description="sshm 一键发版脚本")
    parser.add_argument("version", help="目标版本号，如 0.0.6")
    parser.add_argument("--tag", action="store_true", help="修改文件后打 git tag")
    parser.add_argument("--push", action="store_true", help="修改文件后打 tag 并 push（触发 CI）")
    args = parser.parse_args()

    raw_ver = args.version.strip()
    # 宽容处理：自动剥离合法的 v/V 前缀（如 v0.0.6 / V0.0.6 → 0.0.6）。
    # 脚本内部统一用裸版本号（_version.txt / CHANGELOG / 比较都用无前缀），
    # 只在打 tag 时自行加 v 前缀，避免 v 前缀写进 _version.txt 破坏版本解析。
    new_ver = raw_ver.lstrip("vV")
    if not _SEMVER_RE.match(new_ver):
        fail(f"版本号格式错误：{raw_ver!r}（应为 X.Y.Z，可选 prerelease/build）")

    old_ver = current_version()
    if new_ver == old_ver:
        if args.tag or args.push:
            # 版本已是最新：跳过文件修改，直接打 tag。
            # 用于「上一轮发版只改了文件、未打 tag，现在补打 tag 触发 CI」的场景。
            print(f"ℹ️  版本已是 v{old_ver}，跳过文件修改，直接打 tag。")
            git_tag(new_ver, push=args.push)
            return
        fail(f"当前已是版本 {old_ver}，无需发版")

    print(f"🔀 发版：v{old_ver} → v{new_ver}\n")
    set_version_file(new_ver)
    update_changelog(new_ver, old_ver)
    sync_doc_versions(new_ver, old_ver)
    manual_review_hints(old_ver, new_ver)

    print(f"\n📋 发版文件修改完成（v{old_ver} → v{new_ver}）。请审查后提交。")
    if args.tag or args.push:
        git_tag(new_ver, push=args.push)
    else:
        print("  提交后如需打 tag 触发 CI：python scripts/release.py <版本> --tag（或 --push）")


if __name__ == "__main__":
    main()
