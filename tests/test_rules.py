import pytest
from datetime import datetime
from pathlib import Path

from taxo.models import FileItem
from taxo.config import RuleConfig
from taxo.rules import RuleEngine, BUILTIN_RULES


def make_file(name: str, ext: str | None = None) -> FileItem:
    if ext is None:
        stem, _, e = name.rpartition(".")
        if not stem:
            stem, e = name, ""
        else:
            e = f".{e}"
    else:
        stem = name
        e = ext
    return FileItem(
        path=Path(f"/tmp/{name}"),
        name=stem,
        ext=e.lower(),
        size=1024,
        mtime=datetime(2026, 5, 1, 12, 0, 0),
        ctime=datetime(2026, 5, 1, 12, 0, 0),
        is_hidden=name.startswith("."),
        is_symlink=False,
    )


class TestBuiltinRules:
    def test_builtin_rules_has_expected_categories(self):
        expected = {"图片", "文档", "电子书", "代码", "数据", "压缩包", "安装包", "视频", "音频", "字体", "设计"}
        assert set(BUILTIN_RULES.keys()) == expected

    def test_builtin_rules_cover_common_exts(self):
        all_exts: set[str] = set()
        for exts in BUILTIN_RULES.values():
            all_exts.update(exts)
        assert ".pdf" in all_exts
        assert ".jpg" in all_exts
        assert ".mp4" in all_exts
        assert ".py" in all_exts
        assert ".zip" in all_exts


class TestRuleEngineMatch:
    def setup_method(self):
        self.engine = RuleEngine(RuleConfig())

    def test_match_pdf(self):
        f = make_file("report.pdf")
        assert self.engine.match(f) == "文档"

    def test_match_jpg(self):
        f = make_file("photo.jpg")
        assert self.engine.match(f) == "图片"

    def test_match_png(self):
        f = make_file("screenshot.png")
        assert self.engine.match(f) == "图片"

    def test_match_mp4(self):
        f = make_file("video.mp4")
        assert self.engine.match(f) == "视频"

    def test_match_mp3(self):
        f = make_file("song.mp3")
        assert self.engine.match(f) == "音频"

    def test_match_epub(self):
        f = make_file("book.epub")
        assert self.engine.match(f) == "电子书"

    def test_match_py(self):
        f = make_file("main.py")
        assert self.engine.match(f) == "代码"

    def test_match_zip(self):
        f = make_file("archive.zip")
        assert self.engine.match(f) == "压缩包"

    def test_match_pkg(self):
        f = make_file("installer.pkg")
        assert self.engine.match(f) == "安装包"

    def test_match_ttf(self):
        f = make_file("font.ttf")
        assert self.engine.match(f) == "字体"

    def test_match_psd(self):
        f = make_file("design.psd")
        assert self.engine.match(f) == "设计"

    def test_no_match_unknown_ext(self):
        f = make_file("data.xyz")
        assert self.engine.match(f) is None

    def test_no_match_no_ext(self):
        f = make_file("Makefile")
        assert self.engine.match(f) is None


class TestRuleEngineClassify:
    def setup_method(self):
        self.engine = RuleEngine(RuleConfig())

    def test_classify_mixed_files(self):
        files = [make_file("report.pdf"), make_file("photo.jpg"), make_file("unknown.xyz")]
        matched, unmatched = self.engine.classify(files)
        assert "文档" in matched
        assert "图片" in matched
        assert len(unmatched) == 1
        assert unmatched[0].name == "unknown"

    def test_classify_all_matched(self):
        files = [make_file("a.pdf"), make_file("b.jpg"), make_file("c.mp3")]
        matched, unmatched = self.engine.classify(files)
        assert len(unmatched) == 0

    def test_classify_none_matched(self):
        files = [make_file("a.xyz"), make_file("b.abc")]
        matched, unmatched = self.engine.classify(files)
        assert len(matched) == 0
        assert len(unmatched) == 2

    def test_classify_empty_list(self):
        matched, unmatched = self.engine.classify([])
        assert len(matched) == 0
        assert len(unmatched) == 0


class TestCustomRules:
    def test_custom_ext_rule(self):
        config = RuleConfig(custom=[{"pattern": "ext:.epub", "category": "我的电子书"}])
        engine = RuleEngine(config)
        f = make_file("book.epub")
        assert engine.match(f) == "我的电子书"

    def test_custom_pattern_rule(self):
        config = RuleConfig(custom=[{"pattern": "pattern:*invoice*", "category": "发票"}])
        engine = RuleEngine(config)
        f = make_file("invoice_2026.pdf")
        assert engine.match(f) == "发票"

    def test_custom_regex_rule(self):
        config = RuleConfig(custom=[{"pattern": "regex:^[0-9]{4}-[0-9]{2}-", "category": "日期文件"}])
        engine = RuleEngine(config)
        f = make_file("2026-05-report.pdf")
        assert engine.match(f) == "日期文件"

    def test_custom_rule_takes_priority(self):
        config = RuleConfig(custom=[{"pattern": "ext:.pdf", "category": "我的PDF"}])
        engine = RuleEngine(config)
        f = make_file("report.pdf")
        assert engine.match(f) == "我的PDF"

    def test_disable_builtin(self):
        config = RuleConfig(use_builtin=False)
        engine = RuleEngine(config)
        f = make_file("report.pdf")
        assert engine.match(f) is None

    def test_compound_rule(self):
        config = RuleConfig(custom=[{"pattern": "ext:.pdf AND pattern:*report*", "category": "报告"}])
        engine = RuleEngine(config)
        matched_f = make_file("annual_report.pdf")
        assert engine.match(matched_f) == "报告"
        unmatched_f = make_file("contract.pdf")
        assert engine.match(unmatched_f) == "文档"
