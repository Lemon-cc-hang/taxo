from __future__ import annotations

import json
import hashlib
import logging
import time
from datetime import datetime
from pathlib import Path

from taxo.models import ClassifyResult, FileItem

logger = logging.getLogger(__name__)

_DEFAULT_TTL_DAYS = 30
_DEFAULT_MAX_ENTRIES = 10000


class CacheManager:
    def __init__(
        self,
        cache_dir: Path,
        ttl_days: int = _DEFAULT_TTL_DAYS,
        max_entries: int = _DEFAULT_MAX_ENTRIES,
    ) -> None:
        self._cache_dir = cache_dir
        self._ttl_days = ttl_days
        self._max_entries = max_entries
        self._entries: dict[str, dict] = {}
        self._current_dir: Path | None = None
        self._current_dir_key: str | None = None
        self._dirty = False

    def load(self, dir_path: Path) -> None:
        self._current_dir = dir_path
        self._current_dir_key = self._dir_key(dir_path)
        self._entries = {}
        self._dirty = False

        cache_path = self._cache_path()
        if not cache_path.exists():
            return

        try:
            data = json.loads(cache_path.read_text())
        except (json.JSONDecodeError, OSError):
            return

        if not isinstance(data, dict):
            return

        now = time.time()
        ttl_seconds = self._ttl_days * 86400
        pruned = 0

        for key, entry in data.items():
            cached_at = entry.get("cached_at", 0)
            if now - cached_at > ttl_seconds:
                pruned += 1
                continue

            self._entries[key] = entry

        if pruned > 0:
            self._dirty = True
            logger.debug(f"Cache pruned {pruned} expired entries for {dir_path}")

        if len(self._entries) > self._max_entries:
            sorted_entries = sorted(
                self._entries.items(), key=lambda x: x[1].get("cached_at", 0)
            )
            self._entries = dict(sorted_entries[-self._max_entries:])
            self._dirty = True
            logger.debug(f"Cache trimmed to {self._max_entries} entries")

    def get(self, file: FileItem) -> ClassifyResult | None:
        key = self._file_key(file)
        entry = self._entries.get(key)
        if entry is None:
            return None

        if not self._entry_valid(entry, file):
            del self._entries[key]
            self._dirty = True
            return None

        try:
            return ClassifyResult.model_validate_json(entry["result"])
        except Exception:
            del self._entries[key]
            self._dirty = True
            return None

    def put(self, result: ClassifyResult) -> None:
        key = self._file_key(result.file)
        self._entries[key] = {
            "path": str(result.file.path),
            "name": result.file.name + result.file.ext,
            "size": result.file.size,
            "mtime": result.file.mtime if isinstance(result.file.mtime, (int, float)) else result.file.mtime.timestamp(),
            "cached_at": time.time(),
            "result": result.model_dump_json(),
        }
        self._dirty = True

    def save(self) -> None:
        if not self._dirty or not self._current_dir_key:
            return

        self._cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = self._cache_path()
        cache_path.write_text(json.dumps(self._entries, ensure_ascii=False))

    def stats(self) -> dict[str, int]:
        return {
            "total": len(self._entries),
            "max": self._max_entries,
        }

    def clear(self, dir_path: Path | None = None) -> int:
        if dir_path:
            cache_path = self._cache_dir / f"scan_{self._dir_key(dir_path)}.json"
            if cache_path.exists():
                cache_path.unlink()
                return 1
            return 0
        count = 0
        for f in self._cache_dir.glob("scan_*.json"):
            f.unlink()
            count += 1
        return count

    def _file_key(self, file: FileItem) -> str:
        mtime = file.mtime if isinstance(file.mtime, (int, float)) else file.mtime.timestamp()
        return f"{file.path}:{file.size}:{mtime}"

    def _dir_key(self, dir_path: Path) -> str:
        return hashlib.md5(str(dir_path.resolve()).encode()).hexdigest()[:12]

    def _cache_path(self) -> Path:
        return self._cache_dir / f"scan_{self._current_dir_key}.json"

    def _entry_valid(self, entry: dict, file: FileItem) -> bool:
        if entry.get("size") != file.size:
            return False
        cached_mtime = entry.get("mtime", 0)
        current_mtime = file.mtime if isinstance(file.mtime, (int, float)) else file.mtime.timestamp()
        if cached_mtime != current_mtime:
            return False
        return True
