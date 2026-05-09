from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from taxo.cache import CacheManager
from taxo.config import TaxoConfig
from taxo.llm import LLMClient, LLMUnavailableError
from taxo.models import ClassifyResult, FileItem
from taxo.rules import RuleEngine

logger = logging.getLogger(__name__)


class Classifier:
    def __init__(self, config: TaxoConfig, cache: CacheManager | None = None) -> None:
        self._config = config
        self._rule_engine = RuleEngine(config.rules)
        self._llm_client = LLMClient(config.llm) if config.llm.api_key else None
        self._cache = cache

    def classify(
        self, files: list[FileItem], source_dir: Path | None = None
    ) -> list[ClassifyResult]:
        if not files:
            return []

        if self._cache and source_dir:
            return self._classify_with_cache(files, source_dir)

        if self._config.classify.mode == "semantic":
            return self._classify_semantic(files)

        return self._classify_hybrid(files)

    def _classify_with_cache(
        self, files: list[FileItem], source_dir: Path
    ) -> list[ClassifyResult]:
        self._cache.load(source_dir)

        cached_results: list[ClassifyResult] = []
        missed_files: list[FileItem] = []

        for f in files:
            hit = self._cache.get(f)
            if hit is not None:
                cached_results.append(hit)
            else:
                missed_files.append(f)

        if missed_files:
            if self._config.classify.mode == "semantic":
                new_results = self._classify_semantic(missed_files)
            else:
                new_results = self._classify_hybrid(missed_files)

            for r in new_results:
                if r.method == "llm":
                    self._cache.put(r)
            cached_results.extend(new_results)

        self._cache.save()

        hit_count = len(cached_results) - len(missed_files)
        if hit_count > 0:
            logger.info(f"Cache: {hit_count} hits, {len(missed_files)} misses")

        return cached_results

    def _classify_hybrid(self, files: list[FileItem]) -> list[ClassifyResult]:
        matched, unmatched = self._rule_engine.classify(files)
        results = self._build_rule_results(matched)

        # 对规则匹配的文件进一步细分（文档类按启发式/LLM细分）
        refined = self._refine_rule_results(results)
        results = refined

        if unmatched:
            if self._llm_client:
                results.extend(self._classify_with_llm(unmatched))
            else:
                results.extend(self._classify_by_heuristics(unmatched))

        return results

    def _refine_rule_results(self, results: list[ClassifyResult]) -> list[ClassifyResult]:
        needs_refine = {"文档"}
        to_refine = [r for r in results if r.category in needs_refine]
        keep = [r for r in results if r.category not in needs_refine]

        if not to_refine:
            return results

        if self._llm_client:
            refined = self._classify_with_llm([r.file for r in to_refine])
        else:
            refined = self._classify_by_heuristics([r.file for r in to_refine])

        return keep + refined

    def _classify_semantic(self, files: list[FileItem]) -> list[ClassifyResult]:
        return self._classify_with_llm(files)

    def _classify_with_llm(self, files: list[FileItem]) -> list[ClassifyResult]:
        if not self._llm_client:
            return self._classify_by_heuristics(files)

        batch_size = self._config.classify.batch_size
        max_workers = self._config.classify.max_workers
        batches = [files[i : i + batch_size] for i in range(0, len(files), batch_size)]

        def classify_one(batch: list[FileItem]) -> list[ClassifyResult]:
            try:
                category_map = self._llm_client.classify_batch(
                    batch, [], self._config.classify.mode
                )
                return self._map_llm_results(batch, category_map)
            except LLMUnavailableError:
                logger.warning("LLM unavailable, falling back to heuristic classification")
                return self._classify_by_heuristics(batch)

        results: list[ClassifyResult] = []

        if len(batches) <= 1 or max_workers <= 1:
            for batch in batches:
                results.extend(classify_one(batch))
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {pool.submit(classify_one, b): i for i, b in enumerate(batches)}
                ordered: list[list[ClassifyResult] | None] = [None] * len(batches)
                for future in as_completed(futures):
                    ordered[futures[future]] = future.result()
            for batch_results in ordered:
                if batch_results:
                    results.extend(batch_results)

        return results

    def _classify_by_heuristics(self, files: list[FileItem]) -> list[ClassifyResult]:
        results: list[ClassifyResult] = []
        for f in files:
            category = self._guess_category(f)
            results.append(
                ClassifyResult(
                    file=f,
                    category=category,
                    subcategory=None,
                    confidence=0.5,
                    method="rule",
                    reason=f"启发式分类: {category}",
                )
            )
        return results

    def _guess_category(self, file: FileItem) -> str:
        name = file.name.lower()

        if any(kw in name for kw in ["invoice", "发票", "收据", "receipt"]):
            return "发票"
        if any(kw in name for kw in ["report", "报告", "总结", "summary"]):
            return "报告"
        if any(kw in name for kw in ["contract", "合同", "协议", "agreement"]):
            return "合同"
        if any(kw in name for kw in ["resume", "简历", "cv"]):
            return "简历"
        if any(kw in name for kw in ["screenshot", "截图", "screen", "截图"]):
            return "截图"
        if any(kw in name for kw in ["backup", "备份", "bak"]):
            return "备份"
        if any(kw in name for kw in ["logo", "icon", "头像", "avatar", "banner"]):
            return "设计素材"
        if any(kw in name for kw in ["wallpaper", "壁纸", "background"]):
            return "壁纸"
        if any(kw in name for kw in ["mem", "表情", "sticker", "emoji"]):
            return "表情包"
        if any(kw in name for kw in ["photo", "照片", "img", "pic", "camera", "dcim"]):
            return "照片"
        if any(kw in name for kw in ["doc", "文档", "document"]):
            return "文档"
        if any(kw in name for kw in ["install", "setup", "安装"]):
            return "安装包"
        if any(kw in name for kw in ["project", "项目"]):
            return "项目"
        if any(kw in name for kw in ["test", "测试"]):
            return "测试"
        if any(kw in name for kw in ["config", "配置", "setting"]):
            return "配置"
        if any(kw in name for kw in ["readme", "说明"]):
            return "说明"

        import re
        date_pattern = r"(?:20\d{2})[\-_]?(?:0[1-9]|1[0-2])[\-_]?(?:0[1-9]|[12]\d|3[01])"
        if re.search(date_pattern, name):
            return "按日期归档"

        if file.ext in (".pdf", ".doc", ".docx", ".txt", ".md", ".rtf"):
            return "其他文档"
        if file.ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"):
            return "其他图片"
        if file.ext in (".mp4", ".avi", ".mkv", ".mov", ".webm"):
            return "其他视频"
        if file.ext in (".mp3", ".wav", ".flac", ".aac", ".ogg"):
            return "其他音频"
        if file.ext in (".zip", ".rar", ".7z", ".tar", ".gz"):
            return "其他压缩包"
        if file.ext in (".js", ".ts", ".py", ".java", ".go", ".rs", ".cpp"):
            return "代码片段"
        if file.ext in (".json", ".yaml", ".yml", ".xml", ".csv"):
            return "数据文件"

        return "未分类"

    def _get_categories(self) -> list[str]:
        if self._config.classify.categories:
            return [
                c["name"] if isinstance(c, dict) else str(c)
                for c in self._config.classify.categories
            ]
        return []

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
