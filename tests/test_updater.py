"""Tests for taxo.updater — auto-update system."""
import pytest

from taxo.updater import compare_versions, get_current_version, is_frozen


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
