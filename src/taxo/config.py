from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

CONFIG_DIR = Path.home() / ".taxo"
CONFIG_FILE = CONFIG_DIR / "config.yaml"


class LLMProviderConfig(BaseModel):
    name: str = "deepseek"
    base_url: str = "https://api.deepseek.com/v1"
    api_key: str = ""
    model: str = "deepseek-chat"
    timeout: int = 30
    max_retries: int = 3


class LLMConfig(BaseModel):
    provider: str = "deepseek"
    base_url: str = "https://api.deepseek.com/v1"
    api_key: str = ""
    model: str = "deepseek-chat"
    timeout: int = 60
    max_retries: int = 3
    max_tokens_per_call: int = 16000
    providers: list[LLMProviderConfig] = []


class ClassifyConfig(BaseModel):
    mode: Literal["type", "hybrid", "semantic"] = "hybrid"
    content_analysis: bool = False
    batch_size: int = 30
    categories: list[dict] = []
    max_workers: int = 5


class RuleConfig(BaseModel):
    use_builtin: bool = True
    custom: list[dict] = []


class OrganizeConfig(BaseModel):
    target_dir: str | None = None
    structure: Literal["flat", "date", "custom"] = "flat"
    date_template: str = "{category}/{year}/{month}"
    conflict_strategy: Literal["skip", "rename", "overwrite", "ask"] = "rename"
    rename_template: str = "{name}_{timestamp}{ext}"
    move_workers: int = 4


class ScanConfig(BaseModel):
    exclude: list[str] = [".*", "*.tmp", "*.part", "*.crdownload"]
    exclude_dirs: list[str] = [".git", "node_modules", "__pycache__"]
    max_depth: int | None = None
    min_size: int = 0
    max_size: int | None = None


class WatchConfig(BaseModel):
    debounce_seconds: int = 5
    delay_seconds: int = 30


class CostConfig(BaseModel):
    monthly_budget: float = 5.0
    max_cost_per_call: float = 0.01
    over_budget_action: Literal["warn", "block"] = "warn"


class CacheConfig(BaseModel):
    enabled: bool = True
    ttl_days: int = 30
    max_entries: int = 10000


class TaxoConfig(BaseModel):
    llm: LLMConfig = LLMConfig()
    classify: ClassifyConfig = ClassifyConfig()
    rules: RuleConfig = RuleConfig()
    organize: OrganizeConfig = OrganizeConfig()
    scan: ScanConfig = ScanConfig()
    watch: WatchConfig = WatchConfig()
    cost: CostConfig = CostConfig()
    cache: CacheConfig = CacheConfig()


def get_default_config() -> TaxoConfig:
    return TaxoConfig()


def load_config() -> TaxoConfig:
    config = get_default_config()
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            data = yaml.safe_load(f) or {}
        config = TaxoConfig(**data)
    config = _apply_env_overrides(config)
    return config


def save_config(config: TaxoConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = config.model_dump(mode="json")
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def _apply_env_overrides(config: TaxoConfig) -> TaxoConfig:
    env_api_key = os.environ.get("TAXO_LLM_API_KEY")
    if env_api_key:
        config.llm.api_key = env_api_key
    env_base_url = os.environ.get("TAXO_LLM_BASE_URL")
    if env_base_url:
        config.llm.base_url = env_base_url
    env_model = os.environ.get("TAXO_LLM_MODEL")
    if env_model:
        config.llm.model = env_model
    return config
