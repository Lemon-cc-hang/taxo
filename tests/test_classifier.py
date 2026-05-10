import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from taxo.classifier import Classifier
from taxo.config import TaxoConfig, LLMConfig, ClassifyConfig, RuleConfig
from taxo.models import FileItem


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


class TestClassifierRuleOnly:
    def test_all_rule_matched(self):
        config = TaxoConfig()
        classifier = Classifier(config)
        files = [make_file("song.mp3"), make_file("archive.zip")]
        results = classifier.classify(files)
        assert len(results) == 2
        categories = {r.category for r in results}
        assert "音频" in categories
        assert "压缩包" in categories

    def test_confidence_is_1_for_non_refined_rules(self):
        config = TaxoConfig()
        classifier = Classifier(config)
        files = [make_file("song.mp3")]
        results = classifier.classify(files)
        assert results[0].confidence == 1.0
        assert results[0].method == "rule"


class TestClassifierWithLLM:
    def test_llm_classifies_unmatched_files(self):
        config = TaxoConfig(llm=LLMConfig(api_key="sk-test"))
        classifier = Classifier(config)
        mock_response = ({"工作": ["ideas.xyz"]}, 500)
        with patch.object(classifier._llm_client, "classify_batch", return_value=mock_response):
            files = [make_file("photo.jpg"), make_file("ideas.xyz")]
            results = classifier.classify(files)
            assert len(results) == 2
            rule_result = next(r for r in results if r.method == "rule")
            assert rule_result.category == "图片"
            llm_result = next(r for r in results if r.method == "llm")
            assert llm_result.category == "工作"

    def test_llm_unavailable_falls_back_to_uncategorized(self):
        from taxo.llm import LLMUnavailableError
        config = TaxoConfig(llm=LLMConfig(api_key="sk-test"))
        classifier = Classifier(config)
        with patch.object(classifier._llm_client, "classify_batch", side_effect=LLMUnavailableError("connection failed")):
            files = [make_file("unknown.xyz")]
            results = classifier.classify(files)
            assert len(results) == 1
            assert results[0].category == "未分类"
            assert results[0].method == "rule"

    def test_llm_batching(self):
        config = TaxoConfig(
            llm=LLMConfig(api_key="sk-test"),
            classify=ClassifyConfig(batch_size=2),
        )
        classifier = Classifier(config)
        call_count = 0

        def mock_classify(files, categories, mode):
            nonlocal call_count
            call_count += 1
            return {"未分类": [f.name + f.ext for f in files]}, 100

        with patch.object(classifier._llm_client, "classify_batch", side_effect=mock_classify):
            files = [make_file(f"file{i}.xyz") for i in range(5)]
            classifier.classify(files)
            assert call_count == 3


class TestClassifierModes:
    def test_type_mode(self):
        config = TaxoConfig(classify=ClassifyConfig(mode="type"))
        classifier = Classifier(config)
        files = [make_file("photo.jpg")]
        results = classifier.classify(files)
        assert results[0].category == "图片"

    def test_type_mode_no_llm_even_with_api_key(self):
        config = TaxoConfig(
            llm=LLMConfig(api_key="sk-test"),
            classify=ClassifyConfig(mode="type"),
        )
        classifier = Classifier(config)
        with patch.object(classifier._llm_client, "classify_batch") as mock_llm:
            files = [make_file("unknown.xyz")]
            results = classifier.classify(files)
            mock_llm.assert_not_called()
            assert results[0].method == "rule"

    def test_semantic_mode_sends_all_to_llm(self):
        config = TaxoConfig(
            classify=ClassifyConfig(mode="semantic"),
            llm=LLMConfig(api_key="sk-test"),
        )
        classifier = Classifier(config)
        with patch.object(classifier._llm_client, "classify_batch", return_value=({"截图": ["photo.jpg"]}, 200)) as mock_llm:
            files = [make_file("photo.jpg")]
            results = classifier.classify(files)
            mock_llm.assert_called_once()
            call_kwargs = mock_llm.call_args
            assert call_kwargs[1].get("existing_dirs") is not None or len(call_kwargs[0]) >= 4

    def test_semantic_mode_passes_existing_dirs(self, tmp_path):
        from taxo.scanner import scan_dir_structure

        subdir_a = tmp_path / "工作文档"
        subdir_b = tmp_path / "旅行照片"
        subdir_a.mkdir()
        subdir_b.mkdir()

        dirs = scan_dir_structure(tmp_path)
        assert "工作文档" in dirs
        assert "旅行照片" in dirs
        assert len(dirs) == 2

        config = TaxoConfig(
            classify=ClassifyConfig(mode="semantic"),
            llm=LLMConfig(api_key="sk-test"),
        )
        classifier = Classifier(config)
        with patch.object(classifier._llm_client, "classify_batch", return_value=({"工作文档": ["ideas.xyz"]}, 300)) as mock_llm:
            files = [FileItem(
                path=tmp_path / "ideas.xyz",
                name="ideas",
                ext=".xyz",
                size=1024,
                mtime=datetime(2026, 5, 1, 12, 0, 0),
                ctime=datetime(2026, 5, 1, 12, 0, 0),
                is_hidden=False,
                is_symlink=False,
            )]
            results = classifier.classify(files)
            mock_llm.assert_called_once()
            call_args = mock_llm.call_args
            existing_dirs = call_args.kwargs.get("existing_dirs") or call_args[1].get("existing_dirs")
            assert existing_dirs is not None
            assert "工作文档" in existing_dirs
            assert "旅行照片" in existing_dirs

    def test_semantic_mode_falls_back_without_llm(self):
        config = TaxoConfig(classify=ClassifyConfig(mode="semantic"))
        classifier = Classifier(config)
        files = [make_file("photo.jpg")]
        results = classifier.classify(files)
        assert results[0].category == "图片"
        assert results[0].method == "rule"

    def test_empty_files(self):
        config = TaxoConfig()
        classifier = Classifier(config)
        results = classifier.classify([])
        assert results == []


class TestClassifierConcurrency:
    def test_concurrent_llm_batches_complete(self):
        config = TaxoConfig(
            llm=LLMConfig(api_key="sk-test"),
            classify=ClassifyConfig(batch_size=2, max_workers=3),
        )
        classifier = Classifier(config)

        def mock_classify(files, categories, mode, **kwargs):
            return {"未分类": [f.name + f.ext for f in files]}, 100

        with patch.object(classifier._llm_client, "classify_batch", side_effect=mock_classify):
            files = [make_file(f"file{i}.xyz") for i in range(7)]
            results = classifier.classify(files)
            assert len(results) == 7
            assert all(r.method == "llm" for r in results)

    def test_concurrent_preserves_order(self):
        config = TaxoConfig(
            llm=LLMConfig(api_key="sk-test"),
            classify=ClassifyConfig(batch_size=2, max_workers=3),
        )
        classifier = Classifier(config)
        call_count = 0

        def mock_classify(files, categories, mode, **kwargs):
            nonlocal call_count
            call_count += 1
            return {f"cat_{call_count}": [f.name + f.ext for f in files]}, 100

        with patch.object(classifier._llm_client, "classify_batch", side_effect=mock_classify):
            files = [make_file(f"file{i}.xyz") for i in range(6)]
            results = classifier.classify(files)
            names = [r.file.name + r.file.ext for r in results]
            expected = [f"file{i}.xyz" for i in range(6)]
            assert names == expected

    def test_single_worker_is_serial(self):
        config = TaxoConfig(
            llm=LLMConfig(api_key="sk-test"),
            classify=ClassifyConfig(batch_size=2, max_workers=1),
        )
        classifier = Classifier(config)
        call_count = 0

        def mock_classify(files, categories, mode, **kwargs):
            nonlocal call_count
            call_count += 1
            return {"未分类": [f.name + f.ext for f in files]}, 100

        with patch.object(classifier._llm_client, "classify_batch", side_effect=mock_classify):
            files = [make_file(f"file{i}.xyz") for i in range(5)]
            results = classifier.classify(files)
            assert len(results) == 5
            assert call_count == 3


class TestClassifierCacheOnlyLLM:
    def test_only_llm_results_cached(self, tmp_path):
        from taxo.cache import CacheManager
        from taxo.config import CacheConfig

        config = TaxoConfig(llm=LLMConfig(api_key="sk-test"))
        cache = CacheManager(tmp_path, ttl_days=30)
        classifier = Classifier(config, cache)

        def mock_classify(files, categories, mode, **kwargs):
            return {"LLM类别": [f.name + f.ext for f in files]}, 100

        with patch.object(classifier._llm_client, "classify_batch", side_effect=mock_classify):
            # song.mp3 -> rule match (音频), ideas.xyz -> LLM match
            files = [make_file("song.mp3"), make_file("ideas.xyz")]
            results = classifier.classify(files, source_dir=Path("/tmp/testdir"))

        # Cache should only have the LLM result
        assert cache.stats()["total"] == 1
        assert cache.get(make_file("ideas.xyz")) is not None
        assert cache.get(make_file("song.mp3")) is None
