from __future__ import annotations

import time
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TaskProgressColumn

from taxo import __version__
from taxo.cache import CacheManager
from taxo.classifier import Classifier
from taxo.config import TaxoConfig, load_config, save_config, CONFIG_DIR, CONFIG_FILE, get_default_config
from taxo.display import print_execute_result, print_history, print_plan_preview, print_scan_table
from taxo.executor import Executor
from taxo.history import HistoryManager
from taxo.planner import Planner
from taxo.rules import BUILTIN_RULES
from taxo.scanner import scan_files
from taxo.watcher import start_watcher, start_daemon, stop_daemon, get_daemon_status

import logging

console = Console()
logger = logging.getLogger(__name__)


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
@click.option("--mode", type=click.Choice(["type", "hybrid", "semantic"]), default=None, help="Classification mode")
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

    # Build progress callbacks only when output is a terminal
    scan_callback = None
    classify_callback = None
    progress_ctx = None

    if console.is_terminal:
        progress_ctx = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        )

    if progress_ctx:
        with progress_ctx as progress:
            scan_task = progress.add_task("Scanning files...", total=None)

            def on_scan(count: int) -> None:
                progress.update(scan_task, completed=count)

            files = scan_files(directory, config.scan, progress_callback=on_scan)
            progress.update(scan_task, total=len(files), completed=len(files))

            if not files:
                console.print("[dim]No files found.[/dim]")
                return

            classifier = Classifier(config, _get_cache_manager(config))
            classify_task = progress.add_task("Classifying...", total=None)

            def on_classify(done: int, total: int) -> None:
                progress.update(classify_task, total=total, completed=done)

            start = time.monotonic()
            results = classifier.classify(files, source_dir=directory, progress_callback=on_classify)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            progress.update(classify_task, total=len(results), completed=len(results))
    else:
        files = scan_files(directory, config.scan)
        if not files:
            console.print("[dim]No files found.[/dim]")
            return
        classifier = Classifier(config, _get_cache_manager(config))
        start = time.monotonic()
        results = classifier.classify(files, source_dir=directory)
        elapsed_ms = int((time.monotonic() - start) * 1000)

    if output_fmt == "json":
        import json
        data = []
        for r in results:
            data.append({
                "file": r.file.name + r.file.ext,
                "category": r.category,
                "method": r.method,
                "confidence": r.confidence,
                "duration_ms": r.duration_ms,
            })
        console.print_json(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print_scan_table(console, results, total_ms=elapsed_ms)


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--mode", type=click.Choice(["type", "hybrid", "semantic"]), default=None)
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

    scan_callback = None
    classify_callback = None
    progress_ctx = None

    if console.is_terminal:
        progress_ctx = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        )

    if progress_ctx:
        with progress_ctx as progress:
            scan_task = progress.add_task("Scanning files...", total=None)

            def on_scan(count: int) -> None:
                progress.update(scan_task, completed=count)

            files = scan_files(directory, config.scan, progress_callback=on_scan)
            progress.update(scan_task, total=len(files), completed=len(files))

            if not files:
                console.print("[dim]No files found.[/dim]")
                return

            classifier = Classifier(config, _get_cache_manager(config))
            classify_task = progress.add_task("Classifying...", total=None)

            def on_classify(done: int, total: int) -> None:
                progress.update(classify_task, total=total, completed=done)

            start = time.monotonic()
            results = classifier.classify(files, source_dir=directory, progress_callback=on_classify)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            progress.update(classify_task, total=len(results), completed=len(results))
    else:
        files = scan_files(directory, config.scan)
        if not files:
            console.print("[dim]No files found.[/dim]")
            return
        classifier = Classifier(config, _get_cache_manager(config))
        start = time.monotonic()
        results = classifier.classify(files, source_dir=directory)
        elapsed_ms = int((time.monotonic() - start) * 1000)

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


def _organize_callback(directory: Path) -> None:
    """Callback for watcher: classify and organize files in a directory."""
    config = _get_config()
    files = scan_files(directory, config.scan)
    if not files:
        return
    classifier = Classifier(config, _get_cache_manager(config))
    results = classifier.classify(files, source_dir=directory)
    planner = Planner(config.organize)
    plan = planner.create_plan(results, directory)
    hm = _get_history_manager(config)
    executor = Executor(hm, move_workers=config.organize.move_workers)
    result = executor.execute(plan, dry_run=False)
    logger.info(f"Auto-organized: {result.success} files moved, {result.failed} failed")


@cli.command()
@click.argument("path", required=False, type=click.Path(exists=True))
@click.option("--daemon", is_flag=True, help="Run as background daemon")
@click.option("--stop", "stop_flag", is_flag=True, help="Stop the running daemon")
@click.option("--status", "status_flag", is_flag=True, help="Check daemon status")
def watch(path: str | None, daemon: bool, stop_flag: bool, status_flag: bool) -> None:
    """Watch a directory for new files and auto-organize them."""
    if stop_flag:
        stop_daemon()
        return

    if status_flag:
        status = get_daemon_status()
        console.print(f"Watcher status: {status}")
        return

    if path is None:
        console.print("[red]Error: PATH is required unless using --stop or --status.[/red]")
        raise SystemExit(1)

    directory = Path(path)
    config = _get_config()
    debounce = config.watch.debounce_seconds
    delay = config.watch.delay_seconds

    if daemon:
        start_daemon(directory, _organize_callback, debounce_seconds=debounce, delay_seconds=delay)
    else:
        console.print(f"[bold]Watching {directory} for new files...[/bold] (Ctrl+C to stop)")
        start_watcher(directory, _organize_callback, debounce_seconds=debounce, delay_seconds=delay)


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
    save_config(get_default_config())
    console.print("[green]Configuration reset to defaults.[/green]")


@config.command("init")
def config_init() -> None:
    """Interactive configuration wizard."""
    console.print("[bold]Taxo Configuration Wizard[/bold]\n")

    if CONFIG_FILE.exists():
        if not click.confirm("Config file exists. Overwrite?", default=False):
            console.print("[dim]Cancelled.[/dim]")
            return

    defaults = get_default_config()

    api_key = click.prompt("API Key (press Enter to skip)", default="", hide_input=True, show_default=False)
    base_url = click.prompt("API Base URL", default=defaults.llm.base_url)
    model = click.prompt("Model", default=defaults.llm.model)
    mode = click.prompt("Classification mode (type/hybrid/semantic)", default=defaults.classify.mode)
    structure = click.prompt("Directory structure (flat/date)", default=defaults.organize.structure)

    cfg = get_default_config()
    cfg.llm.api_key = api_key
    cfg.llm.base_url = base_url
    cfg.llm.model = model
    cfg.classify.mode = mode
    cfg.organize.structure = structure

    save_config(cfg)
    console.print(f"\n[green]Configuration saved to {CONFIG_FILE}[/green]")


@config.command("edit")
def config_edit() -> None:
    """Open configuration file in editor."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        save_config(get_default_config())

    click.edit(filename=str(CONFIG_FILE))


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


@cli.command("cost")
def cost_cmd() -> None:
    """Show monthly LLM API cost statistics."""
    from taxo.cost import CostTracker

    config = _get_config()
    tracker = CostTracker(config.cost)
    stats = tracker.get_stats()

    console.print("[bold]Monthly Cost Report[/bold]\n")
    console.print(f"  Month spend:       ${stats['monthly_spend']:.6f}")
    console.print(f"  Monthly budget:    ${stats['monthly_budget']:.2f}")
    console.print(f"  Budget remaining:  ${stats['budget_remaining']:.6f}")
    console.print(f"  Total API calls:   {stats['total_calls']}")
    console.print(f"  Input tokens:      {stats['total_input_tokens']:,}")
    console.print(f"  Output tokens:     {stats['total_output_tokens']:,}")
    console.print(f"  Max cost/call:     ${stats['max_cost_per_call']:.6f}")
    console.print(f"  Over-budget action: {stats['over_budget_action']}")


@cli.group()
def cache() -> None:
    """Manage classification cache."""
    pass


@cache.command("stats")
def cache_stats() -> None:
    """Show cache statistics."""
    from taxo.config import CONFIG_DIR
    cache_dir = CONFIG_DIR / "cache"
    if not cache_dir.exists():
        console.print("[dim]No cache data.[/dim]")
        return
    files = list(cache_dir.glob("scan_*.json"))
    total = 0
    for f in files:
        import json
        data = json.loads(f.read_text())
        total += len(data)
    console.print(f"Cache files: {len(files)}")
    console.print(f"Cached entries: {total}")


@cache.command("clear")
@click.option("--dir", "dir_path", type=click.Path(), default=None, help="Clear cache for specific directory")
def cache_clear(dir_path: str | None) -> None:
    """Clear classification cache."""
    from taxo.config import CONFIG_DIR
    cm = CacheManager(cache_dir=CONFIG_DIR / "cache")
    path = Path(dir_path) if dir_path else None
    count = cm.clear(path)
    if count:
        target = f" for {dir_path}" if dir_path else ""
        console.print(f"[green]Cleared {count} cache file(s){target}.[/green]")
    else:
        console.print("[dim]No cache to clear.[/dim]")


if __name__ == "__main__":
    cli()
