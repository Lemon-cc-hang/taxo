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
        mock_response = {"工作": ["ideas.xyz"]}
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
            return {"未分类": [f.name + f.ext for f in files]}

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

    def test_semantic_mode_sends_all_to_llm(self):
        config = TaxoConfig(
            classify=ClassifyConfig(mode="semantic"),
            llm=LLMConfig(api_key="sk-test"),
        )
        classifier = Classifier(config)
        with patch.object(classifier._llm_client, "classify_batch", return_value={"截图": ["photo.jpg"]}) as mock_llm:
            files = [make_file("photo.jpg")]
            results = classifier.classify(files)
            mock_llm.assert_called_once()

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

        def mock_classify(files, categories, mode):
            return {"未分类": [f.name + f.ext for f in files]}

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

        def mock_classify(files, categories, mode):
            nonlocal call_count
            call_count += 1
            # Each batch returns files with category based on their index
            return {f"cat_{call_count}": [f.name + f.ext for f in files]}

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

        def mock_classify(files, categories, mode):
            nonlocal call_count
            call_count += 1
            return {"未分类": [f.name + f.ext for f in files]}

        with patch.object(classifier._llm_client, "classify_batch", side_effect=mock_classify):
            files = [make_file(f"file{i}.xyz") for i in range(5)]
            results = classifier.classify(files)
            assert len(results) == 5
            assert call_count == 3
