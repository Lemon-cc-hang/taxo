from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

from taxo import __version__
from taxo.cache import CacheManager
from taxo.classifier import Classifier
from taxo.config import TaxoConfig, load_config, save_config, CONFIG_DIR
from taxo.display import print_execute_result, print_history, print_plan_preview, print_scan_table
from taxo.executor import Executor
from taxo.history import HistoryManager
from taxo.planner import Planner
from taxo.rules import BUILTIN_RULES
from taxo.scanner import scan_files

console = Console()


def _get_config() -> TaxoConfig:
    return load_config()


def _get_cache_manager(config: TaxoConfig) -> CacheManager | None:
    if not config.cache.enabled:
        return None
    return CacheManager(
        cache_dir=CONFIG_DIR / "cache",
        ttl_days=config.cache.ttl_days,
        max_entries=config.cache.max_entries,
    )


def _get_history_manager(config: TaxoConfig | None = None) -> HistoryManager:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return HistoryManager(CONFIG_DIR / "history.jsonl")


@click.group()
@click.version_option(version=__version__, prog_name="Taxo")
def cli() -> None:
    """Taxo - AI-powered file classifier."""
    pass


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--mode", type=click.Choice(["type", "semantic", "project", "hybrid"]), default=None, help="Classification mode")
@click.option("--output", "output_fmt", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.option("--max-depth", type=int, default=None, help="Max scan depth")
def scan(path: str, mode: str | None, output_fmt: str, max_depth: int | None) -> None:
    """Scan and preview file classification."""
    config = _get_config()
    if mode:
        config.classify.mode = mode
    if max_depth is not None:
        config.scan.max_depth = max_depth

    directory = Path(path)
    files = scan_files(directory, config.scan)
    if not files:
        console.print("[dim]No files found.[/dim]")
        return

    classifier = Classifier(config, _get_cache_manager(config))
    results = classifier.classify(files, source_dir=directory)

    if output_fmt == "json":
        import json
        data = []
        for r in results:
            data.append({
                "file": r.file.name + r.file.ext,
                "category": r.category,
                "method": r.method,
                "confidence": r.confidence,
            })
        console.print_json(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print_scan_table(console, results)


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--mode", type=click.Choice(["type", "semantic", "project", "hybrid"]), default=None)
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.option("--dry-run", is_flag=True, default=True, help="Preview only")
@click.option("--target", type=click.Path(), default=None, help="Target directory")
@click.option("--conflict-strategy", type=click.Choice(["skip", "rename", "overwrite", "ask"]), default=None)
def organize(path: str, mode: str | None, yes: bool, dry_run: bool, target: str | None, conflict_strategy: str | None) -> None:
    """Organize files by classification."""
    config = _get_config()
    if mode:
        config.classify.mode = mode
    if target:
        config.organize.target_dir = target
    if conflict_strategy:
        config.organize.conflict_strategy = conflict_strategy

    directory = Path(path)
    files = scan_files(directory, config.scan)
    if not files:
        console.print("[dim]No files found.[/dim]")
        return

    classifier = Classifier(config, _get_cache_manager(config))
    results = classifier.classify(files, source_dir=directory)

    planner = Planner(config.organize)
    plan = planner.create_plan(results, directory)

    print_plan_preview(console, plan)

    if yes:
        dry_run = False
    elif dry_run:
        console.print("\n[dim]Dry run - no files moved. Use --yes to execute.[/dim]")
        return
    else:
        if not click.confirm("\nExecute?", default=False):
            console.print("[dim]Cancelled.[/dim]")
            return

    hm = _get_history_manager(config)
    executor = Executor(hm, move_workers=config.organize.move_workers)
    result = executor.execute(plan, dry_run=dry_run)
    print_execute_result(console, result)


@cli.command()
@click.option("--step", type=int, default=1, help="Undo step N from last")
@click.option("--id", "entry_id", type=str, default=None, help="Undo specific entry by ID")
@click.option("--force", is_flag=True, help="Skip confirmation")
def undo(step: int, entry_id: str | None, force: bool) -> None:
    """Undo last organize operation."""
    hm = _get_history_manager()
    executor = Executor(hm)

    if not force:
        last = hm.get_last()
        if not last:
            console.print("[dim]No history to undo.[/dim]")
            return
        if not click.confirm(f"Undo '{last.command}'?", default=False):
            console.print("[dim]Cancelled.[/dim]")
            return

    result = executor.undo(step=step)
    if result.total == 0:
        console.print("[dim]Nothing to undo.[/dim]")
    else:
        print_execute_result(console, result)


@cli.command("history")
@click.option("--last", "show_last", is_flag=True, help="Show last entry only")
@click.option("--since", type=str, default=None, help="Show entries since date (YYYY-MM-DD)")
def history_cmd(show_last: bool, since: str | None) -> None:
    """View operation history."""
    hm = _get_history_manager()

    if show_last:
        entry = hm.get_last()
        if entry:
            print_history(console, [entry])
        else:
            console.print("[dim]No history found.[/dim]")
        return

    since_dt = None
    if since:
        from datetime import datetime
        since_dt = datetime.strptime(since, "%Y-%m-%d")

    entries = hm.list_entries(limit=20, since=since_dt)
    print_history(console, entries)


@cli.group()
def config() -> None:
    """Manage configuration."""
    pass


@config.command("show")
def config_show() -> None:
    """Show current configuration."""
    cfg = _get_config()
    data = cfg.model_dump(mode="json")
    if data.get("llm", {}).get("api_key"):
        key = data["llm"]["api_key"]
        data["llm"]["api_key"] = key[:6] + "***" + key[-4:] if len(key) > 10 else "***"
    import yaml
    console.print(yaml.dump(data, default_flow_style=False, allow_unicode=True))


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """Set a configuration value (dot notation, e.g. llm.model)."""
    cfg = _get_config()
    parts = key.split(".")
    obj = cfg
    for part in parts[:-1]:
        obj = getattr(obj, part)

    attr = parts[-1]
    current = getattr(obj, attr)
    if isinstance(current, bool):
        setattr(obj, attr, value.lower() in ("true", "1", "yes"))
    elif isinstance(current, int):
        setattr(obj, attr, int(value))
    elif isinstance(current, float):
        setattr(obj, attr, float(value))
    else:
        setattr(obj, attr, value)

    save_config(cfg)
    console.print(f"[green]Set {key} = {value}[/green]")


@config.command("get")
@click.argument("key")
def config_get(key: str) -> None:
    """Get a configuration value (dot notation)."""
    cfg = _get_config()
    parts = key.split(".")
    obj = cfg
    for part in parts:
        obj = getattr(obj, part)
    console.print(str(obj))


@config.command("reset")
def config_reset() -> None:
    """Reset configuration to defaults."""
    from taxo.config import get_default_config
    save_config(get_default_config())
    console.print("[green]Configuration reset to defaults.[/green]")


@cli.group()
def rules() -> None:
    """Manage classification rules."""
    pass


@rules.command("list")
def rules_list() -> None:
    """List all rules."""
    console.print("[bold]Builtin rules:[/bold]\n")
    for category, exts in BUILTIN_RULES.items():
        ext_str = ", ".join(exts)
        console.print(f"  [cyan]{category}[/cyan]: {ext_str}")

    cfg = _get_config()
    if cfg.rules.custom:
        console.print("\n[bold]Custom rules:[/bold]\n")
        for i, rule in enumerate(cfg.rules.custom):
            console.print(f"  {i + 1}. [yellow]{rule['pattern']}[/yellow] -> {rule['category']}")


@rules.command("add")
@click.argument("pattern")
@click.argument("category")
def rules_add(pattern: str, category: str) -> None:
    """Add a custom rule. E.g.: taxo rules add "ext:.epub" "电子书" """
    cfg = _get_config()
    cfg.rules.custom.append({"pattern": pattern, "category": category})
    save_config(cfg)
    console.print(f"[green]Added rule: {pattern} -> {category}[/green]")


@rules.command("remove")
@click.argument("index", type=int)
def rules_remove(index: int) -> None:
    """Remove a custom rule by index (1-based)."""
    cfg = _get_config()
    if 1 <= index <= len(cfg.rules.custom):
        removed = cfg.rules.custom.pop(index - 1)
        save_config(cfg)
        console.print(f"[green]Removed rule: {removed['pattern']} -> {removed['category']}[/green]")
    else:
        console.print(f"[red]Invalid index: {index}. Use 'taxo rules list' to see available rules.[/red]")


if __name__ == "__main__":
    cli()
