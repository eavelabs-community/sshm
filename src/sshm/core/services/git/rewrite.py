"""Git 历史作者重写模块（纯 Python 实现，不依赖外部 filter-repo/filter-branch）

使用 git fast-export / fast-import 流协议：
1. `git fast-export --all` 导出完整历史（含 author/committer 信息）
2. Python 按「字节」解析流，对命令层的 author/committer 行进行替换；
   `data <n>` 块是字节计数的、内容可为任意二进制，必须原样复制
3. `git fast-import` 导入重写后的流
4. 原 refs 先备份到 refs/original/，避免历史丢失

适用于 sshm 打包分发（无 Python 环境），无需额外安装任何工具。

关键正确性约束（曾因违反导致 fast-import 崩溃）：
- fast-export 流必须按原始字节处理，绝不能用文本 + errors="replace" 读写。
  仓库历史中的二进制 blob 含非法 UTF-8 字节，一旦经 decode(→U+FFFD)+encode
  往返，字节数会变化，而 `data <n>` 仍声明旧字节数，fast-import 读偏移后
  报 `fatal: unsupported command`。
- 不能对整条流做 CRLF 归一化：那同样会改变 data 块字节数。
- author/committer 只存在于命令层（commit 头部），data 块内容可能恰好长得像
  author 行，必须用状态机跳过 data 块，避免误重写并破坏字节数。
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Iterator
from pathlib import Path

# author/committer 行示例：
#   author Alice <alice@x.com> 1786862590 +0800
#   committer Bob <bob@y.com> 1786862590 +0800
# 解析：前缀(author|committer) + 姓名(可能含空格，到 < 为止) + <邮箱> + 时间戳 + 时区
# 用 bytes 正则，仅用于命令层（data 块已被跳过）。
_PERSON_LINE = re.compile(
    rb"^(?P<kind>author|committer) "
    rb"(?P<name>(?:[^<]|\\.)+) "
    rb"<(?P<email>[^>]*)>"
    rb"(?P<rest>[ \t].*)$"
)
# `data <count>`：其后紧跟恰好 count 个原始字节（内容可为任意二进制）+ 一个 \n 分隔
_DATA_COUNT = re.compile(rb"^data (\d+)$")
# `data <<DELIM`（fast-export 一般不用，但为稳妥支持）：直到独立 DELIM 行结束
_DATA_DELIM = re.compile(rb"^data <<(?P<delim>\S+)$")


class RewriteConfig:
    """一次历史重写的匹配/替换规则。所有字段均可选。"""

    def __init__(
        self,
        old_name: str | None = None,
        new_name: str | None = None,
        old_email: str | None = None,
        new_email: str | None = None,
        match_all: bool = False,
    ):
        self.old_name = old_name
        self.new_name = new_name
        self.old_email = old_email
        self.new_email = new_email
        # match_all：无 old 条件，把历史所有作者/邮箱统一为 new_name/new_email
        self.match_all = match_all


# 会被外部 git 环境劫持、导致 `-C <repo>` 指定的仓库失效或作者被覆盖的环境变量。
# 典型场景：在 git hook（如 pre-commit）内运行本工具/测试时，git 会设置
# GIT_DIR、GIT_INDEX_FILE、GIT_AUTHOR_*/GIT_COMMITTER_* 等变量，即使显式
# `-C <repo>`，这些变量仍会让 git 指向错误位置或覆盖仓库作者，造成重写不生效
# 或操作落到当前项目仓库。这里移除所有 GIT_* 前缀变量（GIT_PAGER/GIT_EXEC_PATH
# 等不影响仓库定位，一并清除也无妨），保证操作始终作用于目标仓库。
def _clean_git_env() -> dict:
    """返回移除了全部 GIT_* 污染变量后的环境副本（保留其它变量）。"""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _run_git(
    repo: Path,
    args: list,
    input_bytes: bytes | None = None,
    input_text: str | None = None,
    capture: bool = True,
    binary_output: bool = False,
) -> subprocess.CompletedProcess:
    """在指定仓库执行 git 命令。

    - input_bytes：以原始 bytes 写入 stdin（用于 fast-import，绝不经过文本层，
      否则 Windows 换行转换或 UTF-8 往返会破坏 data 块字节数）
    - input_text：可选文本 stdin（仅用于无二进制内容的命令）
    - binary_output：为 True 时以原始 bytes 读取 stdout（用于 fast-export，
      避免 errors="replace" 把二进制 blob 内容改坏）
    - 统一使用干净 env，屏蔽外部 GIT_DIR 等环境变量干扰
    """
    cmd = ["git", "-C", str(repo)] + args
    env = _clean_git_env()
    if input_bytes is not None:
        return subprocess.run(cmd, input=input_bytes, capture_output=capture, env=env)
    if input_text is not None:
        return subprocess.run(
            cmd,
            input=input_text,
            capture_output=capture,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    if binary_output:
        return subprocess.run(cmd, capture_output=capture, env=env)
    return subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def _walk_person_lines(stream: bytes) -> Iterator[tuple[int, int, re.Match]]:
    """逐字节遍历 fast-export 流，仅 yield 命令层的 author/committer 行。

    yield (行起始字节下标, 行结束字节下标, 匹配对象)。
    data 块内容原样跳过，绝不到达 person 匹配分支。
    """
    n = len(stream)
    i = 0
    while i < n:
        nl = stream.find(b"\n", i)
        line_end = (nl + 1) if nl != -1 else n
        content = stream[i : nl if nl != -1 else n]

        dm = _DATA_COUNT.match(content)
        if dm:
            count = int(dm.group(1))
            i = nl + 1 + count  # 跳过 count 个原始字节
            if i < n and stream[i : i + 1] == b"\n":
                i += 1  # 跳过 data 后的 \n 分隔符
            continue

        dm2 = _DATA_DELIM.match(content)
        if dm2:
            delim = dm2.group("delim")
            j = nl + 1
            while j < n:
                lf = stream.find(b"\n", j)
                if lf == -1:
                    j = n
                    break
                if stream[j:lf] == delim:
                    j = lf + 1
                    break
                j = lf + 1
            i = j
            continue

        m = _PERSON_LINE.match(content)
        if m:
            yield i, line_end, m
        i = line_end


def _count_matches(stream: bytes, cfg: RewriteConfig) -> int:
    """统计流中命令层匹配旧作者/邮箱的提交行数（用于预览与结果确认）。

    match_all 时统计所有命令层作者/提交者行（全量刷新）。
    data 块内容不计入，避免误判二进制里恰好形似 author 的片段。
    """
    count = 0
    for _s, _e, m in _walk_person_lines(stream):
        if cfg.match_all:
            count += 1
            continue
        name = m.group("name")
        email = m.group("email")
        if cfg.old_name and name == cfg.old_name.encode("utf-8") or cfg.old_email and email == cfg.old_email.encode("utf-8"):
            count += 1
    return count


def _rewrite_stream(stream: bytes, cfg: RewriteConfig) -> tuple[bytes, int]:
    """字节级重写 fast-export 流，返回 (新流 bytes, 替换次数)。

    data 块按原始字节整体复制，命令层 author/committer 行按规则替换。
    """
    out = bytearray()
    replaced = 0
    n = len(stream)
    i = 0
    while i < n:
        nl = stream.find(b"\n", i)
        line_end = (nl + 1) if nl != -1 else n
        content = stream[i : nl if nl != -1 else n]

        dm = _DATA_COUNT.match(content)
        if dm:
            count = int(dm.group(1))
            out += stream[i : nl + 1]  # 'data <n>\n'
            out += stream[nl + 1 : nl + 1 + count]  # 原样复制 count 个原始字节
            i = nl + 1 + count
            if i < n and stream[i : i + 1] == b"\n":
                out += b"\n"
                i += 1
            continue

        dm2 = _DATA_DELIM.match(content)
        if dm2:
            delim = dm2.group("delim")
            j = nl + 1
            end = n
            while j < n:
                lf = stream.find(b"\n", j)
                if lf == -1:
                    end = n
                    break
                if stream[j:lf] == delim:
                    end = lf + 1
                    break
                j = lf + 1
            out += stream[i:end]
            i = end
            continue

        m = _PERSON_LINE.match(content)
        if m:
            name = m.group("name")
            email = m.group("email")
            new_name = name
            new_email = email
            hit = False
            if cfg.match_all:
                # 全量刷新：所有作者/提交者统一为 new_name/new_email
                if cfg.new_name is not None:
                    new_name = cfg.new_name.encode("utf-8")
                if cfg.new_email is not None:
                    new_email = cfg.new_email.encode("utf-8")
                hit = True
            elif cfg.old_name and name == cfg.old_name.encode("utf-8"):
                if cfg.new_name is not None:
                    new_name = cfg.new_name.encode("utf-8")
                hit = True
            elif cfg.old_email and email == cfg.old_email.encode("utf-8"):
                if cfg.new_email is not None:
                    new_email = cfg.new_email.encode("utf-8")
                hit = True
            if hit:
                replaced += 1
                rest = m.group("rest")
                out += m.group("kind") + b" " + new_name + b" <" + new_email + b">" + rest + b"\n"
            else:
                out += stream[i:line_end]
        else:
            out += stream[i:line_end]
        i = line_end

    return bytes(out), replaced


def _active_refs(repo: Path) -> list:
    """返回所有「真实」refs，排除 refs/original/ 备份命名空间。

    refs/original/ 是历史重写产生的备份（git filter-branch 同款约定），
    不属于真实历史。若 fast-export / git log --all 误包含它，会导致：
    重写后旧作者仍能通过 --all 查到、matched 计数反复命中备份旧历史。
    """
    refs = _run_git(repo, ["for-each-ref", "--format=%(refname)"])
    if refs.returncode != 0:
        return []
    return [r for r in refs.stdout.splitlines() if r and not r.startswith("refs/original/")]


def _backup_refs(repo: Path) -> None:
    """把当前所有活跃 refs 备份到 refs/original/，避免重写后历史丢失。

    镜像路径语义：
      refs/heads/main        -> refs/original/main
      refs/tags/v1.0         -> refs/original/tags/v1.0
      refs/remotes/origin/x  -> refs/original/refs/remotes/origin/x
    """
    for ref in _active_refs(repo):
        if ref.startswith("refs/heads/"):
            target = "refs/original/" + ref[len("refs/heads/") :]
        elif ref.startswith("refs/tags/"):
            target = "refs/original/tags/" + ref[len("refs/tags/") :]
        else:
            target = "refs/original/" + ref
        _run_git(repo, ["update-ref", target, ref])


def _update_current_branch(repo: Path) -> None:
    """fast-import 更新 refs/heads/* 后，把 HEAD 重新挂回当前分支。

    fast-import 导入新历史后，HEAD 可能变成 detached（指向旧 ref 或游离状态）。
    这里稳健地恢复到原分支：优先用 symbolic-ref，失败则从 refs/heads 推断。
    """
    branch = _current_branch_name(repo)
    if not branch:
        # 无法确定当前分支，尝试 main/master 兜底
        for cand in ("main", "master"):
            if (repo / ".git").exists():
                chk = _run_git(repo, ["rev-parse", "--verify", f"refs/heads/{cand}"])
                if chk.returncode == 0:
                    branch = cand
                    break
    if branch:
        _run_git(repo, ["checkout", "-f", branch])


def _current_branch_name(repo: Path) -> str:
    """返回 HEAD 当前所在分支名；若 detached 返回空字符串。"""
    # 先尝试 symbolic-ref（正常挂载时可用）
    sym = _run_git(repo, ["symbolic-ref", "--quiet", "HEAD"])
    if sym.returncode == 0:
        ref = sym.stdout.strip()
        if ref.startswith("refs/heads/"):
            return ref[len("refs/heads/") :]
        return ""
    # detached：尝试解析 HEAD 指向的 commit 属于哪个分支
    name = _run_git(repo, ["name-rev", "--name-only", "HEAD"])
    if name.returncode == 0:
        n = name.stdout.strip()
        # 格式如 "main"、"main~1"、"tags/v0.0.1^0"
        if "~" in n or "^" in n:
            n = n.split("~")[0].split("^")[0]
        if n and not n.startswith("tags/"):
            return n
    return ""


def rewrite_history(repo_path: Path, cfg: RewriteConfig, *, original: bytes | None = None) -> dict:
    """重写指定仓库的历史作者/邮箱。

    Args:
        repo_path: 仓库路径
        cfg: 重写规则
        original: 可选，已用 fast-export 导出的原始字节流。命令层预览已导出
            一次，可传入复用，避免「预览 + 实际」重复导出完整历史。

    Returns:
        统计信息 dict：
            matched_commits: 匹配到旧作者/邮箱的提交数
            rewritten: 实际重写的行数
    """
    if cfg.match_all:
        # 全量刷新：无需 old 条件，但必须指定 new_name 或 new_email
        if not cfg.new_name and not cfg.new_email:
            raise ValueError("全量刷新模式需要提供 new_name 或 new_email")
    elif not cfg.old_name and not cfg.old_email:
        raise ValueError("old_name 和 old_email 至少需要一个")

    repo = Path(repo_path)

    # 1. 导出原始字节流（binary_output），统计受影响提交数。
    #    显式传入活跃 refs（排除 refs/original/ 备份）。不能依赖 `--all --exclude`
    #    （git 不会过滤 --all 预展开的 refs），否则旧备份历史会被反复重写，
    #    且 matched 计数会反复命中已重写过的旧提交。
    active = _active_refs(repo)
    if not active:
        return {"matched_commits": 0, "rewritten": 0}
    if original is None:
        export = _run_git(repo, ["fast-export"] + active, binary_output=True)
        if export.returncode != 0:
            raise RuntimeError(f"git fast-export failed: {export.stderr.decode('utf-8', 'replace').strip()}")
        original = export.stdout or b""
    stream: bytes = original

    matched = _count_matches(stream, cfg)
    if matched == 0:
        return {"matched_commits": 0, "rewritten": 0}

    # 2. 备份原 refs
    _backup_refs(repo)

    # 3. 字节级重写流（data 块原样保留，author/committer 替换）
    new_stream, replaced = _rewrite_stream(stream, cfg)

    # 4. 导入重写后的流（原始 bytes stdin，绝不经过文本层）
    imp = _run_git(repo, ["fast-import", "--quiet", "--force"], input_bytes=new_stream)
    if imp.returncode != 0:
        raise RuntimeError(f"git fast-import failed: {imp.stderr.decode('utf-8', 'replace').strip()}")

    # 5. 更新当前分支指向
    _update_current_branch(repo)

    return {"matched_commits": matched, "rewritten": replaced}


def get_authors_in_repo(repo_path: Path) -> list:
    """列出仓库历史中出现过的所有作者（用于预览，展示将影响谁）。"""
    repo = Path(repo_path)
    # 显式传活跃 refs（排除 refs/original/ 备份），避免列出重写前的旧作者
    active = _active_refs(repo)
    if not active:
        return []
    log = _run_git(repo, ["log"] + active + ["--format=%an <%ae>"])
    if log.returncode != 0:
        return []
    seen = {}
    for line in log.stdout.splitlines():
        if line and line not in seen:
            seen[line] = True
    return list(seen.keys())
