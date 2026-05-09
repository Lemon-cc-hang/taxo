from __future__ import annotations

import logging
import os
import signal
import sys
import time
from pathlib import Path
from threading import Timer

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)


class FileEventHandler(FileSystemEventHandler):
    def __init__(self, callback, debounce_seconds: int = 5, delay_seconds: int = 30) -> None:
        self._callback = callback
        self._debounce_seconds = debounce_seconds
        self._delay_seconds = delay_seconds
        self._pending: dict[str, Timer] = {}

    def on_created(self, event) -> None:
        if event.is_directory:
            return
        path = event.src_path
        if path in self._pending:
            self._pending[path].cancel()

        timer = Timer(self._delay_seconds, self._process_file, args=[path])
        self._pending[path] = timer
        timer.start()

    def _process_file(self, path: str) -> None:
        self._pending.pop(path, None)
        p = Path(path)
        if p.exists() and p.is_file():
            logger.info(f"Processing new file: {path}")
            try:
                self._callback(p.parent)
            except Exception as e:
                logger.error(f"Error processing {path}: {e}")


def start_watcher(
    directory: Path,
    callback,
    debounce_seconds: int = 5,
    delay_seconds: int = 30,
) -> None:
    handler = FileEventHandler(callback, debounce_seconds, delay_seconds)
    observer = Observer()
    observer.schedule(handler, str(directory), recursive=False)
    observer.start()
    logger.info(f"Watching {directory} for new files...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


def get_pid_file() -> Path:
    from taxo.config import CONFIG_DIR
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR / "watch.pid"


def start_daemon(directory: Path, callback, **kwargs) -> None:
    pid_file = get_pid_file()
    if pid_file.exists():
        pid = int(pid_file.read_text().strip())
        try:
            os.kill(pid, 0)
            print(f"Watcher already running (PID {pid})")
            return
        except ProcessLookupError:
            pid_file.unlink()

    pid = os.fork()
    if pid > 0:
        pid_file.write_text(str(pid))
        print(f"Watcher started (PID {pid})")
        return

    sys.stdin.close()
    start_watcher(directory, callback, **kwargs)


def stop_daemon() -> None:
    pid_file = get_pid_file()
    if not pid_file.exists():
        print("No watcher running")
        return

    pid = int(pid_file.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        pid_file.unlink()
        print(f"Watcher stopped (PID {pid})")
    except ProcessLookupError:
        pid_file.unlink()
        print("Watcher process not found, cleaned up PID file")


def get_daemon_status() -> str:
    pid_file = get_pid_file()
    if not pid_file.exists():
        return "not running"

    pid = int(pid_file.read_text().strip())
    try:
        os.kill(pid, 0)
        return f"running (PID {pid})"
    except ProcessLookupError:
        return "not running (stale PID file)"
