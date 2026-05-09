from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import httpx

from taxo.config import LLMConfig
from taxo.models import FileItem

logger = logging.getLogger(__name__)


class LLMUnavailableError(Exception):
    pass


class LLMClient:
    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        self._client = httpx.Client(
            base_url=config.base_url,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=config.timeout,
        )

    def classify_batch(
        self,
        files: list[FileItem],
        categories: list[str],
        mode: str,
    ) -> dict[str, list[str]]:
        if not files:
            return {}

        system_prompt = self._build_system_prompt(categories, mode)
        user_prompt = self._build_user_prompt(files)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        raw = self._call_api(messages)
        return self._parse_response(raw)

    def _build_system_prompt(self, categories: list[str], mode: str) -> str:
        cat_list = "、".join(categories)
        return (
            f"你是文件分类助手。根据文件名和元数据，将文件分类到以下类别：\n"
            f"{cat_list}\n\n"
            f"要求：\n"
            f"1. 输出严格 JSON 格式\n"
            f"2. 每个文件必须分配到一个类别\n"
            f'3. 如果不确定，放入 "未分类"\n'
            f"4. 不要添加任何解释文字\n\n"
            f"输出格式：\n"
            f'{{"categories": {{"类别名": ["文件名1", "文件名2"]}}, "uncategorized": []}}'
        )

    def _build_user_prompt(self, files: list[FileItem]) -> str:
        file_infos = []
        for f in files:
            info: dict[str, Any] = {
                "name": f.name + f.ext,
                "ext": f.ext,
                "size": f.size,
            }
            file_infos.append(info)
        return f"请分类以下文件：\n{json.dumps(file_infos, ensure_ascii=False, indent=2)}"

    def _call_api(self, messages: list[dict]) -> str:
        payload = {
            "model": self._config.model,
            "messages": messages,
            "temperature": 0.1,
        }
        last_error: Exception | None = None

        for attempt in range(self._config.max_retries):
            try:
                response = self._client.post("/chat/completions", json=payload)
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
            except httpx.ConnectError as e:
                raise LLMUnavailableError(f"Cannot connect to {self._config.base_url}") from e
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                last_error = e
                logger.warning(f"LLM API attempt {attempt + 1} failed: {e}")
                if attempt < self._config.max_retries - 1:
                    time.sleep(2 ** attempt)

        raise LLMUnavailableError(
            f"LLM API failed after {self._config.max_retries} retries: {last_error}"
        )

    def _parse_response(self, raw: str) -> dict[str, list[str]]:
        cleaned = raw.strip()
        markdown_match = re.match(r"```(?:json)?\s*\n?(.*?)\n?```", cleaned, re.DOTALL)
        if markdown_match:
            cleaned = markdown_match.group(1).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM response as JSON: {raw[:200]}")
            return {}

        if "categories" not in data or not isinstance(data["categories"], dict):
            logger.warning(f"LLM response missing 'categories' key: {raw[:200]}")
            return {}

        result: dict[str, list[str]] = {}
        for category, filenames in data["categories"].items():
            if isinstance(filenames, list):
                result[category] = [str(f) for f in filenames]

        return result
