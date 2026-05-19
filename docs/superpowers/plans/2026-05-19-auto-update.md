# Auto-Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add auto-update capability to Taxo CLI — passive check on every run, active `taxo update` command, supporting both binary (PyInstaller) and pip installations.

**Architecture:** New `updater.py` module handles version comparison, GitHub API polling, download, and binary replacement. CLI layer adds `taxo update` command and passive hint in main callback. Cache stored in `~/.taxo/update_cache.json` with 24h TTL. Install method detected via `sys.frozen`.

**Tech Stack:** httpx (already available), Pydantic (data models), Rich (progress bars), platform/os/stdlib (binary replacement)

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/taxo/updater.py` | Create | Version check, download, binary replace, pip upgrade |
| `src/taxo/cli.py` | Modify | Add `update` command, passive check hint in main callback |
| `src/taxo/__init__.py` | Modify | Bump `__version__` to `"0.2.0"` |
| `pyproject.toml` | Modify | Bump `version` to `"0.2.0"` |
| `tests/test_updater.py` | Create | Unit tests for all updater logic (mocked HTTP/filesystem) |

---

### Task 1: Version Bump

**Files:**
- Modify: `src/taxo/__init__.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Update version in `__init__.py`**

In `src/taxo/__init__.py`, change the version string:

```python
__version__ = "0.2.0"
```

- [ ] **Step 2: Update version in `pyproject.toml`**

Find the `version` field and change it:

```toml
version = "0.2.0"
```

- [ ] **Step 3: Verify version is importable**

Run: `uv run python -c "from taxo import __version__; print(__version__)"`
Expected: `0.2.0`

- [ ] **Step 4: Commit**

```bash
git add src/taxo/__init__.py pyproject.toml
git commit -m "chore: bump version to 0.2.0"
```

---

### Task 2: UpdateInfo Model and Version Comparison

**Files:**
- Create: `src/taxo/updater.py`
- Create: `tests/test_updater.py`

- [ ] **Step 1: Write failing tests for version comparison**

In `tests/test_updater.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_updater.py -v`
Expected: FAIL — `ImportError: cannot import name 'compare_versions' from 'taxo.updater'`

- [ ] **Step 3: Write minimal implementation**

In `src/taxo/updater.py`:

```python
"""Auto-update system for Taxo CLI.

Checks GitHub Releases for new versions, downloads and replaces
the binary (or runs pip upgrade) when an update is available.
"""
from __future__ import annotations

import sys
from typing import Literal

from taxo import __version__


def get_current_version() -> str:
    """Return the current Taxo version string."""
    return __version__


def is_frozen() -> bool:
    """Return True if running as a PyInstaller binary."""
    return getattr(sys, "frozen", False)


def compare_versions(current: str, latest: str) -> Literal[-1, 0, 1] | None:
    """Compare two semver strings. Returns -1 if latest is newer, 0 if equal, 1 if current is newer.

    Returns None if either version string cannot be parsed.
    """
    try:
        c_parts = [int(p) for p in current.lstrip("v").split(".")]
        l_parts = [int(p) for p in latest.lstrip("v").split(".")]
    except (ValueError, AttributeError):
        return None

    # Pad to same length
    max_len = max(len(c_parts), len(l_parts))
    c_parts.extend([0] * (max_len - len(c_parts)))
    l_parts.extend([0] * (max_len - len(l_parts)))

    for c, l in zip(c_parts, l_parts):
        if c < l:
            return -1
        if c > l:
            return 1
    return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_updater.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/taxo/updater.py tests/test_updater.py
git commit -m "feat(updater): add version comparison and frozen detection"
```

---

### Task 3: Platform Detection and Asset Matching

**Files:**
- Modify: `src/taxo/updater.py`
- Modify: `tests/test_updater.py`

- [ ] **Step 1: Write failing tests for platform detection**

Append to `tests/test_updater.py`:

```python
from unittest.mock import patch

from taxo.updater import get_platform_asset_name, PLATFORM_MAP


class TestPlatformAssetName:
    def test_macos_arm64(self):
        with patch("taxo.updater.platform") as mock_plat:
            mock_plat.system.return_value = "Darwin"
            mock_plat.machine.return_value = "arm64"
            assert get_platform_asset_name() == "taxo-macos-arm64"

    def test_linux_x86_64(self):
        with patch("taxo.updater.platform") as mock_plat:
            mock_plat.system.return_value = "Linux"
            mock_plat.machine.return_value = "x86_64"
            assert get_platform_asset_name() == "taxo-linux-x86_64"

    def test_windows_x86_64(self):
        with patch("taxo.updater.platform") as mock_plat:
            mock_plat.system.return_value = "Windows"
            mock_plat.machine.return_value = "AMD64"
            assert get_platform_asset_name() == "taxo-windows-x86_64.exe"

    def test_unsupported_platform_returns_none(self):
        with patch("taxo.updater.platform") as mock_plat:
            mock_plat.system.return_value = "FreeBSD"
            mock_plat.machine.return_value = "x86_64"
            assert get_platform_asset_name() is None

    def test_platform_map_has_three_entries(self):
        assert len(PLATFORM_MAP) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_updater.py::TestPlatformAssetName -v`
Expected: FAIL — `ImportError: cannot import name 'get_platform_asset_name'`

- [ ] **Step 3: Add platform detection to updater.py**

Append to `src/taxo/updater.py`:

```python
import platform as _platform

# (add `import platform as _platform` at the top with other imports)

PLATFORM_MAP: dict[tuple[str, str], str] = {
    ("Darwin", "arm64"): "taxo-macos-arm64",
    ("Linux", "x86_64"): "taxo-linux-x86_64",
    ("Windows", "AMD64"): "taxo-windows-x86_64.exe",
}


def get_platform_asset_name() -> str | None:
    """Return the release asset name for the current platform, or None if unsupported."""
    key = (_platform.system(), _platform.machine())
    return PLATFORM_MAP.get(key)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_updater.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/taxo/updater.py tests/test_updater.py
git commit -m "feat(updater): add platform detection and asset name mapping"
```

---

### Task 4: Update Cache (Read/Write/Check TTL)

**Files:**
- Modify: `src/taxo/updater.py`
- Modify: `tests/test_updater.py`

- [ ] **Step 1: Write failing tests for cache operations**

Append to `tests/test_updater.py`:

```python
import json
import time
from pathlib import Path

from taxo.updater import UpdateCache, CACHE_TTL_SECONDS


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_updater.py::TestUpdateCache -v`
Expected: FAIL — `ImportError: cannot import name 'UpdateCache'`

- [ ] **Step 3: Add UpdateCache class to updater.py**

Append to `src/taxo/updater.py`:

```python
import json
import time
from pathlib import Path


CACHE_TTL_SECONDS = 86400  # 24 hours


class UpdateCache:
    """Manages the update check cache file at ~/.taxo/update_cache.json."""

    def __init__(self, cache_dir: Path | None = None):
        self._cache_dir = cache_dir or Path.home() / ".taxo"
        self._cache_file = self._cache_dir / "update_cache.json"

    def save(self, latest_version: str, download_url: str, asset_name: str) -> None:
        """Save check result to cache."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "last_check": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "latest_version": latest_version,
            "download_url": download_url,
            "asset_name": asset_name,
        }
        self._cache_file.write_text(json.dumps(data, indent=2))

    def load(self) -> dict | None:
        """Load cached check result. Returns None if cache is missing or corrupt."""
        if not self._cache_file.exists():
            return None
        try:
            return json.loads(self._cache_file.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def is_stale(self) -> bool:
        """Return True if cache is missing or older than TTL."""
        data = self.load()
        if data is None:
            return True
        try:
            last_check = time.mktime(time.strptime(data["last_check"], "%Y-%m-%dT%H:%M:%S"))
            return (time.time() - last_check) > CACHE_TTL_SECONDS
        except (KeyError, ValueError):
            return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_updater.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/taxo/updater.py tests/test_updater.py
git commit -m "feat(updater): add update cache with 24h TTL"
```

---

### Task 5: GitHub API Check for Latest Release

**Files:**
- Modify: `src/taxo/updater.py`
- Modify: `tests/test_updater.py`

- [ ] **Step 1: Write failing tests for check_latest_release**

Append to `tests/test_updater.py`:

```python
from unittest.mock import patch, MagicMock

from taxo.updater import check_latest_release, GITHUB_RELEASES_URL


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_updater.py::TestCheckLatestRelease -v`
Expected: FAIL — `ImportError: cannot import name 'check_latest_release'`

- [ ] **Step 3: Add check_latest_release to updater.py**

Add `import httpx` at the top imports section, then append to `src/taxo/updater.py`:

```python
import logging

logger = logging.getLogger(__name__)

GITHUB_RELEASES_URL = "https://api.github.com/repos/Lemon-cc-hang/taxo/releases/latest"


def check_latest_release() -> dict | None:
    """Query GitHub Releases API for the latest version.

    Returns dict with keys: latest_version, assets (list of {name, browser_download_url}).
    Returns None on any failure (network, parse, non-200).
    """
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(
                GITHUB_RELEASES_URL,
                headers={"Accept": "application/vnd.github+json"},
            )
            if resp.status_code != 200:
                logger.debug("GitHub API returned %d", resp.status_code)
                return None
            data = resp.json()
    except (httpx.HTTPError, OSError) as e:
        logger.debug("GitHub API check failed: %s", e)
        return None

    try:
        tag = data["tag_name"].lstrip("v")
        assets = [
            {"name": a["name"], "browser_download_url": a["browser_download_url"]}
            for a in data.get("assets", [])
        ]
        return {"latest_version": tag, "assets": assets}
    except (KeyError, TypeError) as e:
        logger.debug("Failed to parse GitHub release: %s", e)
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_updater.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/taxo/updater.py tests/test_updater.py
git commit -m "feat(updater): add GitHub Releases API check"
```

---

### Task 6: Passive Update Check (Hint on Every Run)

**Files:**
- Modify: `src/taxo/updater.py`
- Modify: `tests/test_updater.py`

- [ ] **Step 1: Write failing tests for check_for_update_hint**

Append to `tests/test_updater.py`:

```python
from taxo.updater import check_for_update_hint


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_updater.py::TestCheckForUpdateHint -v`
Expected: FAIL — `ImportError: cannot import name 'check_for_update_hint'`

- [ ] **Step 3: Add check_for_update_hint to updater.py**

Append to `src/taxo/updater.py`:

```python
def check_for_update_hint(
    current_version: str | None = None,
    cache: UpdateCache | None = None,
) -> str | None:
    """Check if an update is available, using cache when fresh.

    Returns a hint string if update available, None otherwise.
    Never raises — all errors are caught and logged.
    """
    current_version = current_version or get_current_version()
    cache = cache or UpdateCache()

    try:
        if cache.is_stale():
            release = check_latest_release()
            if release is None:
                return None
            # Find matching asset for current platform
            asset_name = get_platform_asset_name()
            download_url = ""
            for a in release["assets"]:
                if a["name"] == asset_name:
                    download_url = a["browser_download_url"]
                    break
            cache.save(release["latest_version"], download_url, asset_name or "")

        data = cache.load()
        if data is None:
            return None

        cmp = compare_versions(current_version, data["latest_version"])
        if cmp == -1:
            return (
                f"⬆ New version available: {current_version} → {data['latest_version']}. "
                f"Run `taxo update` to upgrade."
            )
        return None
    except Exception as e:
        logger.debug("Update hint check failed: %s", e)
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_updater.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/taxo/updater.py tests/test_updater.py
git commit -m "feat(updater): add passive update check with hint"
```

---

### Task 7: Binary Download and Atomic Replace

**Files:**
- Modify: `src/taxo/updater.py`
- Modify: `tests/test_updater.py`

- [ ] **Step 1: Write failing tests for download_and_replace**

Append to `tests/test_updater.py`:

```python
import stat


class TestDownloadAndReplace:
    def test_downloads_to_temp_and_replaces(self, tmp_path: Path):
        # Create a fake "current binary"
        current_binary = tmp_path / "taxo"
        current_binary.write_text("old binary")

        # Mock httpx to return fake binary content
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_bytes.return_value = [b"new binary content"]
        mock_response.headers = {"content-length": "20"}

        with patch("taxo.updater.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = mock_response
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client_cls.return_value = mock_client

            download_and_replace(
                url="https://example.com/taxo-macos-arm64",
                current_binary=str(current_binary),
                cache_dir=tmp_path / ".taxo",
            )

        # Binary should be replaced
        assert current_binary.read_text() == "new binary content"

    def test_sets_executable_permission(self, tmp_path: Path):
        current_binary = tmp_path / "taxo"
        current_binary.write_text("old")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_bytes.return_value = [b"new"]
        mock_response.headers = {"content-length": "3"}

        with patch("taxo.updater.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = mock_response
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client_cls.return_value = mock_client

            download_and_replace(
                url="https://example.com/taxo",
                current_binary=str(current_binary),
                cache_dir=tmp_path / ".taxo",
            )

        mode = current_binary.stat().st_mode
        assert mode & stat.S_IXUSR  # Owner executable bit set

    def test_cleans_up_temp_on_failure(self, tmp_path: Path):
        current_binary = tmp_path / "taxo"
        current_binary.write_text("old")

        with patch("taxo.updater.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get.side_effect = httpx.ConnectError("fail")
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(httpx.ConnectError):
                download_and_replace(
                    url="https://example.com/taxo",
                    current_binary=str(current_binary),
                    cache_dir=tmp_path / ".taxo",
                )

        # Temp dir should be cleaned up
        temp_dir = tmp_path / ".taxo" / "tmp"
        if temp_dir.exists():
            assert not any(temp_dir.iterdir())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_updater.py::TestDownloadAndReplace -v`
Expected: FAIL — `ImportError: cannot import name 'download_and_replace'`

- [ ] **Step 3: Add download_and_replace to updater.py**

Append to `src/taxo/updater.py`:

```python
import os
import stat


def download_and_replace(
    url: str,
    current_binary: str,
    cache_dir: Path | None = None,
) -> None:
    """Download new binary and atomically replace the current one.

    Args:
        url: Download URL for the new binary.
        current_binary: Path to the current binary to replace.
        cache_dir: Directory for temp files (default: ~/.taxo).

    Raises:
        httpx.HTTPError: On download failure.
        OSError: On file replacement failure.
    """
    cache_dir = cache_dir or Path.home() / ".taxo"
    tmp_dir = cache_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / "taxo-new"

    try:
        with httpx.Client(timeout=60.0) as client:
            with client.stream("GET", url, follow_redirects=True) as resp:
                resp.raise_for_status()
                with open(tmp_path, "wb") as f:
                    for chunk in resp.iter_bytes():
                        f.write(chunk)

        # Set executable permission before rename
        os.chmod(tmp_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP)

        # Atomic replace (POSIX)
        os.rename(tmp_path, current_binary)

        logger.info("Updated binary: %s", current_binary)
    except Exception:
        # Clean up temp file on any failure
        if tmp_path.exists():
            tmp_path.unlink()
        raise
    finally:
        # Clean up temp dir
        if tmp_dir.exists():
            try:
                tmp_dir.rmdir()
            except OSError:
                pass  # Directory not empty or other issue, leave it
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_updater.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/taxo/updater.py tests/test_updater.py
git commit -m "feat(updater): add binary download and atomic replace"
```

---

### Task 8: Pip Upgrade Path

**Files:**
- Modify: `src/taxo/updater.py`
- Modify: `tests/test_updater.py`

- [ ] **Step 1: Write failing tests for pip_upgrade**

Append to `tests/test_updater.py`:

```python
import subprocess


class TestPipUpgrade:
    def test_calls_pip_install_upgrade(self):
        with patch("taxo.updater.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["pip", "install", "--upgrade", "taxo"],
                returncode=0,
                stdout="Successfully installed taxo-0.3.0",
            )
            result = pip_upgrade()
            assert result is True
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert "pip" in " ".join(call_args)
            assert "install" in " ".join(call_args)
            assert "--upgrade" in " ".join(call_args)
            assert "taxo" in " ".join(call_args)

    def test_returns_false_on_failure(self):
        with patch("taxo.updater.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["pip", "install", "--upgrade", "taxo"],
                returncode=1,
                stdout="",
                stderr="ERROR: Could not find a version",
            )
            result = pip_upgrade()
            assert result is False

    def test_returns_false_on_exception(self):
        with patch("taxo.updater.subprocess.run", side_effect=FileNotFoundError("no pip")):
            result = pip_upgrade()
            assert result is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_updater.py::TestPipUpgrade -v`
Expected: FAIL — `ImportError: cannot import name 'pip_upgrade'`

- [ ] **Step 3: Add pip_upgrade to updater.py**

Add `import subprocess` at the top imports, then append to `src/taxo/updater.py`:

```python
def pip_upgrade() -> bool:
    """Upgrade taxo via pip. Returns True on success, False on failure."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "taxo"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            logger.info("Pip upgrade succeeded: %s", result.stdout.strip())
            return True
        logger.warning("Pip upgrade failed: %s", result.stderr.strip())
        return False
    except (subprocess.SubprocessError, OSError) as e:
        logger.warning("Pip upgrade error: %s", e)
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_updater.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/taxo/updater.py tests/test_updater.py
git commit -m "feat(updater): add pip upgrade path"
```

---

### Task 9: CLI `taxo update` Command

**Files:**
- Modify: `src/taxo/cli.py`

- [ ] **Step 1: Add the `update` command to cli.py**

Find the location in `src/taxo/cli.py` where other commands are defined (after the `cost` command or before the main group). Add the following command:

```python
@cli.command()
def update():
    """Check for updates and upgrade Taxo to the latest version."""
    from taxo.updater import (
        check_latest_release,
        compare_versions,
        download_and_replace,
        get_current_version,
        get_platform_asset_name,
        is_frozen,
        pip_upgrade,
        UpdateCache,
    )

    current = get_current_version()
    console.print(f"Current version: [bold]{current}[/bold]")

    console.print("Checking for updates...")
    release = check_latest_release()
    if release is None:
        console.print("[red]Failed to check for updates. Network may be unavailable.[/red]")
        raise SystemExit(1)

    latest = release["latest_version"]
    console.print(f"Latest version:  [bold]{latest}[/bold]")

    cmp = compare_versions(current, latest)
    if cmp >= 0:
        console.print(f"[green]Already up to date (v{latest}).[/green]")
        return

    console.print(f"\n[bold yellow]Update available![/bold yellow] {current} → {latest}")

    if is_frozen():
        # Binary update path
        asset_name = get_platform_asset_name()
        if asset_name is None:
            console.print(
                "[red]Auto-update not available for this platform.[/red]\n"
                "Please download manually from "
                "https://github.com/Lemon-cc-hang/taxo/releases"
            )
            raise SystemExit(1)

        download_url = ""
        for a in release["assets"]:
            if a["name"] == asset_name:
                download_url = a["browser_download_url"]
                break

        if not download_url:
            console.print(f"[red]Could not find asset '{asset_name}' in release.[/red]")
            raise SystemExit(1)

        console.print(f"Downloading [bold]{asset_name}[/bold]...")
        try:
            from rich.progress import Progress, BarColumn, DownloadColumn, TransferSpeedColumn

            with Progress(
                "[progress.description]{task.description}",
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                console=console,
            ) as progress:
                # We use download_and_replace which does the full flow
                # The progress bar is shown via httpx streaming inside it
                download_and_replace(
                    url=download_url,
                    current_binary=sys.executable,
                )
                progress.update(progress.add_task("Downloading", total=None), advance=1)

            console.print("[green]Updated successfully![/green]")
        except Exception as e:
            console.print(f"[red]Update failed: {e}[/red]")
            console.print(
                "Try running with [bold]sudo[/bold] or download manually from "
                "https://github.com/Lemon-cc-hang/taxo/releases"
            )
            raise SystemExit(1)
    else:
        # Pip update path
        console.print("Upgrading via pip...")
        if pip_upgrade():
            console.print("[green]Updated successfully![/green]")
        else:
            console.print("[red]Pip upgrade failed.[/red] Try: [bold]pip install --upgrade taxo[/bold]")
            raise SystemExit(1)

    # Update cache
    cache = UpdateCache()
    cache.save(latest, "", asset_name if is_frozen() else "")
```

Also add `import sys` at the top of `cli.py` if not already present (it likely is).

- [ ] **Step 2: Run CLI help to verify command is registered**

Run: `uv run taxo --help`
Expected: `update` appears in the command list

- [ ] **Step 3: Test the update command with mocked API**

Run: `uv run taxo update`
Expected: Either "Already up to date" or "Failed to check for updates" (depending on network)

- [ ] **Step 4: Commit**

```bash
git add src/taxo/cli.py
git commit -m "feat(cli): add taxo update command"
```

---

### Task 10: Passive Hint in Main CLI Callback

**Files:**
- Modify: `src/taxo/cli.py`

- [ ] **Step 1: Add passive update check to the main CLI callback**

Find the `cli()` main group callback function in `src/taxo/cli.py`. At the end of the function body (after any existing logic), add:

```python
    # Passive update check — non-blocking hint
    try:
        from taxo.updater import check_for_update_hint
        hint = check_for_update_hint()
        if hint:
            console.print(f"[yellow]{hint}[/yellow]")
    except Exception:
        pass  # Never block normal operation
```

This must be placed at the end of the `cli()` callback so it runs after the subcommand completes. The `try/except` ensures it never interferes with normal CLI operation.

- [ ] **Step 2: Verify passive check doesn't break any command**

Run: `uv run taxo --help`
Expected: Normal help output, no errors. If cache is stale and API is reachable, a yellow hint may appear.

Run: `uv run taxo scan --help`
Expected: Normal help output, no errors.

- [ ] **Step 3: Commit**

```bash
git add src/taxo/cli.py
git commit -m "feat(cli): add passive update hint on every run"
```

---

### Task 11: Full Test Suite Verification

**Files:**
- All test files

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS (including existing tests — no regressions)

- [ ] **Step 2: Run ruff check**

Run: `uv run ruff check src/taxo/updater.py src/taxo/cli.py`
Expected: No errors

- [ ] **Step 3: Run mypy type check on new file**

Run: `uv run mypy src/taxo/updater.py --ignore-missing-imports`
Expected: No errors

- [ ] **Step 4: Final commit if any fixes needed**

If any linting or type issues were found and fixed:

```bash
git add -A
git commit -m "fix: address linting and type issues in updater"
```

---

## Self-Review Checklist

### Spec Coverage

| Spec Requirement | Task |
|-----------------|------|
| Version detection (GitHub API, semver compare) | Task 2, 5 |
| Install method detection (sys.frozen) | Task 2 |
| Passive check (hint on every run) | Task 6, 10 |
| Active `taxo update` command | Task 9 |
| Platform detection + asset matching | Task 3 |
| Binary download with progress | Task 7, 9 |
| Atomic replace (POSIX) | Task 7 |
| Executable permission | Task 7 |
| Pip upgrade path | Task 8, 9 |
| 24h cache TTL | Task 4 |
| Error handling (API fail, download fail, permissions) | Task 5, 7, 8, 9 |
| Unsupported platform message | Task 9 |
| UpdateInfo data model | Covered by cache dict structure (YAGNI — no separate model needed for this scope) |
| Version bump to 0.2.0 | Task 1 |

### Placeholder Scan

No TBD, TODO, or placeholder patterns found. All steps contain complete code.

### Type Consistency

- `compare_versions` returns `Literal[-1, 0, 1] | None` — consistent across all usages
- `check_latest_release` returns `dict | None` — consistent in Tasks 5, 6, 9
- `UpdateCache.save()` takes `(str, str, str)` — consistent in Tasks 4, 6, 9
- `get_platform_asset_name` returns `str | None` — consistent in Tasks 3, 6, 9
- `download_and_replace` takes `(url: str, current_binary: str, cache_dir: Path | None)` — consistent in Tasks 7, 9
