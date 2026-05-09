from __future__ import annotations

import logging
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pydantic import BaseModel

from taxo.history import HistoryManager
from taxo.models import HistoryEntry, MoveOperation, Plan

logger = logging.getLogger(__name__)


class ExecuteResult(BaseModel):
    plan_id: str
    total: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    errors: list[str] = []


class Executor:
    def __init__(self, history_manager: HistoryManager, move_workers: int = 4) -> None:
        self._history = history_manager
        self._move_workers = move_workers

    def execute(self, plan: Plan, dry_run: bool = True) -> ExecuteResult:
        if dry_run:
            return ExecuteResult(plan_id=plan.id, total=len(plan.operations))

        skip_ops: list[MoveOperation] = []
        move_ops: list[MoveOperation] = []

        for op in plan.operations:
            if op.action == "skip":
                skip_ops.append(op.model_copy(update={"status": "skipped"}))
            else:
                move_ops.append(op)

        # Pre-create all target directories (sequential, avoids race conditions)
        dest_dirs: set[Path] = set()
        for op in move_ops:
            dest_dirs.add(Path(op.target).parent)
        for d in dest_dirs:
            d.mkdir(parents=True, exist_ok=True)

        succeeded: list[MoveOperation] = []
        failed_list: list[tuple[MoveOperation, str]] = []
        lock = threading.Lock()

        def move_one(op: MoveOperation) -> None:
            try:
                target = Path(op.target)
                shutil.move(str(op.source), str(target))
                with lock:
                    succeeded.append(op.model_copy(update={"status": "success"}))
            except Exception as e:
                with lock:
                    failed_list.append((op, str(e)))
                logger.warning(f"Failed to move {op.source} -> {op.target}: {e}")

        if len(move_ops) <= 1 or self._move_workers <= 1:
            for op in move_ops:
                move_one(op)
        else:
            with ThreadPoolExecutor(max_workers=self._move_workers) as pool:
                futures = [pool.submit(move_one, op) for op in move_ops]
                for f in as_completed(futures):
                    pass

        errors = [f"{op.source}: {err}" for op, err in failed_list]
        failed_ops = [op.model_copy(update={"status": "failed"}) for op, _ in failed_list]

        total_success = len(succeeded)
        total_failed = len(failed_list)
        total_skipped = len(skip_ops)

        status = "success" if total_failed == 0 else ("partial" if total_success > 0 else "failed")

        # Maintain original order for history
        completed_ops = skip_ops + succeeded + failed_ops

        entry = HistoryEntry(
            plan_id=plan.id,
            command="taxo organize",
            status=status,
            operations=completed_ops,
        )
        self._history.record(entry)

        return ExecuteResult(
            plan_id=plan.id,
            total=len(plan.operations),
            success=total_success,
            failed=total_failed,
            skipped=total_skipped,
            errors=errors,
        )

    def undo(self, step: int = 1) -> ExecuteResult:
        entries = self._history.list_entries(limit=step + 10)
        undoable = [e for e in entries if e.undo_available]
        if not undoable:
            return ExecuteResult(plan_id="")

        target = undoable[-step] if step <= len(undoable) else None
        if target is None:
            return ExecuteResult(plan_id="")

        success = 0
        failed = 0
        errors: list[str] = []

        for op in reversed(target.operations):
            if op.status != "success":
                continue
            try:
                source = Path(op.source)
                target_path = Path(op.target)
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target_path), str(source))
                success += 1
            except Exception as e:
                failed += 1
                errors.append(f"Undo {op.target}: {e}")
                logger.warning(f"Failed to undo {op.target} -> {op.source}: {e}")

        self._history.mark_undone(target.id)

        return ExecuteResult(
            plan_id=target.id,
            total=success + failed,
            success=success,
            failed=failed,
            errors=errors,
        )
