from __future__ import annotations

import logging

from taxo.config import TaxoConfig
from taxo.llm import LLMClient, LLMUnavailableError
from taxo.models import ClassifyResult, FileItem
from taxo.rules import RuleEngine

logger = logging.getLogger(__name__)


class Classifier:
    def __init__(self, config: TaxoConfig) -> None:
        self._config = config
        self._rule_engine = RuleEngine(config.rules)
        self._llm_client = LLMClient(config.llm) if config.llm.api_key else None

    def classify(self, files: list[FileItem]) -> list[ClassifyResult]:
        if not files:
            return []

        if self._config.classify.mode == "semantic":
            return self._classify_semantic(files)

        return self._classify_hybrid(files)

    def _classify_hybrid(self, files: list[FileItem]) -> list[ClassifyResult]:
        matched, unmatched = self._rule_engine.classify(files)
        results = self._build_rule_results(matched)

        if unmatched:
            results.extend(self._classify_with_llm(unmatched))

        return results

    def _classify_semantic(self, files: list[FileItem]) -> list[ClassifyResult]:
        return self._classify_with_llm(files)

    def _classify_with_llm(self, files: list[FileItem]) -> list[ClassifyResult]:
        if not self._llm_client:
            return self._build_uncategorized_results(files)

        categories = self._get_categories()
        batch_size = self._config.classify.batch_size
        results: list[ClassifyResult] = []

        for i in range(0, len(files), batch_size):
            batch = files[i : i + batch_size]
            try:
                category_map = self._llm_client.classify_batch(
                    batch, categories, self._config.classify.mode
                )
                results.extend(self._map_llm_results(batch, category_map))
            except LLMUnavailableError:
                logger.warning("LLM unavailable, falling back to uncategorized")
                results.extend(self._build_uncategorized_results(batch))

        return results

    def _get_categories(self) -> list[str]:
        if self._config.classify.categories:
            return [
                c["name"] if isinstance(c, dict) else str(c)
                for c in self._config.classify.categories
            ]
        return [
            "财务", "报告", "合同", "发票", "个人", "工作",
            "学习", "娱乐", "截图", "备份", "临时", "未分类",
        ]

    def _build_rule_results(
        self, matched: dict[str, list[FileItem]]
    ) -> list[ClassifyResult]:
        results = []
        for category, files in matched.items():
            for f in files:
                results.append(
                    ClassifyResult(
                        file=f,
                        category=category,
                        subcategory=None,
                        confidence=1.0,
                        method="rule",
                        reason=f"扩展名匹配: {f.ext}",
                    )
                )
        return results

    def _map_llm_results(
        self, files: list[FileItem], category_map: dict[str, list[str]]
    ) -> list[ClassifyResult]:
        file_lookup = {f.name + f.ext: f for f in files}
        results: list[ClassifyResult] = []
        matched_files: set[str] = set()

        for category, filenames in category_map.items():
            for filename in filenames:
                if filename in file_lookup:
                    results.append(
                        ClassifyResult(
                            file=file_lookup[filename],
                            category=category,
                            subcategory=None,
                            confidence=0.8,
                            method="llm",
                            reason=f"LLM 分类: {category}",
                        )
                    )
                    matched_files.add(filename)

        for f in files:
            if f.name + f.ext not in matched_files:
                results.append(
                    ClassifyResult(
                        file=f,
                        category="未分类",
                        subcategory=None,
                        confidence=0.5,
                        method="llm",
                        reason="LLM 未能分类",
                    )
                )

        return results

    def _build_uncategorized_results(self, files: list[FileItem]) -> list[ClassifyResult]:
        return [
            ClassifyResult(
                file=f,
                category="未分类",
                subcategory=None,
                confidence=0.0,
                method="rule",
                reason="无匹配规则且 LLM 不可用",
            )
            for f in files
        ]
