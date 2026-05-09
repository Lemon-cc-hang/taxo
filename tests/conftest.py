import pytest
from datetime import datetime
from pathlib import Path


@pytest.fixture
def sample_file_item():
    from taxo.models import FileItem

    return FileItem(
        path=Path("/tmp/test.pdf"),
        name="test",
        ext=".pdf",
        size=1024,
        mtime=datetime(2026, 5, 1, 12, 0, 0),
        ctime=datetime(2026, 5, 1, 12, 0, 0),
        is_hidden=False,
        is_symlink=False,
    )


@pytest.fixture
def hidden_file_item():
    from taxo.models import FileItem

    return FileItem(
        path=Path("/tmp/.hidden"),
        name=".hidden",
        ext="",
        size=512,
        mtime=datetime(2026, 5, 1, 12, 0, 0),
        ctime=datetime(2026, 5, 1, 12, 0, 0),
        is_hidden=True,
        is_symlink=False,
    )


@pytest.fixture
def tmp_dir_with_files(tmp_path):
    """创建包含多种文件的临时目录。"""
    (tmp_path / "report.pdf").write_text("pdf content")
    (tmp_path / "photo.jpg").write_bytes(b"\xff\xd8\xff\xe0")
    (tmp_path / ".DS_Store").write_bytes(b"\x00")
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "data.csv").write_text("a,b,c\n1,2,3")
    return tmp_path
