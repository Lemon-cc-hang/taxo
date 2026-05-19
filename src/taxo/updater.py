"""Auto-update system for Taxo CLI.

Checks GitHub Releases for new versions, downloads and replaces
the binary (or runs pip upgrade) when an update is available.
"""
from __future__ import annotations

import platform as _platform
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


PLATFORM_MAP: dict[tuple[str, str], str] = {
    ("Darwin", "arm64"): "taxo-macos-arm64",
    ("Linux", "x86_64"): "taxo-linux-x86_64",
    ("Windows", "AMD64"): "taxo-windows-x86_64.exe",
}


def get_platform_asset_name() -> str | None:
    """Return the release asset name for the current platform, or None if unsupported."""
    key = (_platform.system(), _platform.machine())
    return PLATFORM_MAP.get(key)
