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
        existing_dirs: list[str] | None = None,
    ) -> tuple[dict[str, list[str]], int]:
        if not files:
            return {}, 0

        existing_dirs = existing_dirs or []
        system_prompt = self._build_system_prompt(categories, mode, existing_dirs)
        user_prompt = self._build_user_prompt(files, existing_dirs)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        raw, elapsed_ms = self._call_api(messages)
        result = self._parse_response(raw)
        logger.info(f"LLM batch: {len(files)} files, {elapsed_ms}ms, {len(result)} categories")
        return result, elapsed_ms

    def _build_system_prompt(self, categories: list[str], mode: str, existing_dirs: list[str] | None = None) -> str:
        existing_dirs = existing_dirs or []

        if mode == "semantic":
            base = (
                "你是文件分类助手。你需要将文件整理到一个已有子目录结构的文件夹中。\n\n"
                "规则：\n"
                "1. 优先将文件归入已有的子目录（如果内容匹配）\n"
                '2. 临时文件归入"临时文件"，包括：截图、安装包、日志、缓存、.tmp、'
                "单字母/极短无意义命名（如 a.sql、b.txt、x.py）\n"
                "3. 只在没有合适目录时才创建新类别\n"
                "4. 类别名要简短有意义（2-6个字）\n"
                "5. 相同模式命名的文件（如纯数字.json、UUID.xlsx）必须归入同一类别\n\n"
            )
            if existing_dirs:
                base += f"已有子目录：{', '.join(existing_dirs)}\n\n"
            base += (
                "输出格式：\n"
                '{"categories": {"类别名": ["文件名1", "文件名2"]}, "uncategorized": []}\n'
                "严格 JSON，不要解释文字。"
            )
            return base

        base = (
            "你是文件分类助手。根据文件名和元数据，将文件分到合适的类别。\n"
            "类别名由你根据文件内容自由创建，要求简短有意义（2-6个字），"
            "例如：工作文档、旅行照片、学习资料、财务报表、项目代码 等。\n"
            "相似的文件应归入同一类别。尽量合并，类别数越少越好。\n\n"
            "要求：\n"
            "1. 输出严格 JSON 格式\n"
            "2. 每个文件必须分配到一个类别\n"
            '3. 如果完全无法判断，放入 "未分类"\n'
            "4. 不要添加任何解释文字\n\n"
            "输出格式：\n"
            '{"categories": {"类别名": ["文件名1", "文件名2"]}, "uncategorized": []}'
        )
        if categories:
            cat_list = "、".join(categories)
            base += f"\n\n参考类别（可从中选择，也可自行创建新类别）：{cat_list}"
        return base

    def _build_user_prompt(self, files: list[FileItem], existing_dirs: list[str] | None = None) -> str:
        file_infos = []
        for f in files:
            info: dict[str, Any] = {
                "name": f.name + f.ext,
                "ext": f.ext,
                "size": f.size,
            }
            file_infos.append(info)
        prompt = f"请分类以下文件：\n{json.dumps(file_infos, ensure_ascii=False, indent=2)}"
        return prompt

    def _call_api(self, messages: list[dict]) -> tuple[str, int]:
        payload = {
            "model": self._config.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": self._config.max_tokens_per_call,
        }
        last_error: Exception | None = None

        for attempt in range(self._config.max_retries):
            start = time.monotonic()
            try:
                response = self._client.post("/chat/completions", json=payload)
                response.raise_for_status()
                data = response.json()
                elapsed_ms = int((time.monotonic() - start) * 1000)
                content = data["choices"][0]["message"]["content"]
                return content, elapsed_ms
            except httpx.ConnectError as e:
                elapsed_ms = int((time.monotonic() - start) * 1000)
                raise LLMUnavailableError(f"Cannot connect to {self._config.base_url}") from e
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                elapsed_ms = int((time.monotonic() - start) * 1000)
                last_error = e
                logger.warning(
                    f"LLM API retry {attempt + 1}/{self._config.max_retries}: "
                    f"{type(e).__name__}, {elapsed_ms}ms"
                )
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
