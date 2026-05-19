"""Tests for taxo.updater — auto-update system."""
from unittest.mock import patch

import pytest

from taxo.updater import compare_versions, get_current_version, get_platform_asset_name, is_frozen, PLATFORM_MAP


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
