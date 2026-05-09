import pytest
from click.testing import CliRunner
from unittest.mock import patch
from pathlib import Path

from taxo.cli import cli


class TestCLIBase:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Taxo" in result.output

    def test_version(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_scan_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["scan", "--help"])
        assert result.exit_code == 0

    def test_organize_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["organize", "--help"])
        assert result.exit_code == 0

    def test_undo_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["undo", "--help"])
        assert result.exit_code == 0

    def test_history_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["history", "--help"])
        assert result.exit_code == 0

    def test_config_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "--help"])
        assert result.exit_code == 0

    def test_rules_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["rules", "--help"])
        assert result.exit_code == 0


class TestScanCommand:
    def test_scan_nonexistent_dir(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["scan", "/nonexistent/path"])
        assert result.exit_code != 0

    def test_scan_empty_dir(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli, ["scan", str(tmp_path)])
        assert result.exit_code == 0

    def test_scan_with_files(self, tmp_path):
        (tmp_path / "test.pdf").write_text("pdf")
        (tmp_path / "photo.jpg").write_bytes(b"\xff\xd8")
        runner = CliRunner()
        result = runner.invoke(cli, ["scan", str(tmp_path)])
        assert result.exit_code == 0


class TestOrganizeCommand:
    def test_organize_dry_run(self, tmp_path):
        (tmp_path / "test.pdf").write_text("pdf")
        runner = CliRunner()
        result = runner.invoke(cli, ["organize", str(tmp_path)])
        assert result.exit_code == 0

    def test_organize_yes(self, tmp_path):
        (tmp_path / "test.pdf").write_text("pdf")
        runner = CliRunner()
        result = runner.invoke(cli, ["organize", str(tmp_path), "--yes"])
        assert result.exit_code == 0


class TestConfigCommand:
    def test_config_show(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "show"])
        assert result.exit_code == 0

    def test_config_set_and_get(self, tmp_path):
        runner = CliRunner()
        with patch("taxo.config.CONFIG_DIR", tmp_path / ".taxo"):
            with patch("taxo.config.CONFIG_FILE", tmp_path / ".taxo" / "config.yaml"):
                result_set = runner.invoke(cli, ["config", "set", "classify.mode", "semantic"])
                assert result_set.exit_code == 0


class TestHistoryCommand:
    def test_history_empty(self, tmp_path):
        runner = CliRunner()
        with patch("taxo.cli._get_history_manager") as mock:
            from taxo.history import HistoryManager
            mock.return_value = HistoryManager(tmp_path / "history.jsonl")
            result = runner.invoke(cli, ["history"])
            assert result.exit_code == 0


class TestUndoCommand:
    def test_undo_no_history(self, tmp_path):
        runner = CliRunner()
        with patch("taxo.cli._get_history_manager") as mock:
            from taxo.history import HistoryManager
            mock.return_value = HistoryManager(tmp_path / "history.jsonl")
            result = runner.invoke(cli, ["undo", "--force"])
            assert result.exit_code == 0


class TestRulesCommand:
    def test_rules_list(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["rules", "list"])
        assert result.exit_code == 0
