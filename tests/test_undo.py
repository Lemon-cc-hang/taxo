import pytest
import shutil
from pathlib import Path

from taxo.executor import Executor
from taxo.history import HistoryManager
from taxo.models import MoveOperation, Plan, PlanStats


class TestUndo:
    def test_undo_moves_files_back(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        dest = tmp_path / "dest"
        dest.mkdir()
        (src / "file.txt").write_text("content")

        hm = HistoryManager(tmp_path / "history.jsonl")
        executor = Executor(hm)

        plan = Plan(
            source_dir=src,
            operations=[
                MoveOperation(source=src / "file.txt", target=dest / "file.txt", action="move", reason="test")
            ],
            stats=PlanStats(total_files=1, total_size=7, by_category={"test": 1}, api_calls=0, estimated_cost=0.0, duration_ms=0),
        )

        executor.execute(plan, dry_run=False)
        assert (dest / "file.txt").exists()
        assert not (src / "file.txt").exists()

        result = executor.undo()
        assert result.success == 1
        assert (src / "file.txt").exists()
        assert not (dest / "file.txt").exists()
        assert (src / "file.txt").read_text() == "content"

    def test_undo_creates_source_dir_if_missing(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        dest = tmp_path / "dest"
        dest.mkdir()
        (src / "file.txt").write_text("content")

        hm = HistoryManager(tmp_path / "history.jsonl")
        executor = Executor(hm)

        plan = Plan(
            source_dir=src,
            operations=[
                MoveOperation(source=src / "file.txt", target=dest / "file.txt", action="move", reason="test")
            ],
            stats=PlanStats(total_files=1, total_size=7, by_category={"test": 1}, api_calls=0, estimated_cost=0.0, duration_ms=0),
        )

        executor.execute(plan, dry_run=False)
        shutil.rmtree(src)

        result = executor.undo()
        assert result.success == 1
        assert (src / "file.txt").exists()

    def test_undo_no_history(self, tmp_path):
        hm = HistoryManager(tmp_path / "history.jsonl")
        executor = Executor(hm)
        result = executor.undo()
        assert result.total == 0

    def test_undo_skips_already_undone(self, tmp_path):
        src = tmp_path / "source"
        src.mkdir()
        dest = tmp_path / "dest"
        dest.mkdir()
        (src / "file.txt").write_text("content")

        hm = HistoryManager(tmp_path / "history.jsonl")
        executor = Executor(hm)

        plan = Plan(
            source_dir=src,
            operations=[
                MoveOperation(source=src / "file.txt", target=dest / "file.txt", action="move", reason="test")
            ],
            stats=PlanStats(total_files=1, total_size=7, by_category={"test": 1}, api_calls=0, estimated_cost=0.0, duration_ms=0),
        )

        executor.execute(plan, dry_run=False)
        executor.undo()
        result = executor.undo()
        assert result.total == 0
