"""Tests for taxo.updater — auto-update system."""
import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import httpx
import pytest

from taxo.updater import (
    CACHE_TTL_SECONDS,
    GITHUB_RELEASES_URL,
    UpdateCache,
    check_for_update_hint,
    check_latest_release,
    compare_versions,
    get_current_version,
    get_platform_asset_name,
    is_frozen,
    PLATFORM_MAP,
)


class TestCompareVersions:
    def test_newer_version_available(self):
        assert compare_versions("0.2.0", "0.3.0") == -1

    def test_older_version(self):
        assert compare_versions("0.3.0", "0.2.0") == 1

    def test_same_version(self):
        assert compare_versions("0.2.0", "0.2.0") == 0

    def test_major_version_difference(self):
        assert compare_versions("1.0.0", "2.0.0") == -1

    def test_minor_version_difference(self):
        assert compare_versions("0.2.0", "0.2.1") == -1

    def test_patch_version_difference(self):
        assert compare_versions("0.2.1", "0.2.0") == 1

    def test_different_lengths(self):
        assert compare_versions("0.2.0", "0.2.0.1") == -1

    def test_v_prefix_stripped(self):
        assert compare_versions("v0.2.0", "0.2.0") == 0

    def test_invalid_version_returns_none(self):
        assert compare_versions("not-a-version", "0.2.0") is None


class TestGetCurrentVersion:
    def test_returns_string(self):
        v = get_current_version()
        assert isinstance(v, str)
        assert "." in v

    def test_matches_package_version(self):
        from taxo import __version__
        assert get_current_version() == __version__


class TestIsFrozen:
    def test_returns_bool(self):
        result = is_frozen()
        assert isinstance(result, bool)

    def test_not_frozen_in_test_env(self):
        # Tests run via pytest, not PyInstaller
        assert is_frozen() is False


class TestPlatformAssetName:
    def test_macos_arm64(self):
        with patch("taxo.updater._platform") as mock_plat:
            mock_plat.system.return_value = "Darwin"
            mock_plat.machine.return_value = "arm64"
            assert get_platform_asset_name() == "taxo-macos-arm64"

    def test_linux_x86_64(self):
        with patch("taxo.updater._platform") as mock_plat:
            mock_plat.system.return_value = "Linux"
            mock_plat.machine.return_value = "x86_64"
            assert get_platform_asset_name() == "taxo-linux-x86_64"

    def test_windows_x86_64(self):
        with patch("taxo.updater._platform") as mock_plat:
            mock_plat.system.return_value = "Windows"
            mock_plat.machine.return_value = "AMD64"
            assert get_platform_asset_name() == "taxo-windows-x86_64.exe"

    def test_unsupported_platform_returns_none(self):
        with patch("taxo.updater._platform") as mock_plat:
            mock_plat.system.return_value = "FreeBSD"
            mock_plat.machine.return_value = "x86_64"
            assert get_platform_asset_name() is None

    def test_platform_map_has_three_entries(self):
        assert len(PLATFORM_MAP) == 3


class TestUpdateCache:
    def test_cache_file_created_on_save(self, tmp_path: Path):
        cache = UpdateCache(cache_dir=tmp_path)
        cache.save("0.3.0", "https://example.com/taxo-macos-arm64", "taxo-macos-arm64")
        assert (tmp_path / "update_cache.json").exists()

    def test_cache_roundtrip(self, tmp_path: Path):
        cache = UpdateCache(cache_dir=tmp_path)
        cache.save("0.3.0", "https://example.com/taxo-macos-arm64", "taxo-macos-arm64")
        info = cache.load()
        assert info is not None
        assert info["latest_version"] == "0.3.0"
        assert info["download_url"] == "https://example.com/taxo-macos-arm64"
        assert info["asset_name"] == "taxo-macos-arm64"

    def test_cache_is_stale_when_no_file(self, tmp_path: Path):
        cache = UpdateCache(cache_dir=tmp_path)
        assert cache.is_stale() is True

    def test_cache_is_fresh_within_ttl(self, tmp_path: Path):
        cache = UpdateCache(cache_dir=tmp_path)
        cache.save("0.3.0", "https://example.com/taxo", "taxo-macos-arm64")
        assert cache.is_stale() is False

    def test_cache_is_stale_after_ttl(self, tmp_path: Path):
        cache = UpdateCache(cache_dir=tmp_path)
        cache.save("0.3.0", "https://example.com/taxo", "taxo-macos-arm64")
        # Manually backdate the cache
        cache_file = tmp_path / "update_cache.json"
        data = json.loads(cache_file.read_text())
        data["last_check"] = time.strftime(
            "%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - CACHE_TTL_SECONDS - 100)
        )
        cache_file.write_text(json.dumps(data))
        assert cache.is_stale() is True

    def test_cache_load_returns_none_on_corrupt_file(self, tmp_path: Path):
        cache = UpdateCache(cache_dir=tmp_path)
        (tmp_path / "update_cache.json").write_text("not json")
        assert cache.load() is None

    def test_cache_ttl_is_24_hours(self):
        assert CACHE_TTL_SECONDS == 86400


class TestCheckLatestRelease:
    def test_returns_version_and_url(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tag_name": "v0.3.0",
            "assets": [
                {"name": "taxo-macos-arm64", "browser_download_url": "https://github.com/example/taxo-macos-arm64"},
                {"name": "taxo-linux-x86_64", "browser_download_url": "https://github.com/example/taxo-linux-x86_64"},
            ],
        }

        with patch("taxo.updater.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = mock_response
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = check_latest_release()
            assert result is not None
            assert result["latest_version"] == "0.3.0"
            assert len(result["assets"]) == 2

    def test_returns_none_on_http_error(self):
        with patch("taxo.updater.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get.side_effect = httpx.ConnectError("no network")
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = check_latest_release()
            assert result is None

    def test_returns_none_on_non_200(self):
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.json.return_value = {}

        with patch("taxo.updater.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = mock_response
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = check_latest_release()
            assert result is None

    def test_strips_v_prefix_from_tag(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tag_name": "v0.4.0",
            "assets": [],
        }

        with patch("taxo.updater.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = mock_response
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = check_latest_release()
            assert result["latest_version"] == "0.4.0"

    def test_github_url_is_correct(self):
        assert "Lemon-cc-hang/taxo" in GITHUB_RELEASES_URL
        assert "releases/latest" in GITHUB_RELEASES_URL


class TestCheckForUpdateHint:
    def test_returns_none_when_up_to_date(self, tmp_path: Path):
        cache = UpdateCache(cache_dir=tmp_path)
        cache.save("0.2.0", "https://example.com/taxo", "taxo-macos-arm64")

        result = check_for_update_hint(current_version="0.2.0", cache=cache)
        assert result is None

    def test_returns_hint_when_newer_available(self, tmp_path: Path):
        cache = UpdateCache(cache_dir=tmp_path)
        cache.save("0.3.0", "https://example.com/taxo", "taxo-macos-arm64")

        result = check_for_update_hint(current_version="0.2.0", cache=cache)
        assert result is not None
        assert "0.3.0" in result
        assert "taxo update" in result

    def test_returns_none_when_cache_stale_and_api_fails(self, tmp_path: Path):
        cache = UpdateCache(cache_dir=tmp_path)
        # No cache file → stale

        with patch("taxo.updater.check_latest_release", return_value=None):
            result = check_for_update_hint(current_version="0.2.0", cache=cache)
            assert result is None

    def test_refreshes_cache_when_stale(self, tmp_path: Path):
        cache = UpdateCache(cache_dir=tmp_path)
        # No cache → stale, but API returns new version
        api_result = {
            "latest_version": "0.3.0",
            "assets": [
                {"name": "taxo-macos-arm64", "browser_download_url": "https://example.com/taxo"},
            ],
        }

        with patch("taxo.updater.check_latest_release", return_value=api_result):
            result = check_for_update_hint(current_version="0.2.0", cache=cache)
            assert result is not None
            assert "0.3.0" in result
            # Cache should now be populated
            assert cache.is_stale() is False
