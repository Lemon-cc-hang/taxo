from __future__ import annotations

from datetime import datetime
from pathlib import Path

from taxo.config import OrganizeConfig
from taxo.models import (
    ClassifyResult,
    FileItem,
    MoveOperation,
    Plan,
    PlanStats,
)


class Planner:
    def __init__(self, config: OrganizeConfig) -> None:
        self._config = config

    def create_plan(
        self,
        results: list[ClassifyResult],
        source_dir: Path,
    ) -> Plan:
        target_root = (
            Path(self._config.target_dir) if self._config.target_dir else source_dir
        )
        operations: list[MoveOperation] = []
        by_category: dict[str, int] = {}

        for result in results:
            category = result.category
            by_category[category] = by_category.get(category, 0) + 1

            target_path = self._resolve_target(
                target_root, category, result.file, result.file.mtime
            )
            action, final_target = self._resolve_conflict(result.file, target_path)

            operations.append(
                MoveOperation(
                    source=result.file.path,
                    target=final_target,
                    action=action,
                    reason=f"分类: {category}",
                )
            )

        stats = PlanStats(
            total_files=len(results),
            total_size=sum(r.file.size for r in results),
            by_category=by_category,
            api_calls=0,
            estimated_cost=0.0,
            duration_ms=0,
        )

        return Plan(
            source_dir=source_dir,
            operations=operations,
            stats=stats,
        )

    def _resolve_target(
        self, root: Path, category: str, file: FileItem, mtime: datetime
    ) -> Path:
        filename = file.name + file.ext
        if self._config.structure == "date":
            template = self._config.date_template
            relative = template.format(
                category=category,
                year=str(mtime.year),
                month=f"{mtime.month:02d}",
            )
            return root / relative / filename

        return root / category / filename

    def _resolve_conflict(
        self, file: FileItem, target: Path
    ) -> tuple[str, Path]:
        if not target.exists():
            return "move", target

        if self._config.conflict_strategy == "skip":
            return "skip", target

        parent = target.parent
        stem = file.name
        ext = file.ext
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        new_target = parent / f"{stem}_{timestamp}{ext}"

        counter = 1
        while new_target.exists():
            new_target = parent / f"{stem}_{timestamp}_{counter}{ext}"
            counter += 1

        return "rename", new_target
