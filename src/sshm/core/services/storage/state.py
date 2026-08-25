#!/usr/bin/env python3
"""
状态管理器 - 负责密钥状态的持久化
"""

import json
import os
from pathlib import Path


class StateManager:
    """密钥状态管理器"""

    # 顶层保留字段，不参与 active_keys 映射
    RESERVED_KEYS = ("authors", "hosts", "lang")

    def __init__(self, state_file: Path):
        self.state_file = state_file
        # 状态文件位于 SSH 目录下，故其父目录即 ssh_dir
        self.ssh_dir = state_file.parent
        # 进程内缓存：CLI 单进程场景下避免每个操作都重读磁盘
        self._cache: dict | None = None

    def _read_state(self) -> dict:
        """读取完整状态文件（兼容旧格式），带进程内缓存"""
        if self._cache is not None:
            return self._cache
        if not self.state_file.exists():
            self._cache = {}
            return self._cache
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._cache = data
                return data
        except (OSError, json.JSONDecodeError):
            # 状态文件损坏：备份原文件，避免后续写入静默覆盖丢失数据
            try:
                corrupt_backup = self.state_file.with_suffix(".state.corrupt")
                self.state_file.rename(corrupt_backup)
            except OSError:
                pass
        self._cache = {}
        return self._cache

    def _write_state(self, state: dict):
        """原子写入完整状态文件（临时文件 + os.replace，避免崩溃/断电损坏）"""
        self._cache = state
        tmp = self.state_file.with_suffix(".state.tmp")
        try:
            tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
            os.replace(tmp, self.state_file)
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass

    # ------------------------------------------------------------------
    # active_keys 相关
    # ------------------------------------------------------------------

    def read_active_keys(self) -> dict[str, str]:
        """读取当前激活的密钥状态"""
        state = self._read_state()
        active = {}
        for k, v in state.items():
            if k in self.RESERVED_KEYS:
                continue
            # 兼容旧格式：标签为小写
            active[k] = v.lower() if isinstance(v, str) else v
        return active

    def write_active_key(self, key_type: str, label: str):
        """写入当前激活的密钥状态"""
        state = self._read_state()
        state[key_type] = label.lower()
        self._write_state(state)

    def remove_active_key(self, key_type: str):
        """移除指定类型的激活状态"""
        state = self._read_state()
        if key_type in state:
            del state[key_type]
            self._write_state(state)

    def clear_active_keys(self):
        """清除所有激活密钥状态（保留顶层保留字段）。"""
        state = self._read_state()
        for k in list(state.keys()):
            if k not in self.RESERVED_KEYS:
                del state[k]
        self._write_state(state)

    def update_label(self, old_label: str, new_label: str):
        """更新状态文件中的标签名（含作者与主机映射）"""
        state = self._read_state()
        old_label_lower = old_label.lower()
        new_label_lower = new_label.lower()

        updated = False
        for key_type, label in state.items():
            if key_type in self.RESERVED_KEYS:
                continue
            if label == old_label_lower:
                state[key_type] = new_label_lower
                updated = True

        authors = state.get("authors")
        if isinstance(authors, dict) and old_label_lower in authors:
            authors[new_label_lower] = authors.pop(old_label_lower)
            updated = True

        hosts = state.get("hosts")
        if isinstance(hosts, dict) and old_label_lower in hosts:
            hosts[new_label_lower] = hosts.pop(old_label_lower)
            updated = True

        if updated:
            self._write_state(state)

    # ------------------------------------------------------------------
    # authors 相关
    # ------------------------------------------------------------------

    def read_authors(self) -> dict[str, dict[str, str]]:
        """读取作者信息映射 {label: {'name': str, 'email': str}}"""
        state = self._read_state()
        authors = state.get("authors", {})
        return authors if isinstance(authors, dict) else {}

    def write_author(self, label: str, name: str, email: str):
        """写入指定标签的作者信息"""
        state = self._read_state()
        authors = state.setdefault("authors", {})
        if not isinstance(authors, dict):
            authors = state["authors"] = {}
        authors[label.lower()] = {"name": name or "", "email": email or ""}
        self._write_state(state)

    def delete_author(self, label: str):
        """删除指定标签的作者信息"""
        state = self._read_state()
        authors = state.get("authors")
        if isinstance(authors, dict) and label.lower() in authors:
            del authors[label.lower()]
            self._write_state(state)

    def write_authors(self, authors: dict[str, dict[str, str]]):
        """批量写入作者信息（替换整个字典）"""
        state = self._read_state()
        state["authors"] = authors
        self._write_state(state)

    def read_default_author(self) -> str | None:
        """读取默认作者标签"""
        state = self._read_state()
        return state.get("default_author") if isinstance(state.get("default_author"), str) else None

    def write_default_author(self, label: str | None) -> None:
        """设置默认作者标签"""
        state = self._read_state()
        if label is not None:
            state["default_author"] = label.lower()
        else:
            state.pop("default_author", None)
        self._write_state(state)

    def read_keys(self) -> list[dict[str, str]]:
        """读取所有密钥记录列表"""
        state = self._read_state()
        keys = state.get("keys", [])
        return keys if isinstance(keys, list) else []

    def write_keys(self, keys: list[dict[str, str]]) -> None:
        """批量写入密钥记录列表（替换整个列表）"""
        state = self._read_state()
        state["keys"] = keys
        self._write_state(state)

    def read_default_key(self) -> str | None:
        """读取默认密钥标签"""
        state = self._read_state()
        return state.get("default_key") if isinstance(state.get("default_key"), str) else None

    def write_default_key(self, label: str | None) -> None:
        """设置默认密钥标签"""
        state = self._read_state()
        if label is not None:
            state["default_key"] = label.lower()
        else:
            state.pop("default_key", None)
        self._write_state(state)

    def read_repos(self) -> list[dict[str, str]]:
        """读取所有仓库记录列表"""
        state = self._read_state()
        repos = state.get("repos", [])
        return repos if isinstance(repos, list) else []

    def write_repos(self, repos: list[dict[str, str]]) -> None:
        """批量写入仓库记录列表（替换整个列表）"""
        state = self._read_state()
        state["repos"] = repos
        self._write_state(state)

    def read_current_repo(self) -> str | None:
        """读取当前仓库路径"""
        state = self._read_state()
        return state.get("current_repo") if isinstance(state.get("current_repo"), str) else None

    def write_current_repo(self, path: str | None) -> None:
        """设置当前仓库路径"""
        state = self._read_state()
        if path is not None:
            state["current_repo"] = path
        else:
            state.pop("current_repo", None)
        self._write_state(state)

    # ------------------------------------------------------------------
    # hosts 相关（label -> hostname 映射，供 use/remove/rename 使用）
    # ------------------------------------------------------------------

    def read_hosts(self) -> dict[str, str]:
        """读取标签到主机名的映射 {label: hostname}"""
        state = self._read_state()
        hosts = state.get("hosts", {})
        return hosts if isinstance(hosts, dict) else {}

    def write_host(self, label: str, hostname: str):
        """写入指定标签的主机名映射"""
        state = self._read_state()
        hosts = state.setdefault("hosts", {})
        if not isinstance(hosts, dict):
            hosts = state["hosts"] = {}
        hosts[label.lower()] = hostname
        self._write_state(state)

    def write_hosts(self, hosts: dict[str, str]):
        """批量写入主机名映射（替换整个字典）"""
        state = self._read_state()
        state["hosts"] = hosts
        self._write_state(state)

    def remove_host(self, label: str):
        """移除指定标签的主机名映射"""
        state = self._read_state()
        hosts = state.get("hosts")
        if isinstance(hosts, dict) and label.lower() in hosts:
            del hosts[label.lower()]
            self._write_state(state)

    # ------------------------------------------------------------------
    # lang 相关（输出语言设置）
    # ------------------------------------------------------------------

    def read_lang(self) -> str:
        """读取保存的输出语言（'en'/'zh'，默认 'en'）"""
        state = self._read_state()
        lang = state.get("lang")
        return lang if isinstance(lang, str) else "en"

    def write_lang(self, lang: str):
        """保存输出语言设置（'en'/'zh'）"""
        state = self._read_state()
        state["lang"] = lang if lang == "zh" else "en"
        self._write_state(state)

    # ------------------------------------------------------------------
    # auto_author 相关（密钥切换时自动联动作者）
    # ------------------------------------------------------------------

    def read_auto_author(self) -> bool:
        """读取密钥-author 自动联动开关（默认开启）"""
        state = self._read_state()
        return state.get("auto_author", True)

    def write_auto_author(self, enabled: bool):
        """保存密钥-author 自动联动开关"""
        state = self._read_state()
        state["auto_author"] = bool(enabled)
        self._write_state(state)
