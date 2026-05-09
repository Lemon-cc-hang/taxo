from __future__ import annotations

import logging
import shutil
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
    def __init__(self, history_manager: HistoryManager) -> None:
        self._history = history_manager

    def execute(self, plan: Plan, dry_run: bool = True) -> ExecuteResult:
        if dry_run:
            return ExecuteResult(plan_id=plan.id, total=len(plan.operations))

        success = 0
        failed = 0
        skipped = 0
        errors: list[str] = []
        completed_ops: list[MoveOperation] = []

        for op in plan.operations:
            if op.action == "skip":
                skipped += 1
                completed_ops.append(op.model_copy(update={"status": "skipped"}))
                continue

            try:
                target = Path(op.target)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(op.source), str(target))
                success += 1
                completed_ops.append(op.model_copy(update={"status": "success"}))
            except Exception as e:
                failed += 1
                errors.append(f"{op.source}: {e}")
                completed_ops.append(op.model_copy(update={"status": "failed"}))
                logger.warning(f"Failed to move {op.source} -> {op.target}: {e}")

        status = "success" if failed == 0 else ("partial" if success > 0 else "failed")

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
            success=success,
            failed=failed,
            skipped=skipped,
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
