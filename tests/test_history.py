import pytest
from datetime import datetime
from pathlib import Path

from taxo.history import HistoryManager
from taxo.models import HistoryEntry, MoveOperation


def make_entry(command: str = "taxo organize /tmp", status: str = "success", ops: list[MoveOperation] | None = None) -> HistoryEntry:
    return HistoryEntry(
        timestamp=datetime(2026, 5, 1, 12, 0, 0),
        command=command,
        plan_id="plan-123",
        status=status,
        operations=ops or [],
    )


class TestHistoryManager:
    def test_record_and_list(self, tmp_path):
        hm = HistoryManager(tmp_path / "history.jsonl")
        entry = make_entry()
        hm.record(entry)
        entries = hm.list_entries()
        assert len(entries) == 1
        assert entries[0].command == "taxo organize /tmp"

    def test_list_with_limit(self, tmp_path):
        hm = HistoryManager(tmp_path / "history.jsonl")
        for i in range(5):
            hm.record(make_entry(command=f"cmd {i}"))
        entries = hm.list_entries(limit=3)
        assert len(entries) == 3

    def test_get_last(self, tmp_path):
        hm = HistoryManager(tmp_path / "history.jsonl")
        hm.record(make_entry(command="first"))
        hm.record(make_entry(command="second"))
        last = hm.get_last()
        assert last is not None
        assert last.command == "second"

    def test_get_last_empty(self, tmp_path):
        hm = HistoryManager(tmp_path / "history.jsonl")
        assert hm.get_last() is None

    def test_get_by_id(self, tmp_path):
        hm = HistoryManager(tmp_path / "history.jsonl")
        entry = make_entry()
        hm.record(entry)
        found = hm.get_by_id(entry.id)
        assert found is not None
        assert found.id == entry.id

    def test_get_by_id_not_found(self, tmp_path):
        hm = HistoryManager(tmp_path / "history.jsonl")
        assert hm.get_by_id("nonexistent") is None

    def test_jsonl_format(self, tmp_path):
        filepath = tmp_path / "history.jsonl"
        hm = HistoryManager(filepath)
        hm.record(make_entry(command="test"))
        hm.record(make_entry(command="test2"))
        content = filepath.read_text()
        lines = [l for l in content.strip().split("\n") if l]
        assert len(lines) == 2

    def test_create_file_if_not_exists(self, tmp_path):
        filepath = tmp_path / "history.jsonl"
        assert not filepath.exists()
        hm = HistoryManager(filepath)
        hm.record(make_entry())
        assert filepath.exists()

    def test_list_since_date(self, tmp_path):
        hm = HistoryManager(tmp_path / "history.jsonl")
        old = make_entry()
        old.timestamp = datetime(2026, 1, 1, 0, 0, 0)
        hm.record(old)
        recent = make_entry()
        recent.timestamp = datetime(2026, 5, 1, 12, 0, 0)
        hm.record(recent)
        entries = hm.list_entries(since=datetime(2026, 4, 1, 0, 0, 0))
        assert len(entries) == 1
        assert entries[0].timestamp.month == 5

    def test_record_with_operations(self, tmp_path):
        hm = HistoryManager(tmp_path / "history.jsonl")
        ops = [
            MoveOperation(
                source=Path("/tmp/a.pdf"),
                target=Path("/tmp/文档/a.pdf"),
                action="move",
                reason="test",
                status="success",
            )
        ]
        entry = make_entry(ops=ops)
        hm.record(entry)
        found = hm.get_by_id(entry.id)
        assert found is not None
        assert len(found.operations) == 1
        assert found.operations[0].source == Path("/tmp/a.pdf")
