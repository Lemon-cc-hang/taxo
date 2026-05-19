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


class TestExecutorConcurrency:
    def test_concurrent_moves(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        dest = tmp_path / "dest"
        dest.mkdir()
        files = []
        for i in range(10):
            f = src / f"file{i}.txt"
            f.write_text(f"content_{i}")
            files.append((str(f), str(dest / f"file{i}.txt"), "move"))

        hm = HistoryManager(tmp_path / "history.jsonl")
        executor = Executor(hm, move_workers=4)
        plan = make_plan(src, files)
        result = executor.execute(plan, dry_run=False)
        assert result.success == 10
        assert result.failed == 0
        for i in range(10):
            assert (dest / f"file{i}.txt").read_text() == f"content_{i}"

    def test_concurrent_creates_target_dirs(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        files = []
        for i in range(5):
            f = src / f"file{i}.txt"
            f.write_text(f"x_{i}")
            target = tmp_path / f"cat{i}" / f"file{i}.txt"
            files.append((str(f), str(target), "move"))

        hm = HistoryManager(tmp_path / "history.jsonl")
        executor = Executor(hm, move_workers=4)
        plan = make_plan(src, files)
        result = executor.execute(plan, dry_run=False)
        assert result.success == 5
        for i in range(5):
            assert (tmp_path / f"cat{i}" / f"file{i}.txt").exists()

    def test_single_worker_is_serial(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        dest = tmp_path / "dest"
        dest.mkdir()
        (src / "a.txt").write_text("a")
        (src / "b.txt").write_text("b")

        hm = HistoryManager(tmp_path / "history.jsonl")
        executor = Executor(hm, move_workers=1)
        plan = make_plan(src, [
            (str(src / "a.txt"), str(dest / "a.txt"), "move"),
            (str(src / "b.txt"), str(dest / "b.txt"), "move"),
        ])
        result = executor.execute(plan, dry_run=False)
        assert result.success == 2
        assert (dest / "a.txt").exists()
        assert (dest / "b.txt").exists()


class TestCleanEmptyDirs:
    def test_cleans_empty_dirs_after_move(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "sub1").mkdir()
        (src / "sub1" / "deep").mkdir()
        (src / "sub1" / "deep" / "file.txt").write_text("hello")
        dest = tmp_path / "dest"
        dest.mkdir()

        hm = HistoryManager(tmp_path / "history.jsonl")
        executor = Executor(hm)
        plan = make_plan(src, [
            (str(src / "sub1" / "deep" / "file.txt"), str(dest / "file.txt"), "move"),
        ])
        result = executor.execute(plan, dry_run=False)
        assert result.success == 1
        assert result.cleaned_dirs == 2  # deep + sub1
        assert not (src / "sub1").exists()

    def test_keeps_nonempty_dirs(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "sub").mkdir()
        (src / "sub" / "remaining.txt").write_text("stay")
        dest = tmp_path / "dest"
        dest.mkdir()

        hm = HistoryManager(tmp_path / "history.jsonl")
        executor = Executor(hm)
        plan = make_plan(src, [])
        result = executor.execute(plan, dry_run=False)
        assert result.cleaned_dirs == 0
        assert (src / "sub").exists()

    def test_does_not_remove_source_root(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "file.txt").write_text("hello")
        dest = tmp_path / "dest"
        dest.mkdir()

        hm = HistoryManager(tmp_path / "history.jsonl")
        executor = Executor(hm)
        plan = make_plan(src, [
            (str(src / "file.txt"), str(dest / "file.txt"), "move"),
        ])
        result = executor.execute(plan, dry_run=False)
        assert result.success == 1
        assert result.cleaned_dirs == 0  # source_dir itself is not removed even if empty
        assert src.exists()

    def test_nested_empty_dirs_all_removed(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        (src / "a" / "b" / "c").mkdir(parents=True)
        (src / "a" / "b" / "c" / "file.txt").write_text("x")
        dest = tmp_path / "dest"
        dest.mkdir()

        hm = HistoryManager(tmp_path / "history.jsonl")
        executor = Executor(hm)
        plan = make_plan(src, [
            (str(src / "a" / "b" / "c" / "file.txt"), str(dest / "file.txt"), "move"),
        ])
        result = executor.execute(plan, dry_run=False)
        assert result.success == 1
        assert result.cleaned_dirs == 3  # c, b, a
        assert not (src / "a").exists()
