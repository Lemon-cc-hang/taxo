import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
from pathlib import Path

import httpx

from taxo.config import LLMConfig, CostConfig
from taxo.models import FileItem
from taxo.llm import LLMClient, LLMUnavailableError, BudgetExceededError
from taxo.cost import CostTracker


def make_file(name: str) -> FileItem:
    stem, _, e = name.rpartition(".")
    if not stem:
        stem, e = name, ""
    else:
        e = f".{e}"
    return FileItem(
        path=Path(f"/tmp/{name}"),
        name=stem,
        ext=e.lower(),
        size=1024,
        mtime=datetime(2026, 5, 1, 12, 0, 0),
        ctime=datetime(2026, 5, 1, 12, 0, 0),
        is_hidden=False,
        is_symlink=False,
    )


def _make_response(content: dict, usage: dict | None = None) -> httpx.Response:
    payload = {
        "choices": [{"message": {"content": json.dumps(content)}}],
    }
    if usage is not None:
        payload["usage"] = usage
    return httpx.Response(
        200,
        json=payload,
        request=httpx.Request("POST", "https://api.example.com/v1/chat/completions"),
    )


class TestBuildPrompt:
    def setup_method(self):
        self.config = LLMConfig(api_key="sk-test")
        self.client = LLMClient(self.config)

    def test_system_prompt_contains_categories(self):
        categories = ["财务", "报告", "个人"]
        prompt = self.client._build_system_prompt(categories, "hybrid")
        assert "财务" in prompt
        assert "报告" in prompt
        assert "JSON" in prompt

    def test_semantic_prompt_contains_existing_dirs(self):
        prompt = self.client._build_system_prompt([], "semantic", existing_dirs=["工作文档", "旅行照片"])
        assert "已有子目录" in prompt
        assert "工作文档" in prompt
        assert "旅行照片" in prompt
        assert "临时文件" in prompt

    def test_semantic_prompt_without_existing_dirs(self):
        prompt = self.client._build_system_prompt([], "semantic")
        assert "工作文档" not in prompt
        assert "临时文件" in prompt

    def test_user_prompt_contains_file_info(self):
        files = [make_file("Q4财务报告.pdf"), make_file("photo.jpg")]
        prompt = self.client._build_user_prompt(files)
        assert "Q4财务报告" in prompt
        assert ".pdf" in prompt
        assert ".jpg" in prompt


class TestParseResponse:
    def setup_method(self):
        self.config = LLMConfig(api_key="sk-test")
        self.client = LLMClient(self.config)

    def test_parse_valid_json(self):
        raw = json.dumps({"categories": {"财务文档": ["Q4财务报告.pdf"], "截图": ["Screenshot.png"]}, "uncategorized": []})
        result = self.client._parse_response(raw)
        assert "财务文档" in result
        assert "Q4财务报告.pdf" in result["财务文档"]
        assert "截图" in result

    def test_parse_json_with_markdown_wrapper(self):
        raw = '```json\n{"categories": {"文档": ["a.pdf"]}, "uncategorized": []}\n```'
        result = self.client._parse_response(raw)
        assert "文档" in result
        assert "a.pdf" in result["文档"]

    def test_parse_invalid_json_returns_empty(self):
        result = self.client._parse_response("This is not JSON")
        assert result == {}

    def test_parse_missing_categories_key(self):
        result = self.client._parse_response(json.dumps({"results": {}}))
        assert result == {}


class TestClassifyBatch:
    def test_successful_classification(self):
        config = LLMConfig(api_key="sk-test")
        client = LLMClient(config)
        mock_response = _make_response(
            {"categories": {"文档": ["report.pdf"]}, "uncategorized": []},
            usage={"prompt_tokens": 150, "completion_tokens": 80},
        )
        with patch.object(client._client, "post", return_value=mock_response):
            files = [make_file("report.pdf")]
            result, elapsed = client.classify_batch(files, ["文档", "图片"], "type")
            assert "文档" in result
            assert "report.pdf" in result["文档"]
            assert elapsed >= 0

    def test_connection_error_raises_unavailable(self):
        config = LLMConfig(api_key="sk-test", max_retries=1)
        client = LLMClient(config)
        with patch.object(client._client, "post", side_effect=httpx.ConnectError("Connection refused")):
            files = [make_file("test.xyz")]
            with pytest.raises(LLMUnavailableError):
                client.classify_batch(files, ["文档"], "type")

    def test_timeout_retries(self):
        config = LLMConfig(api_key="sk-test", max_retries=2)
        client = LLMClient(config)
        call_count = 0

        def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.TimeoutException("timeout")
            return _make_response(
                {"categories": {"未分类": ["test.xyz"]}, "uncategorized": []},
                usage={"prompt_tokens": 50, "completion_tokens": 20},
            )

        with patch.object(client._client, "post", side_effect=mock_post):
            files = [make_file("test.xyz")]
            result, elapsed = client.classify_batch(files, ["未分类"], "type")
            assert call_count == 2
            assert "未分类" in result

    def test_empty_files_returns_empty(self):
        config = LLMConfig(api_key="sk-test")
        client = LLMClient(config)
        result, elapsed = client.classify_batch([], ["文档"], "type")
        assert result == {}
        assert elapsed == 0

    def test_api_key_in_header(self):
        config = LLMConfig(api_key="sk-test-key-123", base_url="https://api.test.com/v1")
        client = LLMClient(config)
        assert client._client.headers["Authorization"] == "Bearer sk-test-key-123"

    def test_response_without_usage_field(self):
        config = LLMConfig(api_key="sk-test")
        client = LLMClient(config)
        mock_response = _make_response(
            {"categories": {"文档": ["report.pdf"]}, "uncategorized": []},
            usage=None,
        )
        with patch.object(client._client, "post", return_value=mock_response):
            files = [make_file("report.pdf")]
            result, elapsed = client.classify_batch(files, ["文档"], "type")
            assert "文档" in result


class TestCostTracking:
    def test_cost_tracker_records_usage(self, tmp_path: Path):
        cost_file = tmp_path / "cost.jsonl"
        config = LLMConfig(api_key="sk-test")
        tracker = CostTracker(CostConfig(), cost_file)
        client = LLMClient(config, cost_tracker=tracker)

        mock_response = _make_response(
            {"categories": {"文档": ["report.pdf"]}, "uncategorized": []},
            usage={"prompt_tokens": 1500, "completion_tokens": 800},
        )
        with patch.object(client._client, "post", return_value=mock_response):
            files = [make_file("report.pdf")]
            client.classify_batch(files, ["文档"], "type")

        assert cost_file.exists()
        lines = cost_file.read_text().strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["input_tokens"] == 1500
        assert entry["output_tokens"] == 800
        assert entry["cost"] > 0

    def test_budget_exceeded_blocks_call(self, tmp_path: Path):
        cost_file = tmp_path / "cost.jsonl"
        config = LLMConfig(api_key="sk-test")
        tracker = CostTracker(
            CostConfig(monthly_budget=0.001, max_cost_per_call=0.0001, over_budget_action="block"),
            cost_file,
        )
        client = LLMClient(config, cost_tracker=tracker)

        mock_response = _make_response(
            {"categories": {"文档": ["report.pdf"]}, "uncategorized": []},
            usage={"prompt_tokens": 1500, "completion_tokens": 800},
        )
        with patch.object(client._client, "post", return_value=mock_response):
            files = [make_file("report.pdf")]
            with pytest.raises(BudgetExceededError):
                client.classify_batch(files, ["文档"], "type")

    def test_no_cost_tracker_works_as_before(self):
        config = LLMConfig(api_key="sk-test")
        client = LLMClient(config)
        mock_response = _make_response(
            {"categories": {"文档": ["report.pdf"]}, "uncategorized": []},
            usage={"prompt_tokens": 100, "completion_tokens": 50},
        )
        with patch.object(client._client, "post", return_value=mock_response):
            files = [make_file("report.pdf")]
            result, elapsed = client.classify_batch(files, ["文档"], "type")
            assert "文档" in result

    def test_call_api_returns_token_counts(self):
        config = LLMConfig(api_key="sk-test")
        client = LLMClient(config)
        mock_response = _make_response(
            {"categories": {"docs": ["a.pdf"]}, "uncategorized": []},
            usage={"prompt_tokens": 200, "completion_tokens": 100},
        )
        with patch.object(client._client, "post", return_value=mock_response):
            content, elapsed, in_tok, out_tok = client._call_api(
                [{"role": "user", "content": "test"}]
            )
            assert in_tok == 200
            assert out_tok == 100
            assert "docs" in content
