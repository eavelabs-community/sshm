#!/usr/bin/env python3
"""
死代码/冗余内容检测脚本。

检测以下类型的冗余：
  1. 废弃 i18n key：在 KEYS 中声明，但代码里从不被 `_("key")` 或 `K.xxx` 引用
  2. 已知死代码符号：OperationError / RichOutput / GROUP_DESCRIPTIONS /
     find_meta / command_group / CommandMeta.summary 等
  3. 空目录（如 src/sshm/utils/）

用法:
    python scripts/check_deadcode.py
退出码 0 表示无冗余，非 0 表示存在可清理的冗余内容。
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


# ---------------------------------------------------------------------------
# 1. 解析 i18n KEYS
# ---------------------------------------------------------------------------


def parse_i18n_keys() -> list[str]:
    """从 templates.py 解析 KEYS 中声明的所有 key。"""
    py = SRC / "sshm" / "language" / "templates.py"
    tree = ast.parse(py.read_text(encoding="utf-8"))
    keys: list[str] = []
    for node in tree.body:
        # 处理 KEYS: Tuple[str, ...] = (...)（AnnAssign）和 KEYS = (...)（Assign）
        target = None
        value = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target, value = node.target.id, node.value
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    target, value = t.id, node.value
        if target != "KEYS" or not isinstance(value, (ast.Tuple, ast.List, ast.Set)):
            continue
        for elt in value.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                keys.append(elt.value)
    return keys


def _collect_all_src_py() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py"))


def find_unused_i18n_keys(keys: list[str]) -> list[str]:
    """返回在业务代码中从未被引用的 i18n key。

    排除 language/ 目录（key 定义位置），并用 AST 精确检测实际引用：
    - `_(key)` / `_('key')` / `_(K.xxx)` 调用
    - `K.cmd.xxx` 属性访问（对应 key 'cmd.xxx'）
    避免把 docstring / 注释里的示例字符串误判为"使用"。
    """
    used_keys: set[str] = set()
    for p in _collect_all_src_py():
        if "language" in p.parts:
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            # 1. `_(key)` / `_('key')` 调用：第一个参数是字符串常量
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_" and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                used_keys.add(node.args[0].value)
            # 2. `K.cmd.xxx` 属性访问：拼接为 'cmd.xxx'
            if isinstance(node, ast.Attribute):
                parts: list[str] = []
                cur = node
                while isinstance(cur, ast.Attribute):
                    parts.append(cur.attr)
                    cur = cur.value
                if isinstance(cur, ast.Name) and cur.id == "K":
                    # 反转 parts 得到 'cmd.xxx'（K.cmd.xxx -> ['xxx','cmd']）
                    used_keys.add(".".join(reversed(parts)))
            # 3. 错误码体系：ErrorSpec(code, msg_key, hint_key, ...) 的参数字符串
            #    i18n key 通过 ERROR_REGISTRY 间接引用，需显式识别，否则会被误判为未使用。
            if isinstance(node, ast.Call):
                func_name = ""
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr
                if func_name == "ErrorSpec":
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            used_keys.add(arg.value)
    return [k for k in keys if k not in used_keys]


# ---------------------------------------------------------------------------
# 2. 已知死代码符号检测
# ---------------------------------------------------------------------------


def check_symbol_unused(symbol: str, defining_file_rel: str) -> bool:
    """检查某符号（类名/函数名/变量名）除定义文件外是否还有引用。

    返回 True 表示"确定无用"（除定义文件外无任何引用）。
    若符号在定义文件中已不存在（已被删除），返回 False（无需报告）。
    """
    defining_file = (SRC / defining_file_rel).resolve()
    if not defining_file.exists():
        return False
    # 符号必须仍在定义文件中存在，否则说明已清理，跳过
    defining_text = defining_file.read_text(encoding="utf-8")
    if not re.search(rf"\b{symbol}\b", defining_text):
        return False

    refs = 0
    for p in _collect_all_src_py():
        if p.resolve() == defining_file:
            continue
        text = p.read_text(encoding="utf-8")
        if re.search(rf"\b{symbol}\b", text):
            refs += 1
    # 也检查 tests 目录
    tests = ROOT / "tests"
    if tests.exists():
        for p in tests.rglob("*.py"):
            text = p.read_text(encoding="utf-8")
            if re.search(rf"\b{symbol}\b", text):
                refs += 1
    return refs == 0


# ---------------------------------------------------------------------------
# 3. 空目录检测
# ---------------------------------------------------------------------------


def find_empty_dirs() -> list[str]:
    """返回 src 下的空目录（不含任何文件）。"""
    empty = []
    IGNORE_DIRS = {"__pycache__", ".egg-info", ".git"}
    for d in SRC.rglob("*"):
        if d.is_dir() and d.name not in IGNORE_DIRS:
            # 只看是否有 .py 源文件（排除 __pycache__ 编译产物干扰）
            has_py = any(p.suffix == ".py" for p in d.rglob("*.py"))
            if not has_py:
                rel = d.relative_to(ROOT)
                empty.append(str(rel))
    return empty


# ---------------------------------------------------------------------------
# 3.5 i18n 占位符一致性：_('key', x=...) 传参与模板 {} 是否匹配
# ---------------------------------------------------------------------------


def check_i18n_placeholders() -> list[str]:
    """检测 `_('key', **kwargs)` 调用与 i18n 模板占位符的一致性。

    - 调用传了模板没有的占位符（多余）
    - 调用缺少模板需要的占位符（缺失）
    模板以 i18n_en.py 的 EN 字典为权威。
    """
    en_py = SRC / "sshm" / "language" / "i18n_en.py"
    try:
        tree = ast.parse(en_py.read_text(encoding="utf-8"))
    except OSError:
        return []
    templates: dict[str, set] = {}
    for node in tree.body:
        target = None
        value = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target, value = node.target.id, node.value
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    target, value = t.id, node.value
        if target == "EN" and isinstance(value, ast.Dict):
            for k, v in zip(value.keys, value.values):
                if isinstance(k, ast.Constant) and isinstance(v, ast.Constant) and isinstance(k.value, str) and isinstance(v.value, str):
                    templates[k.value] = set(re.findall(r"\{(\w+)\}", v.value))

    problems: list[str] = []
    for p in _collect_all_src_py():
        if "language" in p.parts:
            continue
        try:
            ptree = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, OSError):
            continue
        for node in ast.walk(ptree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_" and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                key = node.args[0].value
                if key not in templates:
                    continue
                kwargs = {kw.arg for kw in node.keywords if kw.arg}
                extra = kwargs - templates[key]
                missing = templates[key] - kwargs
                if extra:
                    problems.append(f"{p.name}:{node.lineno} - '{key}' has extra placeholder(s) {sorted(extra)} (template: {sorted(templates[key])})")
                if missing:
                    problems.append(f"{p.name}:{node.lineno} - '{key}' missing placeholder(s) {sorted(missing)} (template: {sorted(templates[key])})")
    return problems


# ---------------------------------------------------------------------------
# 4. basedpyright 未使用诊断（unused import / variable / function）
# ---------------------------------------------------------------------------


def run_basedpyright_unused() -> list[str]:
    """调用 basedpyright，解析其"未使用"相关诊断。

    返回形如 "file.py:12 - message" 的字符串列表。basedpyright 不可用时
    返回空列表（不阻断其他检测）。
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "basedpyright", "--outputjson", str(SRC)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []  # basedpyright 未安装或超时

    if proc.returncode not in (0, 1):
        return []

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []

    # 匹配"未使用"类诊断的关键词
    UNUSED_PATTERNS = (
        "is not accessed",
        "is not used",
        "is unused",
        'Import "',
        "imported but",
        "is never used",
        "is not read",
        "unused",
        "Unused",
    )
    unused = []
    for diag in data.get("generalDiagnostics", []):
        msg = diag.get("message", "")
        # 只保留 warning 及以上（error/warning），忽略 information
        severity = diag.get("severity", "")
        if severity not in ("error", "warning"):
            continue
        if any(p in msg for p in UNUSED_PATTERNS):
            f = diag.get("file", "")
            line = diag.get("range", {}).get("start", {}).get("line", 0) + 1
            rel = Path(f).name if f else "?"
            unused.append(f"{rel}:{line} - {msg}")
    return unused


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def main() -> int:
    problems: list[str] = []

    # 1. 废弃 i18n key
    keys = parse_i18n_keys()
    unused_keys = find_unused_i18n_keys(keys)
    if unused_keys:
        problems.append(f"[i18n] {len(unused_keys)} unused i18n key(s):")
        for k in sorted(unused_keys):
            problems.append(f"    - {k}")

    # 2. 已知死代码符号
    dead_symbols = [
        ("OperationError", "sshm/core/errors.py"),
        ("RichOutput", "sshm/ui/output.py"),
        ("GROUP_DESCRIPTIONS", "sshm/cli/registry.py"),
        ("find_meta", "sshm/cli/registry.py"),
        ("command_group", "sshm/cli/registry.py"),
    ]
    for symbol, f in dead_symbols:
        if check_symbol_unused(symbol, f):
            problems.append(f"[dead-symbol] '{symbol}' ({f}) has no external references")

    # 3. CommandMeta.summary 字段（仅当字段仍存在时检测是否被读取）
    registry_py = SRC / "sshm" / "cli" / "registry.py"
    if registry_py.exists() and re.search(r"\bsummary\b", registry_py.read_text(encoding="utf-8")):
        summary_used = any(re.search(r"\.summary\b", p.read_text(encoding="utf-8")) for p in _collect_all_src_py())
        if not summary_used:
            problems.append("[dead-field] CommandMeta.summary is never read")

    # 3.5 i18n 占位符一致性
    ph_problems = check_i18n_placeholders()
    if ph_problems:
        problems.append(f"[i18n-placeholder] {len(ph_problems)} placeholder mismatch(es):")
        for pp_ in ph_problems:
            problems.append(f"    - {pp_}")

    # 4. 空目录
    for d in find_empty_dirs():
        problems.append(f"[empty-dir] {d} is empty")

    # 5. basedpyright 未使用诊断（unused import / variable / function）
    bp_unused = run_basedpyright_unused()
    if bp_unused:
        problems.append(f"[basedpyright] {len(bp_unused)} unused diagnostic(s):")
        for u in bp_unused:
            problems.append(f"    - {u}")

    # 输出
    if problems:
        print(f"Found potential dead code / redundancy ({len(problems)} group(s)):")
        for p in problems:
            print(p)
        return 1

    print("[OK] No dead code / redundancy detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
