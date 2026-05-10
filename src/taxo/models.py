from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class FileItem(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    path: Path
    name: str
    ext: str
    size: int
    mtime: datetime
    ctime: datetime
    is_hidden: bool
    is_symlink: bool


class ClassifyResult(BaseModel):
    file: FileItem
    category: str
    subcategory: str | None = None
    confidence: float
    method: Literal["rule", "llm"]
    reason: str
    duration_ms: int = 0


class MoveOperation(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    source: Path
    target: Path
    action: Literal["move", "rename", "skip"]
    reason: str
    status: Literal["pending", "success", "failed", "skipped"] = "pending"


class PlanStats(BaseModel):
    total_files: int
    total_size: int
    by_category: dict[str, int]
    api_calls: int
    estimated_cost: float
    duration_ms: int


class LLMUsage(BaseModel):
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost: float


class Plan(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=datetime.now)
    source_dir: Path
    operations: list[MoveOperation]
    stats: PlanStats
    llm_usage: LLMUsage | None = None


class HistoryEntry(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=datetime.now)
    command: str
    plan_id: str
    status: Literal["success", "partial", "failed"]
    operations: list[MoveOperation]
    undo_available: bool = True
    undo_timestamp: datetime | None = None
    duration_ms: int = 0
