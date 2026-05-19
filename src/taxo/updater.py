"""Auto-update system for Taxo CLI.

Checks GitHub Releases for new versions, downloads and replaces
the binary (or runs pip upgrade) when an update is available.
"""
from __future__ import annotations

import json
import logging
import os
import platform as _platform
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Literal

import httpx

from taxo import __version__

logger = logging.getLogger(__name__)


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

    for cur, lat in zip(c_parts, l_parts):
        if cur < lat:
            return -1
        if cur > lat:
            return 1
    return 0


PLATFORM_MAP: dict[tuple[str, str], str] = {
    ("Darwin", "arm64"): "taxo-macos-arm64",
    ("Linux", "x86_64"): "taxo-linux-x86_64",
    ("Windows", "AMD64"): "taxo-windows-x86_64.exe",
}


def get_platform_asset_name() -> str | None:
    """Return the release asset name for the current platform, or None if unsupported."""
    key = (_platform.system(), _platform.machine())
    return PLATFORM_MAP.get(key)


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
