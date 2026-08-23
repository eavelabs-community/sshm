"""UpdateManager 单元测试：版本解析/比较、缓存读写、check_update 逻辑"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def updater(tmp_path: Path):
    from sshm.core.services.net.updater import UpdateManager

    u = UpdateManager()
    # 隔离缓存文件到临时目录，避免污染真实 ~/.sshm_update_cache
    u.CACHE_FILE = tmp_path / ".sshm_update_cache"
    return u


class TestParseVersion:
    def test_normal(self, updater):
        from packaging.version import Version

        assert updater._parse_version("v1.2.3") == Version("1.2.3")

    def test_v_prefix(self, updater):
        from packaging.version import Version

        assert updater._parse_version("v0.0.3") == Version("0.0.3")

    def test_prerelease(self, updater):
        from packaging.version import Version

        assert updater._parse_version("v1.0.0-beta") == Version("1.0.0-beta")

    def test_invalid_returns_zero(self, updater):
        from packaging.version import Version

        assert updater._parse_version("not-a-version") == Version("0")
        assert updater._parse_version("") == Version("0")


class TestIsNewerVersion:
    def test_newer(self, updater):
        assert updater._is_newer_version("v1.1.0", "v1.0.0") is True

    def test_older(self, updater):
        assert updater._is_newer_version("v1.0.0", "v1.1.0") is False

    def test_equal(self, updater):
        assert updater._is_newer_version("v1.0.0", "1.0.0") is False

    def test_prerelease_handling(self, updater):
        # 1.0.0-beta < 1.0.0
        assert updater._is_newer_version("v1.0.0", "v1.0.0-beta") is True

    def test_invalid(self, updater):
        assert updater._is_newer_version("junk", "v1.0.0") is False


class TestDetectPlatform:
    def test_returns_string(self, updater):
        assert updater._detect_platform() in ("windows", "linux", "macos", "unknown")


class TestCache:
    def test_no_cache_returns_none(self, updater):
        assert updater._get_cache() is None

    def test_save_and_get_roundtrip(self, updater):
        data = {"version": "v9.9.9", "download_url": "https://x/y.exe"}
        updater._save_cache(data)
        got = updater._get_cache()
        assert got is not None
        assert got["version"] == "v9.9.9"

    def test_invalid_cache_structure_rejected(self, updater):
        # 缺 download_url 的结构应被视为无效缓存
        updater.CACHE_FILE.write_text(json.dumps({"version": "v9.9.9"}), encoding="utf-8")
        assert updater._get_cache() is None

    def test_invalid_version_in_cache_rejected(self, updater):
        # 版本无法解析（< 0）应视为无效缓存
        updater.CACHE_FILE.write_text(
            json.dumps({"version": "not-a-version", "download_url": "https://x/y.exe"}),
            encoding="utf-8",
        )
        assert updater._get_cache() is None

    def test_corrupt_json_returns_none(self, updater):
        updater.CACHE_FILE.write_text("{{{not json", encoding="utf-8")
        assert updater._get_cache() is None

    def test_no_tmp_leftover(self, updater):
        updater._save_cache({"version": "v1.0.0", "download_url": "https://x"})
        leftovers = list(updater.CACHE_FILE.parent.glob(".sshm_update_cache.*.tmp"))
        assert not leftovers


class TestCheckUpdate:
    def _fake_response(self, payload: dict, status=200):
        resp = MagicMock()
        resp.status = status
        resp.read.return_value = json.dumps(payload).encode("utf-8")
        # 支持 with 语法
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    def test_uses_cache_when_fresh_and_newer(self, updater):
        """有有效缓存且版本较新时，不发起网络请求"""
        updater._save_cache(
            {
                "version": "v99.0.0",
                "download_url": "https://x/y.exe",
                "body": "",
                "published_at": "",
            }
        )
        with patch("sshm.core.services.net.updater.urlopen") as mock_open:
            result = updater.check_update(force=False)
        mock_open.assert_not_called()
        assert result is not None
        assert result["version"] == "v99.0.0"

    def test_no_update_when_current_newer(self, updater):
        """当前版本比最新版本新 -> 返回 None（无更新）"""
        updater.current_version = "v999.0.0"
        with patch(
            "sshm.core.services.net.updater.urlopen",
            return_value=self._fake_response({"tag_name": "v1.0.0"}),
        ) as mock_open:
            result = updater.check_update(force=True)
        assert result is None

    def test_finds_platform_asset(self, updater):
        updater.current_version = "v0.0.1"
        payload = {
            "tag_name": "v2.0.0",
            "assets": [
                {
                    "name": "sshm-windows-x64.exe",
                    "browser_download_url": "https://x/win.exe",
                },
                {"name": "sshm-linux-x64", "browser_download_url": "https://x/linux"},
            ],
        }
        # 平台在 __init__ 已缓存为 self.platform，patch platform.system 不会生效；
        # 直接设置属性模拟 Windows，使平台资产选择与运行环境无关（CI 上是 Linux）
        updater.platform = "windows"
        with patch(
            "sshm.core.services.net.updater.urlopen",
            return_value=self._fake_response(payload),
        ):
            result = updater.check_update(force=True)
        assert result is not None
        assert result["download_url"] == "https://x/win.exe"

    def test_network_error_raises(self, updater):
        from urllib.error import URLError

        from sshm.core.services.net.updater import UpdateCheckError

        # 网络错误应抛出 UpdateCheckError（区别于「无更新」的 None），
        # 供调用方把网络故障上报为失败，而非误报「已是最新」。
        with patch("sshm.core.services.net.updater.urlopen", side_effect=URLError("offline")):
            with pytest.raises(UpdateCheckError):
                updater.check_update(force=True)

    def test_saves_cache_after_check(self, updater):
        updater.current_version = "v0.0.1"
        payload = {
            "tag_name": "v2.0.0",
            "assets": [
                {
                    "name": "sshm-windows-x64.exe",
                    "browser_download_url": "https://x/win.exe",
                }
            ],
        }
        # 同上：直接设置平台属性，保证 Linux 上也能匹配到 windows 资产并写缓存
        updater.platform = "windows"
        with patch(
            "sshm.core.services.net.updater.urlopen",
            return_value=self._fake_response(payload),
        ):
            updater.check_update(force=True)
        assert updater.CACHE_FILE.exists()
