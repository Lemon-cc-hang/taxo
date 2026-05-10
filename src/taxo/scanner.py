from __future__ import annotations

import fnmatch
import os
import unicodedata
from pathlib import Path

from taxo.config import ScanConfig
from taxo.models import FileItem

SYSTEM_FILES = {
    ".DS_Store",
    ".localized",
    "Thumbs.db",
    "desktop.ini",
}

SYSTEM_DIR_PREFIXES = (
    ".Spotlight-V100",
    ".Trashes",
    ".fseventsd",
    "$RECYCLE.BIN",
)


def scan_files(directory: Path, config: ScanConfig) -> list[FileItem]:
    if not directory.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")

    results: list[FileItem] = []
    _scan_recursive(directory, directory, config, 0, results)
    return results


def _scan_recursive(
    root: Path,
    current: Path,
    config: ScanConfig,
    depth: int,
    results: list[FileItem],
) -> None:
    if config.max_depth is not None and depth > config.max_depth:
        return

    try:
        entries = os.scandir(current)
    except PermissionError:
        return

    for entry in entries:
        name = entry.name

        if entry.is_symlink():
            continue

        if entry.is_dir(follow_symlinks=False):
            if _should_skip_dir(name, config):
                continue
            _scan_recursive(root, Path(entry.path), config, depth + 1, results)
            continue

        if not entry.is_file(follow_symlinks=False):
            continue

        if _should_skip_file(name, config):
            continue

        stat = entry.stat(follow_symlinks=False)
        if stat.st_size < config.min_size:
            continue
        if config.max_size is not None and stat.st_size > config.max_size:
            continue

        normalized_name = unicodedata.normalize("NFC", name)
        stem, ext = _split_ext(normalized_name)

        results.append(
            FileItem(
                path=Path(entry.path),
                name=stem,
                ext=ext.lower(),
                size=stat.st_size,
                mtime=stat.st_mtime,
                ctime=stat.st_ctime,
                is_hidden=name.startswith("."),
                is_symlink=False,
            )
        )


def _should_skip_dir(name: str, config: ScanConfig) -> bool:
    if name in config.exclude_dirs:
        return True
    for prefix in SYSTEM_DIR_PREFIXES:
        if name.startswith(prefix):
            return True
    return False


def _should_skip_file(name: str, config: ScanConfig) -> bool:
    if name in SYSTEM_FILES:
        return True
    for pattern in config.exclude:
        if fnmatch.fnmatch(name, pattern):
            return True
    return False


def _split_ext(name: str) -> tuple[str, str]:
    if name.startswith(".") and "." not in name[1:]:
        return name, ""
    stem, _, ext = name.rpartition(".")
    if not stem or not ext:
        return name, ""
    return stem, f".{ext}"


def scan_dir_structure(directory: Path) -> list[str]:
    """Return direct subdirectory names (non-hidden) for semantic mode context."""
    dirs = []
    try:
        for entry in os.scandir(directory):
            if entry.is_dir(follow_symlinks=False) and not entry.name.startswith("."):
                dirs.append(entry.name)
    except (PermissionError, FileNotFoundError):
        pass
    return sorted(dirs)
