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
        assert "0.3.0" in result.output

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

    def test_config_init_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "init", "--help"])
        assert result.exit_code == 0
        assert "wizard" in result.output.lower() or "init" in result.output.lower()

    def test_config_edit_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "edit", "--help"])
        assert result.exit_code == 0
        assert "editor" in result.output.lower()


class TestConfigInitCommand:
    def test_config_init_saves(self, tmp_path):
        config_dir = tmp_path / ".taxo"
        config_file = config_dir / "config.yaml"
        runner = CliRunner()
        with patch("taxo.config.CONFIG_DIR", config_dir), \
             patch("taxo.config.CONFIG_FILE", config_file), \
             patch("taxo.cli.CONFIG_DIR", config_dir), \
             patch("taxo.cli.CONFIG_FILE", config_file):
            result = runner.invoke(cli, ["config", "init"], input="\n\n\n\n\n")
            assert result.exit_code == 0
            assert config_file.exists()
            import yaml
            data = yaml.safe_load(config_file.read_text())
            assert data["llm"]["api_key"] == ""
            assert data["llm"]["base_url"] == "https://api.deepseek.com/v1"
            assert data["llm"]["model"] == "deepseek-chat"
            assert data["classify"]["mode"] == "hybrid"
            assert data["organize"]["structure"] == "flat"

    def test_config_init_with_custom_values(self, tmp_path):
        config_dir = tmp_path / ".taxo"
        config_file = config_dir / "config.yaml"
        runner = CliRunner()
        with patch("taxo.config.CONFIG_DIR", config_dir), \
             patch("taxo.config.CONFIG_FILE", config_file), \
             patch("taxo.cli.CONFIG_DIR", config_dir), \
             patch("taxo.cli.CONFIG_FILE", config_file):
            result = runner.invoke(cli, ["config", "init"], input="\nhttps://custom.api.com\nmy-model\nsemantic\ndate\n")
            assert result.exit_code == 0
            import yaml
            data = yaml.safe_load(config_file.read_text())
            assert data["llm"]["base_url"] == "https://custom.api.com"
            assert data["llm"]["model"] == "my-model"
            assert data["classify"]["mode"] == "semantic"
            assert data["organize"]["structure"] == "date"

    def test_config_init_existing_no_overwrite(self, tmp_path):
        config_dir = tmp_path / ".taxo"
        config_file = config_dir / "config.yaml"
        config_dir.mkdir(parents=True)
        config_file.write_text("existing: true")
        runner = CliRunner()
        with patch("taxo.config.CONFIG_DIR", config_dir), \
             patch("taxo.config.CONFIG_FILE", config_file), \
             patch("taxo.cli.CONFIG_DIR", config_dir), \
             patch("taxo.cli.CONFIG_FILE", config_file):
            result = runner.invoke(cli, ["config", "init"], input="n\n")
            assert result.exit_code == 0
            assert "Cancelled" in result.output
            assert config_file.read_text() == "existing: true"

    def test_config_init_existing_overwrite(self, tmp_path):
        config_dir = tmp_path / ".taxo"
        config_file = config_dir / "config.yaml"
        config_dir.mkdir(parents=True)
        config_file.write_text("existing: true")
        runner = CliRunner()
        with patch("taxo.config.CONFIG_DIR", config_dir), \
             patch("taxo.config.CONFIG_FILE", config_file), \
             patch("taxo.cli.CONFIG_DIR", config_dir), \
             patch("taxo.cli.CONFIG_FILE", config_file):
            result = runner.invoke(cli, ["config", "init"], input="y\n\n\n\n\n\n")
            assert result.exit_code == 0
            assert "saved" in result.output.lower()


class TestConfigEditCommand:
    def test_config_edit_creates_config_if_missing(self, tmp_path):
        config_dir = tmp_path / ".taxo"
        config_file = config_dir / "config.yaml"
        runner = CliRunner()
        with patch("taxo.config.CONFIG_DIR", config_dir), \
             patch("taxo.config.CONFIG_FILE", config_file), \
             patch("taxo.cli.CONFIG_DIR", config_dir), \
             patch("taxo.cli.CONFIG_FILE", config_file), \
             patch("click.edit") as mock_edit:
            result = runner.invoke(cli, ["config", "edit"])
            assert result.exit_code == 0
            assert config_file.exists()
            mock_edit.assert_called_once_with(filename=str(config_file))

    def test_config_edit_opens_editor(self, tmp_path):
        config_dir = tmp_path / ".taxo"
        config_file = config_dir / "config.yaml"
        config_dir.mkdir(parents=True)
        config_file.write_text("llm:\n  model: test\n")
        runner = CliRunner()
        with patch("taxo.config.CONFIG_DIR", config_dir), \
             patch("taxo.config.CONFIG_FILE", config_file), \
             patch("taxo.cli.CONFIG_DIR", config_dir), \
             patch("taxo.cli.CONFIG_FILE", config_file), \
             patch("click.edit") as mock_edit:
            result = runner.invoke(cli, ["config", "edit"])
            assert result.exit_code == 0
            mock_edit.assert_called_once_with(filename=str(config_file))


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
