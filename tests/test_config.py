import os
import pytest
from pathlib import Path
from unittest.mock import patch

from taxo.config import (
    TaxoConfig,
    LLMConfig,
    ClassifyConfig,
    RuleConfig,
    OrganizeConfig,
    ScanConfig,
    WatchConfig,
    CostConfig,
    get_default_config,
    load_config,
    save_config,
)


class TestDefaultConfig:
    def test_default_config_has_all_sections(self):
        config = get_default_config()
        assert isinstance(config.llm, LLMConfig)
        assert isinstance(config.classify, ClassifyConfig)
        assert isinstance(config.rules, RuleConfig)
        assert isinstance(config.organize, OrganizeConfig)
        assert isinstance(config.scan, ScanConfig)
        assert isinstance(config.watch, WatchConfig)
        assert isinstance(config.cost, CostConfig)

    def test_default_llm_config(self):
        config = get_default_config()
        assert config.llm.base_url == "https://api.deepseek.com/v1"
        assert config.llm.model == "deepseek-chat"
        assert config.llm.timeout == 60
        assert config.llm.max_retries == 3
        assert config.llm.api_key == ""

    def test_default_classify_config(self):
        config = get_default_config()
        assert config.classify.mode == "hybrid"
        assert config.classify.content_analysis is False
        assert config.classify.batch_size == 30

    def test_default_organize_config(self):
        config = get_default_config()
        assert config.organize.target_dir is None
        assert config.organize.structure == "flat"
        assert config.organize.conflict_strategy == "rename"

    def test_default_scan_config(self):
        config = get_default_config()
        assert ".*" in config.scan.exclude
        assert ".git" in config.scan.exclude_dirs
        assert config.scan.max_depth is None


class TestLoadSaveConfig:
    def test_load_returns_default_when_no_file(self, tmp_path):
        config_dir = tmp_path / ".taxo"
        with patch("taxo.config.CONFIG_DIR", config_dir), \
             patch("taxo.config.CONFIG_FILE", config_dir / "config.yaml"):
            config = load_config()
            assert config.llm.model == get_default_config().llm.model

    def test_save_and_load_roundtrip(self, tmp_path):
        config_dir = tmp_path / ".taxo"
        config_dir.mkdir()
        with patch("taxo.config.CONFIG_DIR", config_dir):
            with patch("taxo.config.CONFIG_FILE", config_dir / "config.yaml"):
                config = get_default_config()
                config.llm.api_key = "sk-test-key"
                config.classify.mode = "semantic"
                save_config(config)

                loaded = load_config()
                assert loaded.llm.api_key == "sk-test-key"
                assert loaded.classify.mode == "semantic"

    def test_load_partial_config_merges_with_defaults(self, tmp_path):
        config_dir = tmp_path / ".taxo"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text("llm:\n  model: glm-4\n")
        with patch("taxo.config.CONFIG_DIR", config_dir):
            with patch("taxo.config.CONFIG_FILE", config_file):
                config = load_config()
                assert config.llm.model == "glm-4"
                assert config.llm.timeout == 60
                assert config.classify.mode == "hybrid"


class TestEnvOverride:
    def test_api_key_from_env(self, tmp_path):
        config_dir = tmp_path / ".taxo"
        with patch("taxo.config.CONFIG_DIR", config_dir):
            with patch.dict(os.environ, {"TAXO_LLM_API_KEY": "sk-env-key"}):
                config = load_config()
                assert config.llm.api_key == "sk-env-key"

    def test_base_url_from_env(self, tmp_path):
        config_dir = tmp_path / ".taxo"
        with patch("taxo.config.CONFIG_DIR", config_dir):
            with patch.dict(os.environ, {"TAXO_LLM_BASE_URL": "https://api.openai.com/v1"}):
                config = load_config()
                assert config.llm.base_url == "https://api.openai.com/v1"

    def test_env_overrides_file(self, tmp_path):
        config_dir = tmp_path / ".taxo"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text("llm:\n  api_key: sk-file-key\n")
        with patch("taxo.config.CONFIG_DIR", config_dir):
            with patch("taxo.config.CONFIG_FILE", config_file):
                with patch.dict(os.environ, {"TAXO_LLM_API_KEY": "sk-env-key"}):
                    config = load_config()
                    assert config.llm.api_key == "sk-env-key"
