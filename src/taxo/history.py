from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from taxo.models import HistoryEntry


class HistoryManager:
    def __init__(self, filepath: Path) -> None:
        self._filepath = filepath

    def record(self, entry: HistoryEntry) -> None:
        self._filepath.parent.mkdir(parents=True, exist_ok=True)
        line = entry.model_dump_json() + "\n"
        with open(self._filepath, "a") as f:
            f.write(line)

    def list_entries(
        self,
        limit: int = 20,
        since: datetime | None = None,
    ) -> list[HistoryEntry]:
        entries = self._read_all()
        if since:
            entries = [e for e in entries if e.timestamp >= since]
        return entries[-limit:]

    def get_last(self) -> HistoryEntry | None:
        entries = self._read_all()
        return entries[-1] if entries else None

    def get_by_id(self, id: str) -> HistoryEntry | None:
        for entry in self._read_all():
            if entry.id == id:
                return entry
        return None

    def mark_undone(self, id: str) -> None:
        entries = self._read_all()
        self._filepath.unlink(missing_ok=True)
        for entry in entries:
            if entry.id == id:
                entry.undo_available = False
                entry.undo_timestamp = datetime.now()
            self.record(entry)

    def _read_all(self) -> list[HistoryEntry]:
        if not self._filepath.exists():
            return []
        entries: list[HistoryEntry] = []
        with open(self._filepath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                entries.append(HistoryEntry(**data))
        return entries
