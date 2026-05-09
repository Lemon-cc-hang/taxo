import pytest
from datetime import datetime
from pathlib import Path

from taxo.models import (
    ClassifyResult,
    FileItem,
    HistoryEntry,
    LLMUsage,
    MoveOperation,
    Plan,
    PlanStats,
)


class TestFileItem:
    def test_create_file_item(self, sample_file_item):
        assert sample_file_item.name == "test"
        assert sample_file_item.ext == ".pdf"
        assert sample_file_item.size == 1024
        assert sample_file_item.is_hidden is False
        assert sample_file_item.is_symlink is False

    def test_file_item_path_is_path(self, sample_file_item):
        assert isinstance(sample_file_item.path, Path)

    def test_file_item_requires_path(self):
        with pytest.raises(Exception):
            FileItem(
                name="test",
                ext=".pdf",
                size=100,
                mtime=datetime.now(),
                ctime=datetime.now(),
            )

    def test_hidden_file(self, hidden_file_item):
        assert hidden_file_item.is_hidden is True
        assert hidden_file_item.ext == ""

    def test_file_item_json_roundtrip(self, sample_file_item):
        json_str = sample_file_item.model_dump_json()
        restored = FileItem.model_validate_json(json_str)
        assert restored == sample_file_item


class TestClassifyResult:
    def test_rule_classify_result(self, sample_file_item):
        result = ClassifyResult(
            file=sample_file_item,
            category="文档",
            subcategory=None,
            confidence=1.0,
            method="rule",
            reason="扩展名匹配: .pdf",
        )
        assert result.method == "rule"
        assert result.confidence == 1.0
        assert result.subcategory is None

    def test_llm_classify_result(self, sample_file_item):
        result = ClassifyResult(
            file=sample_file_item,
            category="财务",
            subcategory="报告",
            confidence=0.85,
            method="llm",
            reason="文件名包含'财务报告'",
        )
        assert result.method == "llm"
        assert result.confidence == 0.85

    def test_invalid_method_rejected(self, sample_file_item):
        with pytest.raises(Exception):
            ClassifyResult(
                file=sample_file_item,
                category="文档",
                subcategory=None,
                confidence=1.0,
                method="invalid",
                reason="test",
            )


class TestMoveOperation:
    def test_default_status_is_pending(self):
        op = MoveOperation(
            source=Path("/tmp/a.pdf"),
            target=Path("/tmp/文档/a.pdf"),
            action="move",
            reason="分类结果",
        )
        assert op.status == "pending"

    def test_skip_operation(self):
        op = MoveOperation(
            source=Path("/tmp/a.pdf"),
            target=Path("/tmp/文档/a.pdf"),
            action="skip",
            reason="目标已存在",
        )
        assert op.action == "skip"


class TestPlan:
    def test_create_plan(self, sample_file_item):
        op = MoveOperation(
            source=sample_file_item.path,
            target=Path("/tmp/文档/test.pdf"),
            action="move",
            reason="分类: 文档",
        )
        stats = PlanStats(
            total_files=1,
            total_size=1024,
            by_category={"文档": 1},
            api_calls=0,
            estimated_cost=0.0,
            duration_ms=100,
        )
        plan = Plan(
            id="test-uuid",
            timestamp=datetime(2026, 5, 1, 12, 0, 0),
            source_dir=Path("/tmp"),
            operations=[op],
            stats=stats,
        )
        assert len(plan.operations) == 1
        assert plan.llm_usage is None

    def test_plan_with_llm_usage(self, sample_file_item):
        op = MoveOperation(
            source=sample_file_item.path,
            target=Path("/tmp/财务/test.pdf"),
            action="move",
            reason="分类: 财务",
        )
        stats = PlanStats(
            total_files=1,
            total_size=1024,
            by_category={"财务": 1},
            api_calls=1,
            estimated_cost=0.003,
            duration_ms=2500,
        )
        usage = LLMUsage(
            provider="deepseek",
            model="deepseek-chat",
            input_tokens=500,
            output_tokens=200,
            cost=0.003,
        )
        plan = Plan(
            id="test-uuid-2",
            timestamp=datetime(2026, 5, 1, 12, 0, 0),
            source_dir=Path("/tmp"),
            operations=[op],
            stats=stats,
            llm_usage=usage,
        )
        assert plan.llm_usage.cost == 0.003


class TestHistoryEntry:
    def test_create_history_entry(self):
        entry = HistoryEntry(
            id="hist-uuid",
            timestamp=datetime(2026, 5, 1, 12, 0, 0),
            command="taxo organize ~/Downloads",
            plan_id="test-uuid",
            status="success",
            operations=[],
        )
        assert entry.undo_available is True
        assert entry.undo_timestamp is None

    def test_partial_status(self):
        entry = HistoryEntry(
            id="hist-uuid-2",
            timestamp=datetime(2026, 5, 1, 12, 0, 0),
            command="taxo organize ~/Downloads",
            plan_id="test-uuid",
            status="partial",
            operations=[],
        )
        assert entry.status == "partial"
