#!/usr/bin/env python3
"""
CLI 输出标准化快照 / 回归检查脚本。

自动导出所有 CLI 指令（从 cli.registry），生成场景，执行并收集输出，
校验输出是否符合预期（退出码 / 无 Traceback / 关键格式）。

场景类型：
  1. 分组默认查看（无子命令，如 `sshm key`）
  2. 每个命令的 --help
  3. 非法参数校验（Enum 自动拦截，应优雅报错而非 Traceback）

用法:
    python scripts/cli_snapshot.py            # 默认：生成 en/zh 两份汇总报告
    python scripts/cli_snapshot.py --check                  # 校验输出符合标准（默认）

可重复运行，用于快速排查 CLI 输出回归/标准化问题。

输出报告（--collect，按语言汇总成一份文件，方便 AI 比对）：
    tests/_cli_snapshot/cli_report_en.txt   英文语言汇总报告
    tests/_cli_snapshot/cli_report_zh.txt   中文语言汇总报告
    --lang 控制：en / zh / both（默认 both 生成两份）
"""

from __future__ import annotations

import argparse
import datetime
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
OUT_DIR = ROOT / "tests" / "_cli_snapshot"

# 非法参数/未知命令场景：(命令参数, 说明) —— 期望优雅报错（非零退出、无 Traceback）
INVALID_SCENARIOS = [
    # 参数枚举校验（Typer/Click 原生拦截）
    (["config", "language", "invalidlang"], "config language 非法值应被 Enum 拦截"),
    (["config", "auto-author", "invalid"], "config auto-author 非法开关值应被拦截"),
    (
        ["key", "create", "x", "y@z.com", "--type", "invalid"],
        "key create 非法 type 应被 Enum 拦截",
    ),
    (["auto-author", "invalid"], "非法开关值应被拦截（兼容旧入口）"),
    # 未知命令建议（我的 cli.suggest 层级预校验）
    (["list"], "未知顶层命令应给出建议（list → key/backup/author list）"),
    (["key", "lst"], "组内未知子命令应给出建议（lst → list）"),
    (["key", "lst", "--all"], "组内未知子命令 + 选项：应给建议、忽略选项"),
    (["key", "lst", "somearg"], "组内未知子命令 + 位置参数：应给建议"),
    (["keyz"], "顶层分组拼写错误应建议相近分组（keyz → key）"),
    (["repo", "lst"], "另一分组内未知子命令：无相近则提示查看 --help"),
    # 选项错误（统一模板渲染，保留 Click 的建议文案）
    (["--versoin"], "全局选项拼错应被建议（--versoin → --version）"),
    (["-x"], "未知全局选项应优雅报错"),
    (["key", "list", "--al"], "组内选项拼错应被列出可能选项（--al → --all）"),
    # 缺必填参数（走 render_usage_error 统一模板，取代 Click 原生面板）
    (["key", "switch"], "缺必填参数 LABEL：统一 ❌ 渲染 + 用法提示"),
    (["repo", "use"], "缺必填参数 LABEL：统一 ❌ 渲染 + 用法提示"),
    # 选项缺值（同样应优雅报错）
    (["key", "create", "x", "y@z.com", "--type"], "选项 --type 缺值应优雅报错"),
    # 需至少一个匹配选项（history rewrite 缺 --name/--email/--author）
    (["history", "rewrite"], "history rewrite 无匹配条件：统一 ❌ 渲染 + 用法提示"),
    (
        ["history", "rewrite", "--author", "alice", "--name", "Old:New"],
        "history rewrite 互斥参数应优雅报错（--author 与 --name/--email 不能混用）",
    ),
    (
        ["author", "update", "work"],
        "author update 缺 --name/--email：统一 ❌ 渲染 + 用法提示",
    ),
    # 未知子命令（注意：author 组无 set，属"未知子命令"而非"缺必填参数"）
    (["author", "set"], "author 组未知子命令 set 应给建议"),
]

LANGS = ("en", "zh")


def _load_registry():
    """从 cli.registry 加载 GROUPS（分组 -> 命令名列表）。"""
    sys.path.insert(0, str(SRC))
    from sshm.cli import registry

    groups = {}
    for group, metas in registry.GROUPS.items():
        groups[group] = [m.name for m in metas]
    return groups, list(registry.GROUP_ORDER)


def _run(args: list) -> subprocess.CompletedProcess:
    """运行 `python -m sshm <args>`，UTF-8 收集输出。

    显式把仓库 src 放入 PYTHONPATH：确保校验的是当前仓库源码，而非环境里
    已安装的其它副本（避免被别的 editable 安装 / 残留环境变量遮蔽）。
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "sshm"] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        cwd=str(ROOT),
        env=env,
    )


def _snapshot_jobs() -> int:
    """并行 worker 数：默认 CPU 核数，可用 SSHM_SNAPSHOT_JOBS 覆盖（0=串行）。"""
    try:
        return max(1, int(os.environ.get("SSHM_SNAPSHOT_JOBS", os.cpu_count() or 4)))
    except ValueError:
        return 4


def _run_scenarios(scenarios, handler) -> list:
    """并行执行所有场景，返回按原顺序的 handler 结果列表。

    每个场景是独立的 subprocess 调用（_run），线程池安全且可显著加速。
    """
    jobs = _snapshot_jobs()
    if jobs == 1 or len(scenarios) <= 1:
        return [handler(argv, label, succeed) for argv, label, succeed in scenarios]
    results = [None] * len(scenarios)
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        future_map = {ex.submit(handler, argv, label, succeed): i for i, (argv, label, succeed) in enumerate(scenarios)}
        for fut in as_completed(future_map):
            idx = future_map[fut]
            results[idx] = fut.result()
    return results


def _set_lang(lang: str) -> None:
    """设置输出语言（en/zh），确保收集时语言一致。"""
    subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "sshm", "config", "language", lang],
        capture_output=True,
        timeout=10,
        cwd=str(ROOT),
    )


def _build_scenarios(groups, group_order):
    """生成所有场景：(args, 标签, 是否应成功)。"""
    scenarios = []
    for group in group_order:
        scenarios.append(([group], f"{group} 分组默认查看", True))
        scenarios.append(([group, "--help"], f"{group} 分组 --help", True))
        for cmd in groups.get(group, []):
            scenarios.append(([group, cmd, "--help"], f"{group} {cmd} --help", True))
    # 额外回归场景：抓取"统一 tip 段"模板的真实渲染（命令底部 + 错误建议
    # 共用 render_tip_block，必须有快照覆盖以防模板漂移）
    for args in EXTRA_VIEW_SCENARIOS:
        scenarios.append((list(args), f"{args} 默认视图", True))
    scenarios.append((["--help"], "顶层 --help", True))
    scenarios.append((["--version"], "顶层 --version", True))
    for args, label in INVALID_SCENARIOS:
        scenarios.append((args, label, False))
    return scenarios


# 选取若干代表性子命令，专门覆盖底部统一 tip 段（render_tip_block）的真实渲染
EXTRA_VIEW_SCENARIOS = [
    ("key", "list"),  # 用户截图原场景：两条 tip 段（操作提示 + 相关命令）
    ("repo", "info"),  # 默认视图的另一形态
]


def _validate(name, out, err, code, should_succeed):
    """校验单个场景的输出是否符合标准。返回 (ok, 问题列表)。"""
    problems = []
    combined = out + err
    if should_succeed and code != 0:
        problems.append(f"退出码 {code}（应成功 0）")
    if not should_succeed and code == 0:
        problems.append("退出码 0（非法值应被拦截非零退出）")
    if "Traceback" in combined:
        problems.append("包含 Traceback")
    if "Internal Server Error" in combined:
        problems.append("内部错误")
    if should_succeed and not out.strip():
        problems.append("输出为空")
    # 关键格式断言（防止样式回归，而不仅是"非黑"检查）：
    # - 所有 --help 场景必须给出 Usage 行
    # - 所有失败场景必须走统一 ❌ 错误标记（而非原生面板/裸报错）
    if "--help" in name:
        if should_succeed and "Usage:" not in out:
            problems.append("--help 场景缺少 Usage: 行")
    elif not should_succeed:
        if "❌" not in combined:
            problems.append("错误场景缺少统一 ❌ 错误标记")
        else:
            # 反裸 ❌：错误场景走统一渲染时必须带 💡 引导提示，
            # 否则用户不知道下一步该怎么做（如查看可用 label / --help）。
            # 用户主动取消（cancelled/取消）属于合法无引导，放行。
            has_hint = "💡" in combined
            is_cancel = ("cancelled" in combined.lower()) or ("取消" in combined)
            if not has_hint and not is_cancel:
                problems.append("错误场景有 ❌ 但缺少统一 💡 引导提示（裸报错）")
    return (len(problems) == 0, problems)


def _collect_report(lang: str) -> Path:
    """执行所有场景，汇总成一份结构化报告文件（按语言）。"""
    groups, group_order = _load_registry()
    scenarios = _build_scenarios(groups, group_order)
    # 记录原语言，收集完成后恢复，避免改变用户环境
    prev_lang = _get_lang()
    _set_lang(lang)

    try:
        return _do_collect(lang, scenarios)
    finally:
        _set_lang(prev_lang)


def _get_lang() -> str:
    """读取当前输出语言（en/zh）。"""
    try:
        sys.path.insert(0, str(SRC))
        from sshm.i18n import get_lang

        return get_lang()
    except Exception:
        return "en"


def _clean_residual() -> None:
    """清理快照目录下残留的零散文件（旧 .out/.err），保留汇总报告 cli_report_*.txt。

    避免旧零散文件干扰比对，确保目录只含最新的汇总报告。
    """
    if not OUT_DIR.exists():
        return
    for f in OUT_DIR.iterdir():
        if f.is_file() and f.suffix in (".out", ".err"):
            try:
                f.unlink()
            except OSError:
                pass


def _do_collect(lang: str, scenarios) -> Path:
    """实际执行收集并写入报告。"""
    _clean_residual()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = OUT_DIR / f"cli_report_{lang}.txt"
    lines = []
    lines.append("=" * 72)
    lines.append(f"sshm CLI 输出快照汇总 (语言: {lang})")
    lines.append(f"生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"场景数: {len(scenarios)}")
    lines.append("=" * 72)
    lines.append("")

    def _handler(argv, label, _succeed):
        """收集单个场景输出，返回 (命令, 场景, 退出码, 输出行, stderr 行)。"""
        proc = _run(argv)
        cmd = "sshm " + " ".join(argv) if argv else "sshm"
        return (
            cmd,
            label,
            proc.returncode,
            proc.stdout.strip().splitlines() or ["(空)"],
            proc.stderr.strip().splitlines(),
        )

    for cmd, label, code, out, err in _run_scenarios(scenarios, _handler):
        lines.append("-" * 72)
        lines.append(f"[命令] {cmd}")
        lines.append(f"[场景] {label}")
        lines.append(f"[退出码] {code}")
        lines.append("[输出]")
        for line in out:
            lines.append(f"  | {line}")
        if err:
            lines.append("[stderr]")
            for line in err:
                lines.append(f"  | {line}")
        lines.append("")

    report.write_text("\n".join(lines), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="CLI 输出标准化快照/回归检查")
    parser.add_argument("--check", action="store_true", help="校验输出符合标准（供 check_all.py 调用）")
    parser.add_argument(
        "--lang",
        choices=["en", "zh", "both"],
        default="both",
        help="收集报告的语言（默认 both 生成 en/zh 两份）",
    )
    args = parser.parse_args()

    if not args.check:
        # 默认行为：生成 en/zh 汇总报告
        langs = LANGS if args.lang == "both" else (args.lang,)
        for lang in langs:
            report = _collect_report(lang)
            print(f"已生成 {lang} 报告: {report.relative_to(ROOT)}")
        return 0

    # check 模式（显式 --check，不切换语言，用当前环境语言）
    groups, group_order = _load_registry()
    scenarios = _build_scenarios(groups, group_order)
    print(f"共 {len(scenarios)} 个场景\n")

    failures = 0

    def _checker(argv, label, should_succeed):
        proc = _run(argv)
        ok, problems = _validate(label, proc.stdout, proc.stderr, proc.returncode, should_succeed)
        return (
            label,
            proc.returncode,
            ok,
            problems,
            (proc.stdout or proc.stderr).strip().splitlines(),
        )

    for label, code, ok, problems, snippet in _run_scenarios(scenarios, _checker):
        status = "OK " if ok else "XX "
        print(f"[{status}] {label}: exit={code}")
        if not ok:
            failures += 1
            for p in problems:
                print(f"       - {p}")
            for line in snippet[:5]:
                print(f"       | {line}")

    print()
    if failures:
        print(f"[X] {failures}/{len(scenarios)} 个场景不符合标准")
        return 1
    print(f"[OK] 全部 {len(scenarios)} 个场景通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
