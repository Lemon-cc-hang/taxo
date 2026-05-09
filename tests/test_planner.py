import pytest
from datetime import datetime
from pathlib import Path

from taxo.config import OrganizeConfig
from taxo.models import ClassifyResult, FileItem
from taxo.planner import Planner


def make_file(name: str, path_prefix: str = "/tmp") -> FileItem:
    stem, _, e = name.rpartition(".")
    if not stem:
        stem, e = name, ""
    else:
        e = f".{e}"
    return FileItem(
        path=Path(f"{path_prefix}/{name}"),
        name=stem,
        ext=e.lower(),
        size=1024,
        mtime=datetime(2026, 5, 1, 12, 0, 0),
        ctime=datetime(2026, 5, 1, 12, 0, 0),
        is_hidden=False,
        is_symlink=False,
    )


def make_result(name: str, category: str, path_prefix: str = "/tmp") -> ClassifyResult:
    return ClassifyResult(
        file=make_file(name, path_prefix),
        category=category,
        subcategory=None,
        confidence=1.0,
        method="rule",
        reason=f"test: {category}",
    )


class TestPlannerFlatStructure:
    def setup_method(self):
        self.config = OrganizeConfig(structure="flat", conflict_strategy="rename")
        self.planner = Planner(self.config)
        self.source = Path("/tmp/downloads")

    def test_flat_plan_generates_category_dirs(self):
        results = [make_result("report.pdf", "文档"), make_result("photo.jpg", "图片")]
        plan = self.planner.create_plan(results, self.source)
        targets = {op.target for op in plan.operations}
        assert any("文档" in str(t) for t in targets)
        assert any("图片" in str(t) for t in targets)

    def test_flat_plan_preserves_filename(self):
        results = [make_result("report.pdf", "文档")]
        plan = self.planner.create_plan(results, self.source)
        assert plan.operations[0].target.name == "report.pdf"

    def test_in_place_organize(self):
        results = [make_result("report.pdf", "文档", "/tmp/downloads")]
        plan = self.planner.create_plan(results, self.source)
        assert str(plan.operations[0].target).startswith(str(self.source))

    def test_move_to_target_dir(self):
        config = OrganizeConfig(structure="flat", conflict_strategy="rename", target_dir="/tmp/organized")
        planner = Planner(config)
        results = [make_result("report.pdf", "文档")]
        plan = planner.create_plan(results, self.source)
        assert "/tmp/organized" in str(plan.operations[0].target)


class TestPlannerDateStructure:
    def test_date_structure_includes_year_month(self):
        config = OrganizeConfig(structure="date", conflict_strategy="rename", date_template="{category}/{year}/{month}")
        planner = Planner(config)
        results = [make_result("report.pdf", "文档")]
        plan = planner.create_plan(results, Path("/tmp"))
        target = str(plan.operations[0].target)
        assert "2026" in target
        assert "05" in target


class TestConflictHandling:
    def test_rename_on_conflict(self, tmp_path):
        (tmp_path / "文档").mkdir()
        (tmp_path / "文档" / "report.pdf").write_text("existing")
        config = OrganizeConfig(structure="flat", conflict_strategy="rename")
        planner = Planner(config)
        results = [make_result("report.pdf", "文档")]
        plan = planner.create_plan(results, tmp_path)
        assert plan.operations[0].action == "rename"
        assert plan.operations[0].target.name != "report.pdf"

    def test_skip_on_conflict(self, tmp_path):
        (tmp_path / "图片").mkdir()
        (tmp_path / "图片" / "photo.jpg").write_text("existing")
        config = OrganizeConfig(structure="flat", conflict_strategy="skip")
        planner = Planner(config)
        results = [make_result("photo.jpg", "图片")]
        plan = planner.create_plan(results, tmp_path)
        assert plan.operations[0].action == "skip"

    def test_no_conflict_normal_move(self, tmp_path):
        config = OrganizeConfig(structure="flat", conflict_strategy="rename")
        planner = Planner(config)
        results = [make_result("report.pdf", "文档")]
        plan = planner.create_plan(results, tmp_path)
        assert plan.operations[0].action == "move"


class TestPlanStats:
    def test_plan_stats_populated(self):
        config = OrganizeConfig(structure="flat", conflict_strategy="rename")
        planner = Planner(config)
        source = Path("/tmp")
        results = [make_result("report.pdf", "文档"), make_result("photo.jpg", "图片"), make_result("song.mp3", "音频")]
        plan = planner.create_plan(results, source)
        assert plan.stats.total_files == 3
        assert "文档" in plan.stats.by_category
        assert "图片" in plan.stats.by_category
        assert "音频" in plan.stats.by_category

    def test_plan_has_id_and_timestamp(self):
        config = OrganizeConfig(structure="flat", conflict_strategy="rename")
        planner = Planner(config)
        source = Path("/tmp")
        results = [make_result("report.pdf", "文档")]
        plan = planner.create_plan(results, source)
        assert plan.id
        assert plan.timestamp
