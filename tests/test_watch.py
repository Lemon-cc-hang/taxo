import pytest
from click.testing import CliRunner
from pathlib import Path
from unittest.mock import patch, MagicMock

from taxo.cli import cli


class TestWatchHelp:
    def test_watch_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["watch", "--help"])
        assert result.exit_code == 0
        assert "Watch a directory" in result.output

    def test_watch_accepts_daemon_flag(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["watch", "--help"])
        assert "--daemon" in result.output

    def test_watch_accepts_stop_flag(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["watch", "--help"])
        assert "--stop" in result.output

    def test_watch_accepts_status_flag(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["watch", "--help"])
        assert "--status" in result.output


class TestWatchStopCommand:
    def test_stop_calls_stop_daemon(self):
        runner = CliRunner()
        with patch("taxo.cli.stop_daemon") as mock_stop:
            result = runner.invoke(cli, ["watch", "--stop"])
            assert result.exit_code == 0
            mock_stop.assert_called_once()

    def test_stop_does_not_require_path(self):
        runner = CliRunner()
        with patch("taxo.cli.stop_daemon") as mock_stop:
            result = runner.invoke(cli, ["watch", "--stop"])
            assert result.exit_code == 0


class TestWatchStatusCommand:
    def test_status_calls_get_daemon_status(self):
        runner = CliRunner()
        with patch("taxo.cli.get_daemon_status", return_value="not running") as mock_status:
            result = runner.invoke(cli, ["watch", "--status"])
            assert result.exit_code == 0
            mock_status.assert_called_once()
            assert "not running" in result.output

    def test_status_shows_running(self):
        runner = CliRunner()
        with patch("taxo.cli.get_daemon_status", return_value="running (PID 1234)"):
            result = runner.invoke(cli, ["watch", "--status"])
            assert result.exit_code == 0
            assert "running (PID 1234)" in result.output

    def test_status_does_not_require_path(self):
        runner = CliRunner()
        with patch("taxo.cli.get_daemon_status", return_value="not running"):
            result = runner.invoke(cli, ["watch", "--status"])
            assert result.exit_code == 0


class TestWatchRequiresPath:
    def test_no_path_no_flags_fails(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["watch"])
        assert result.exit_code != 0

    def test_no_path_with_daemon_fails(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["watch", "--daemon"])
        assert result.exit_code != 0


class TestWatchForeground:
    def test_foreground_calls_start_watcher(self, tmp_path):
        runner = CliRunner()
        with patch("taxo.cli.start_watcher") as mock_start:
            result = runner.invoke(cli, ["watch", str(tmp_path)])
            assert result.exit_code == 0
            mock_start.assert_called_once()
            call_args = mock_start.call_args
            assert call_args[0][0] == tmp_path
            # debounce and delay should come from default config
            assert call_args[1].get("debounce_seconds") is not None
            assert call_args[1].get("delay_seconds") is not None


class TestWatchDaemon:
    def test_daemon_calls_start_daemon(self, tmp_path):
        runner = CliRunner()
        with patch("taxo.cli.start_daemon") as mock_start:
            result = runner.invoke(cli, ["watch", str(tmp_path), "--daemon"])
            assert result.exit_code == 0
            mock_start.assert_called_once()
            call_args = mock_start.call_args
            assert call_args[0][0] == tmp_path


class TestOrganizeCallback:
    def test_callback_classifies_and_executes(self, tmp_path):
        from taxo.cli import _organize_callback

        # Create a dummy file so scan_files returns something
        (tmp_path / "test.pdf").write_text("pdf")

        with patch("taxo.cli._get_config") as mock_cfg, \
             patch("taxo.cli.scan_files") as mock_scan, \
             patch("taxo.cli.Classifier") as mock_cls, \
             patch("taxo.cli.Planner") as mock_plan, \
             patch("taxo.cli._get_history_manager") as mock_hm, \
             patch("taxo.cli.Executor") as mock_exec:

            from taxo.config import TaxoConfig
            mock_cfg.return_value = TaxoConfig()

            from taxo.models import FileItem
            from datetime import datetime
            file_item = FileItem(
                path=tmp_path / "test.pdf",
                name="test",
                ext=".pdf",
                size=100,
                mtime=datetime(2026, 5, 1),
                ctime=datetime(2026, 5, 1),
                is_hidden=False,
                is_symlink=False,
            )
            mock_scan.return_value = [file_item]

            mock_classifier = MagicMock()
            mock_cls.return_value = mock_classifier

            from taxo.models import ClassifyResult
            mock_classifier.classify.return_value = [
                ClassifyResult(file=file_item, category="文档", method="rule", confidence=1.0, duration_ms=10, reason="extension match")
            ]

            mock_planner = MagicMock()
            mock_plan.return_value = mock_planner

            from taxo.models import Plan, PlanStats
            mock_planner.create_plan.return_value = Plan(
                id="test-plan",
                source_dir=tmp_path,
                operations=[],
                stats=PlanStats(
                    total_files=1,
                    total_size=100,
                    by_category={"文档": 1},
                    api_calls=0,
                    estimated_cost=0.0,
                    duration_ms=10,
                ),
            )

            mock_executor = MagicMock()
            mock_exec.return_value = mock_executor

            from taxo.executor import ExecuteResult
            mock_executor.execute.return_value = ExecuteResult(plan_id="test-plan", total=0)

            _organize_callback(tmp_path)

            mock_scan.assert_called_once()
            mock_classifier.classify.assert_called_once()
            mock_planner.create_plan.assert_called_once()
            mock_executor.execute.assert_called_once_with(
                mock_planner.create_plan.return_value, dry_run=False
            )

    def test_callback_returns_early_on_empty(self, tmp_path):
        from taxo.cli import _organize_callback

        with patch("taxo.cli._get_config") as mock_cfg, \
             patch("taxo.cli.scan_files") as mock_scan, \
             patch("taxo.cli.Classifier") as mock_cls:

            from taxo.config import TaxoConfig
            mock_cfg.return_value = TaxoConfig()
            mock_scan.return_value = []

            _organize_callback(tmp_path)

            mock_cls.assert_not_called()
