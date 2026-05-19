"""Auto-update system for Taxo CLI.

Checks GitHub Releases for new versions, downloads and replaces
the binary (or runs pip upgrade) when an update is available.
"""
from __future__ import annotations

import json
import logging
import platform as _platform
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

    for c, l in zip(c_parts, l_parts):
        if c < l:
            return -1
        if c > l:
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
