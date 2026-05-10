import pytest
from datetime import datetime
from pathlib import Path

from taxo.config import ScanConfig
from taxo.scanner import scan_files, scan_dir_structure


class TestScanFiles:
    def test_scan_basic_files(self, tmp_dir_with_files):
        config = ScanConfig()
        results = scan_files(tmp_dir_with_files, config)
        names = {f.name + f.ext for f in results}
        assert "report.pdf" in names
        assert "photo.jpg" in names
        assert "data.csv" in names

    def test_excludes_ds_store(self, tmp_dir_with_files):
        config = ScanConfig()
        results = scan_files(tmp_dir_with_files, config)
        names = {f.path.name for f in results}
        assert ".DS_Store" not in names

    def test_excludes_hidden_files(self, tmp_path):
        (tmp_path / ".hidden_file").write_text("hidden")
        (tmp_path / "normal.txt").write_text("normal")
        config = ScanConfig()
        results = scan_files(tmp_path, config)
        names = {f.path.name for f in results}
        assert ".hidden_file" not in names
        assert "normal.txt" in names

    def test_includes_hidden_when_configured(self, tmp_path):
        (tmp_path / ".hidden_file").write_text("hidden")
        config = ScanConfig(exclude=["*.tmp"])
        results = scan_files(tmp_path, config)
        names = {f.path.name for f in results}
        assert ".hidden_file" in names

    def test_excludes_dirs(self, tmp_path):
        (tmp_path / "file.txt").write_text("ok")
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("git config")
        config = ScanConfig(exclude_dirs=[".git"])
        results = scan_files(tmp_path, config)
        names = {f.path.name for f in results}
        assert "config" not in names
        assert "file.txt" in names

    def test_max_depth(self, tmp_path):
        (tmp_path / "level0.txt").write_text("0")
        sub1 = tmp_path / "sub1"
        sub1.mkdir()
        (sub1 / "level1.txt").write_text("1")
        sub2 = sub1 / "sub2"
        sub2.mkdir()
        (sub2 / "level2.txt").write_text("2")
        config = ScanConfig(max_depth=1)
        results = scan_files(tmp_path, config)
        names = {f.path.name for f in results}
        assert "level0.txt" in names
        assert "level1.txt" in names
        assert "level2.txt" not in names

    def test_min_size_filter(self, tmp_path):
        (tmp_path / "small.txt").write_text("hi")
        (tmp_path / "big.txt").write_text("x" * 1000)
        config = ScanConfig(min_size=100)
        results = scan_files(tmp_path, config)
        names = {f.path.name for f in results}
        assert "small.txt" not in names
        assert "big.txt" in names

    def test_max_size_filter(self, tmp_path):
        (tmp_path / "small.txt").write_text("hi")
        (tmp_path / "big.txt").write_text("x" * 1000)
        config = ScanConfig(max_size=500)
        results = scan_files(tmp_path, config)
        names = {f.path.name for f in results}
        assert "small.txt" in names
        assert "big.txt" not in names

    def test_exclude_pattern(self, tmp_path):
        (tmp_path / "file.tmp").write_text("temp")
        (tmp_path / "file.txt").write_text("normal")
        config = ScanConfig(exclude=["*.tmp", ".*"])
        results = scan_files(tmp_path, config)
        names = {f.path.name for f in results}
        assert "file.tmp" not in names
        assert "file.txt" in names

    def test_file_item_metadata(self, tmp_dir_with_files):
        config = ScanConfig()
        results = scan_files(tmp_dir_with_files, config)
        pdf = next(f for f in results if f.ext == ".pdf")
        assert pdf.name == "report"
        assert pdf.ext == ".pdf"
        assert pdf.size > 0
        assert isinstance(pdf.mtime, datetime)
        assert isinstance(pdf.ctime, datetime)
        assert pdf.is_symlink is False

    def test_skips_symlinks(self, tmp_path):
        real = tmp_path / "real.txt"
        real.write_text("content")
        link = tmp_path / "link.txt"
        link.symlink_to(real)
        config = ScanConfig()
        results = scan_files(tmp_path, config)
        names = {f.path.name for f in results}
        assert "real.txt" in names
        assert "link.txt" not in names

    def test_empty_directory(self, tmp_path):
        config = ScanConfig()
        results = scan_files(tmp_path, config)
        assert results == []

    def test_nonexistent_directory_raises(self):
        config = ScanConfig()
        with pytest.raises(FileNotFoundError):
            scan_files(Path("/nonexistent/path"), config)

    def test_ext_is_lowercase(self, tmp_path):
        (tmp_path / "file.PDF").write_text("pdf")
        config = ScanConfig(exclude=[])
        results = scan_files(tmp_path, config)
        f = results[0]
        assert f.ext == ".pdf"

    def test_no_ext_file(self, tmp_path):
        (tmp_path / "Makefile").write_text("all:")
        config = ScanConfig(exclude=[])
        results = scan_files(tmp_path, config)
        f = results[0]
        assert f.name == "Makefile"
        assert f.ext == ""


class TestScanDirStructure:
    def test_returns_subdirectory_names(self, tmp_path):
        (tmp_path / "工作文档").mkdir()
        (tmp_path / "旅行照片").mkdir()
        (tmp_path / "some_file.txt").write_text("file")
        dirs = scan_dir_structure(tmp_path)
        assert dirs == ["工作文档", "旅行照片"]

    def test_excludes_hidden_dirs(self, tmp_path):
        (tmp_path / ".hidden").mkdir()
        (tmp_path / "visible").mkdir()
        dirs = scan_dir_structure(tmp_path)
        assert dirs == ["visible"]

    def test_returns_sorted(self, tmp_path):
        (tmp_path / "zebra").mkdir()
        (tmp_path / "alpha").mkdir()
        (tmp_path / "mid").mkdir()
        dirs = scan_dir_structure(tmp_path)
        assert dirs == ["alpha", "mid", "zebra"]

    def test_empty_directory(self, tmp_path):
        dirs = scan_dir_structure(tmp_path)
        assert dirs == []

    def test_no_permission(self):
        dirs = scan_dir_structure(Path("/nonexistent"))
        assert dirs == []
