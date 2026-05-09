from datetime import datetime
from pathlib import Path

from rich.console import Console

from taxo.display import (
    print_scan_table,
    print_plan_preview,
    print_execute_result,
    print_history,
)
from taxo.models import (
    ClassifyResult,
    FileItem,
    HistoryEntry,
    MoveOperation,
    Plan,
    PlanStats,
)
from taxo.executor import ExecuteResult


def make_file(name: str) -> FileItem:
    stem, _, e = name.rpartition(".")
    if not stem:
        stem, e = name, ""
    else:
        e = f".{e}"
    return FileItem(
        path=Path(f"/tmp/{name}"),
        name=stem,
        ext=e.lower(),
        size=1024,
        mtime=datetime(2026, 5, 1, 12, 0, 0),
        ctime=datetime(2026, 5, 1, 12, 0, 0),
        is_hidden=False,
        is_symlink=False,
    )


class TestPrintScanTable:
    def test_renders_without_error(self):
        console = Console(file=open("/dev/null", "w"), width=120)
        results = [
            ClassifyResult(
                file=make_file("report.pdf"),
                category="文档",
                subcategory=None,
                confidence=1.0,
                method="rule",
                reason="test",
            ),
        ]
        print_scan_table(console, results)

    def test_empty_results(self):
        console = Console(file=open("/dev/null", "w"), width=120)
        print_scan_table(console, [])


class TestPrintPlanPreview:
    def test_renders_plan(self):
        console = Console(file=open("/dev/null", "w"), width=120)
        plan = Plan(
            source_dir=Path("/tmp"),
            operations=[
                MoveOperation(
                    source=Path("/tmp/a.pdf"),
                    target=Path("/tmp/文档/a.pdf"),
                    action="move",
                    reason="test",
                )
            ],
            stats=PlanStats(
                total_files=1, total_size=1024, by_category={"文档": 1},
                api_calls=0, estimated_cost=0.0, duration_ms=0,
            ),
        )
        print_plan_preview(console, plan)


class TestPrintExecuteResult:
    def test_renders_result(self):
        console = Console(file=open("/dev/null", "w"), width=120)
        result = ExecuteResult(plan_id="test", total=3, success=2, failed=0, skipped=1)
        print_execute_result(console, result)


class TestPrintHistory:
    def test_renders_entries(self):
        console = Console(file=open("/dev/null", "w"), width=120)
        entries = [
            HistoryEntry(
                id="h1",
                timestamp=datetime(2026, 5, 1, 12, 0, 0),
                command="taxo organize ~/Downloads",
                plan_id="p1",
                status="success",
                operations=[],
            ),
        ]
        print_history(console, entries)

    def test_empty_entries(self):
        console = Console(file=open("/dev/null", "w"), width=120)
        print_history(console, [])
