#!/usr/bin/env python3
"""
更新管理模块 - 检查更新和自动更新
"""

import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import ClassVar
from urllib.error import URLError
from urllib.request import Request, urlopen

from packaging.version import InvalidVersion, Version

from ....constants import VERSION
from ....i18n import _
from ....language import K
from ....ui.output import ICON_WARN, print, progress
from ....ui.tip import render_business_error


class UpdateManager:
    """更新管理器"""

    GITHUB_API = "https://api.github.com/repos/eavelabs-community/sshm/releases/latest"
    GITHUB_TAG_API = "https://api.github.com/repos/eavelabs-community/sshm/releases/tags/{tag}"
    CACHE_FILE = Path.home() / ".sshm_update_cache"
    CACHE_VALID_HOURS = 24

    def __init__(self) -> None:
        self.current_version = VERSION
        self.platform = self._detect_platform()

    def _detect_platform(self) -> str:
        """检测当前平台"""
        system = platform.system()
        if system == "Windows":
            return "windows"
        elif system == "Linux":
            return "linux"
        elif system == "Darwin":
            return "macos"
        else:
            return "unknown"

    # 各平台对应的资产名关键词（用于从 release assets 中模糊匹配当前平台产物）
    _PLATFORM_ASSET_KEYWORDS: ClassVar[dict] = {
        "windows": ("windows", "win"),
        "linux": ("linux",),
        "macos": ("macos", "darwin"),
    }

    @staticmethod
    def _parse_version(version: str) -> Version:
        """解析版本号（基于 packaging.version，正确处理预发布后缀 v0.0.1-beta）"""
        try:
            return Version(version.lstrip("v"))
        except InvalidVersion:
            return Version("0")

    def _is_newer_version(self, latest: str, current: str) -> bool:
        """比较版本号（基于 packaging.version 语义化比较）"""
        try:
            return self._parse_version(latest) > self._parse_version(current)
        except Exception:
            return False

    def _get_cache(self) -> dict | None:
        """读取缓存的版本信息"""
        if not self.CACHE_FILE.exists():
            return None

        try:
            import time

            cache_age = time.time() - self.CACHE_FILE.stat().st_mtime
            if cache_age > self.CACHE_VALID_HOURS * 3600:
                return None

            with open(self.CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 校验缓存结构：版本可解析为非零版本且下载链接为真实 URL，
            # 避免损坏 / 手写伪造的缓存导致误报"有新版本"
            if (
                isinstance(data, dict)
                and isinstance(data.get("version"), str)
                and self._parse_version(data["version"]) > Version("0")
                and isinstance(data.get("download_url"), str)
                and data["download_url"].startswith(("http://", "https://"))
            ):
                return data
            return None
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    def _save_cache(self, data: dict):
        """原子保存版本信息到缓存（临时文件 + os.replace，避免并发损坏）"""
        tmp = Path(f"{self.CACHE_FILE}.{os.getpid()}.tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.CACHE_FILE)
        except (OSError, TypeError):
            pass
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass

    def check_update(self, force: bool = False) -> dict | None:
        """
        检查更新

        Args:
            force: 强制检查，忽略缓存

        Returns:
            如果有更新，返回 {version, download_url, body}，否则返回 None
        """
        # 尝试从缓存读取
        if not force:
            cache = self._get_cache()
            if cache:
                if self._is_newer_version(cache["version"], self.current_version):
                    return cache
                return None

        # 从 GitHub API 获取最新版本
        try:
            req = Request(self.GITHUB_API)
            req.add_header("User-Agent", f"sshm/{VERSION}")

            with urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))

            latest_version = data["tag_name"]

            # 检查是否有更新
            if not self._is_newer_version(latest_version, self.current_version):
                return None

            result = self._build_release_info(data)
            if result is None:
                return None

            # 保存到缓存
            self._save_cache(result)

            return result

        except URLError:
            # 网络错误，静默失败
            return None
        except Exception:
            return None

    def _match_platform_asset(self, data: dict) -> str | None:
        """从 release assets 中按当前平台关键词模糊匹配可执行资产下载链接。"""
        keywords = self._PLATFORM_ASSET_KEYWORDS.get(self._detect_platform(), ())
        _SOURCE_SUFFIXES = (".tar.gz", ".zip", ".tar.xz")
        for asset in data.get("assets", []):
            name = asset.get("name", "").lower()
            # 跳过源码包/文档等非可执行资产
            if name.endswith(_SOURCE_SUFFIXES) or "source" in name:
                continue
            # 当前平台关键词命中（资产名通常明确区分平台）
            if any(k in name for k in keywords):
                return asset.get("browser_download_url")
        return None

    def _build_release_info(self, data: dict) -> dict | None:
        """把 GitHub release JSON 组装为 {version, download_url, body, published_at}。

        平台无匹配资产时返回 None。
        """
        download_url = self._match_platform_asset(data)
        if not download_url:
            return None
        return {
            "version": data["tag_name"],
            "download_url": download_url,
            "body": data.get("body", ""),
            "published_at": data.get("published_at", ""),
        }

    def get_release_by_tag(self, tag: str) -> dict | None:
        """按 tag 查询指定版本 release 的可执行资产信息（供 reinstall 指定版本）。

        Args:
            tag: 版本标签，如 'v0.0.5' 或 '0.0.5'

        Returns:
            {version, download_url, body, published_at} 或 None（无匹配/网络错误）
        """
        try:
            url = self.GITHUB_TAG_API.format(tag=tag)
            req = Request(url)
            req.add_header("User-Agent", f"sshm/{VERSION}")
            with urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
            return self._build_release_info(data)
        except URLError:
            return None
        except Exception:
            return None

    def download_and_update(self, download_url: str) -> bool:
        """
        下载并更新可执行文件

        Args:
            download_url: 下载链接

        Returns:
            是否成功
        """
        # 源码运行模式：无法用下载的 exe 替换 .py 入口，直接提示
        if not getattr(sys, "frozen", False):
            render_business_error(_(K.upd.from_source), icon=ICON_WARN, hint=_(K.upd.use_git_pull))
            return False

        try:
            # 下载到临时文件
            req = Request(download_url)
            req.add_header("User-Agent", f"sshm/{VERSION}")

            with urlopen(req, timeout=60) as response:
                # 跟随重定向后的最终响应才携带可靠的 content-length
                total_size = int(response.headers.get("content-length", 0) or 0)
                chunk_size = 64 * 1024  # 64KB 分块，减少刷新次数

                temp_fd, temp_path = tempfile.mkstemp(suffix=".exe" if self.platform == "windows" else "")
                os.close(temp_fd)  # 立即关闭 fd，避免文件句柄泄漏（更新后无法删除临时文件）

                with (
                    open(temp_path, "wb") as f,
                    progress(
                        total=total_size if total_size > 0 else None,
                        desc=_(K.upd.downloading),
                    ) as p,
                ):
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        # advance 实时刷新；total 缺失时 rich 显示不确定进度
                        p.update(advance=len(chunk))

            # 获取当前可执行文件路径
            current_exe = sys.executable if getattr(sys, "frozen", False) else sys.argv[0]
            current_exe = os.path.abspath(current_exe)

            print(_(K.upd.updating))

            # 根据平台执行不同的更新策略
            if self.platform == "windows":
                # Windows: 创建批处理脚本延迟替换（UTF-8 编码，避免中文/emoji 写入失败）
                batch_script = f"""@echo off
chcp 65001 >nul
timeout /t 2 /nobreak >nul
move /y "{temp_path}" "{current_exe}"
echo.
echo Update complete!
echo Please restart sshm.
pause
del "%~f0"
"""
                batch_path = os.path.join(tempfile.gettempdir(), "sshm_update.bat")
                with open(batch_path, "w", encoding="utf-8") as f:
                    f.write(batch_script)

                # 启动批处理脚本
                subprocess.Popen(
                    ["cmd", "/c", batch_path],
                    creationflags=subprocess.CREATE_NEW_CONSOLE if hasattr(subprocess, "CREATE_NEW_CONSOLE") else 0,
                )

                print("\n✅ " + _(K.upd.script_started))
                print(_(K.upd.exit_after))

            else:
                # Linux/macOS: 直接替换（需要权限）
                os.chmod(temp_path, 0o755)

                # 尝试直接替换
                try:
                    import shutil

                    shutil.move(temp_path, current_exe)
                    print("\n✅ " + _(K.upd.complete))
                    print(_(K.upd.run_again))
                except PermissionError:
                    # 需要 sudo
                    render_business_error(
                        _(K.upd.need_admin),
                        icon=ICON_WARN,
                        hint=_(K.upd.run_manual, src=temp_path, dst=current_exe),
                    )
                    return False

            return True

        except Exception as e:
            render_business_error(f"{_(K.upd.failed)} {e}")
            return False

    def check_and_notify(self) -> None:
        """
        检查更新并通知用户（静默检查）
        在每次运行时调用，不干扰正常使用
        """
        update_info = self.check_update(force=False)
        if update_info:
            msg = _(
                K.upd.available,
                version=update_info["version"],
                current=self.current_version,
            )
            hint = _(K.upd.run_update)
            print(f"\n💡 {msg}")
            print(f"   {hint}\n")
