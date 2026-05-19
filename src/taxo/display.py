from __future__ import annotations

from rich.console import Console
from rich.table import Table

from taxo.executor import ExecuteResult
from taxo.models import (
    ClassifyResult,
    HistoryEntry,
    Plan,
)


def print_scan_table(console: Console, results: list[ClassifyResult], total_ms: int = 0) -> None:
    if not results:
        console.print("[dim]No files found.[/dim]")
        return

    table = Table(title="Scan Results")
    table.add_column("File", style="cyan")
    table.add_column("Size", justify="right")
    table.add_column("Category", style="green")
    table.add_column("Method", style="yellow")
    table.add_column("Time", justify="right", style="dim")

    for r in results:
        filename = r.file.name + r.file.ext
        size = _format_size(r.file.size)
        time_str = f"{r.duration_ms}ms" if r.duration_ms > 0 else "-"
        table.add_row(filename, size, r.category, r.method, time_str)

    console.print(table)

    rule_count = sum(1 for r in results if r.method == "rule")
    llm_count = sum(1 for r in results if r.method == "llm")
    uncategorized = sum(1 for r in results if r.category == "未分类")
    stats = (
        f"\nStats: {len(results)} files, "
        f"{rule_count} rule-classified, "
        f"{llm_count} llm-classified, "
        f"{uncategorized} uncategorized"
    )
    if total_ms > 0:
        stats += f", {total_ms / 1000:.1f}s elapsed"
    console.print(stats)


def print_plan_preview(console: Console, plan: Plan) -> None:
    console.print(
        f"\n[bold]Plan:[/bold] move {plan.stats.total_files} files "
        f"from {plan.source_dir} to organized folders\n"
    )

    for op in plan.operations:
        if op.action == "skip":
            console.print(f"  [yellow]SKIP[/yellow] {op.source}")
        else:
            console.print(f"  {op.source} [dim]→[/dim] {op.target}")

    console.print(
        f"\n[dim]{plan.stats.total_files} files, "
        f"{_format_size(plan.stats.total_size)}[/dim]"
    )


def print_execute_result(console: Console, result: ExecuteResult) -> None:
    if result.success > 0:
        console.print(f"[green]+ {result.success} files moved[/green]")
    if result.skipped > 0:
        console.print(f"[yellow]- {result.skipped} files skipped[/yellow]")
    if result.failed > 0:
        console.print(f"[red]x {result.failed} files failed[/red]")
        for err in result.errors:
            console.print(f"  [red]{err}[/red]")
    if result.cleaned_dirs > 0:
        console.print(f"[dim]~ {result.cleaned_dirs} empty directories removed[/dim]")


def print_history(console: Console, entries: list[HistoryEntry]) -> None:
    if not entries:
        console.print("[dim]No history found.[/dim]")
        return

    table = Table(title="History")
    table.add_column("Time", style="cyan")
    table.add_column("Command")
    table.add_column("Status")
    table.add_column("Duration", justify="right")
    table.add_column("Undo", justify="center")

    for e in entries:
        time_str = e.timestamp.strftime("%Y-%m-%d %H:%M")
        status_style = (
            "green" if e.status == "success"
            else "yellow" if e.status == "partial"
            else "red"
        )
        undo_str = "Y" if e.undo_available else "-"
        duration_str = f"{e.duration_ms / 1000:.1f}s" if e.duration_ms > 0 else "-"
        table.add_row(
            time_str,
            e.command,
            f"[{status_style}]{e.status}[/{status_style}]",
            duration_str,
            undo_str,
        )

    console.print(table)


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / (1024 * 1024 * 1024):.1f} GB"
