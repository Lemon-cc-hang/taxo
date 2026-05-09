import pytest
from pathlib import Path

from taxo.executor import Executor
from taxo.history import HistoryManager
from taxo.models import MoveOperation, Plan, PlanStats


def make_plan(source: Path, ops: list[tuple[str, str, str]]) -> Plan:
    operations = [
        MoveOperation(source=Path(s), target=Path(t), action=a, reason="test")
        for s, t, a in ops
    ]
    return Plan(
        source_dir=source,
        operations=operations,
        stats=PlanStats(total_files=len(operations), total_size=0, by_category={}, api_calls=0, estimated_cost=0.0, duration_ms=0),
    )


class TestExecutorDryRun:
    def test_dry_run_does_not_move(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "file.txt").write_text("content")
        hm = HistoryManager(tmp_path / "history.jsonl")
        executor = Executor(hm)
        plan = make_plan(src, [(str(src / "file.txt"), str(tmp_path / "dest" / "file.txt"), "move")])
        result = executor.execute(plan, dry_run=True)
        assert result.total == 1
        assert result.success == 0
        assert (src / "file.txt").exists()

    def test_dry_run_returns_pending_counts(self, tmp_path):
        hm = HistoryManager(tmp_path / "history.jsonl")
        executor = Executor(hm)
        plan = make_plan(tmp_path, [("/tmp/a.txt", "/tmp/b.txt", "move"), ("/tmp/c.txt", "/tmp/d.txt", "skip")])
        result = executor.execute(plan, dry_run=True)
        assert result.total == 2


class TestExecutorRealRun:
    def test_move_file(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "file.txt").write_text("hello")
        dest = tmp_path / "dest"
        dest.mkdir()
        hm = HistoryManager(tmp_path / "history.jsonl")
        executor = Executor(hm)
        plan = make_plan(src, [(str(src / "file.txt"), str(dest / "file.txt"), "move")])
        result = executor.execute(plan, dry_run=False)
        assert result.success == 1
        assert result.failed == 0
        assert (dest / "file.txt").exists()
        assert not (src / "file.txt").exists()
        assert (dest / "file.txt").read_text() == "hello"

    def test_creates_target_directory(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "file.txt").write_text("content")
        dest = tmp_path / "deep" / "nested" / "dir"
        hm = HistoryManager(tmp_path / "history.jsonl")
        executor = Executor(hm)
        plan = make_plan(src, [(str(src / "file.txt"), str(dest / "file.txt"), "move")])
        result = executor.execute(plan, dry_run=False)
        assert result.success == 1
        assert (dest / "file.txt").exists()

    def test_skip_operation(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "file.txt").write_text("content")
        hm = HistoryManager(tmp_path / "history.jsonl")
        executor = Executor(hm)
        plan = make_plan(src, [(str(src / "file.txt"), str(tmp_path / "dest" / "file.txt"), "skip")])
        result = executor.execute(plan, dry_run=False)
        assert result.skipped == 1
        assert (src / "file.txt").exists()

    def test_single_failure_continues(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "good.txt").write_text("ok")
        hm = HistoryManager(tmp_path / "history.jsonl")
        executor = Executor(hm)
        plan = make_plan(src, [
            (str(src / "missing.txt"), str(tmp_path / "dest" / "missing.txt"), "move"),
            (str(src / "good.txt"), str(tmp_path / "dest" / "good.txt"), "move"),
        ])
        (tmp_path / "dest").mkdir()
        result = executor.execute(plan, dry_run=False)
        assert result.success == 1
        assert result.failed == 1
        assert len(result.errors) == 1

    def test_records_to_history(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "file.txt").write_text("content")
        dest = tmp_path / "dest"
        dest.mkdir()
        hm = HistoryManager(tmp_path / "history.jsonl")
        executor = Executor(hm)
        plan = make_plan(src, [(str(src / "file.txt"), str(dest / "file.txt"), "move")])
        executor.execute(plan, dry_run=False)
        last = hm.get_last()
        assert last is not None
        assert last.status == "success"

    def test_all_failed_status(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        hm = HistoryManager(tmp_path / "history.jsonl")
        executor = Executor(hm)
        plan = make_plan(src, [(str(src / "missing.txt"), str(tmp_path / "dest" / "missing.txt"), "move")])
        result = executor.execute(plan, dry_run=False)
        assert result.failed == 1
        last = hm.get_last()
        assert last is not None
        assert last.status == "failed"
