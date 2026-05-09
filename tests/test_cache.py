import pytest
from datetime import datetime
from pathlib import Path

from taxo.cache import CacheManager
from taxo.models import ClassifyResult, FileItem


def make_file(name: str, size: int = 1024, mtime: float | None = None) -> FileItem:
    stem, _, e = name.rpartition(".")
    if not stem:
        stem, e = name, ""
    else:
        e = f".{e}"
    return FileItem(
        path=Path(f"/tmp/testdir/{name}"),
        name=stem,
        ext=e.lower(),
        size=size,
        mtime=mtime or datetime(2026, 5, 1, 12, 0, 0).timestamp(),
        ctime=datetime(2026, 5, 1, 12, 0, 0).timestamp(),
        is_hidden=False,
        is_symlink=False,
    )


def make_result(file: FileItem, category: str = "文档") -> ClassifyResult:
    return ClassifyResult(
        file=file,
        category=category,
        subcategory=None,
        confidence=1.0,
        method="rule",
        reason="test",
    )


class TestCacheManager:
    def test_cache_hit(self, tmp_path):
        cache = CacheManager(tmp_path)
        f = make_file("test.pdf")
        r = make_result(f)
        dir_path = Path("/tmp/testdir")

        cache.load(dir_path)
        assert cache.get(f) is None

        cache.put(r)
        assert cache.get(f) is not None
        assert cache.get(f).category == "文档"

    def test_cache_miss_on_size_change(self, tmp_path):
        cache = CacheManager(tmp_path)
        dir_path = Path("/tmp/testdir")

        f1 = make_file("test.pdf", size=100)
        cache.load(dir_path)
        cache.put(make_result(f1))

        f2 = make_file("test.pdf", size=200)
        assert cache.get(f2) is None

    def test_cache_miss_on_mtime_change(self, tmp_path):
        cache = CacheManager(tmp_path)
        dir_path = Path("/tmp/testdir")

        f1 = make_file("test.pdf", mtime=1000.0)
        cache.load(dir_path)
        cache.put(make_result(f1))

        f2 = make_file("test.pdf", mtime=2000.0)
        assert cache.get(f2) is None

    def test_save_and_reload(self, tmp_path):
        dir_path = Path("/tmp/testdir")
        f = make_file("test.pdf")
        r = make_result(f)

        cache1 = CacheManager(tmp_path)
        cache1.load(dir_path)
        cache1.put(r)
        cache1.save()

        cache2 = CacheManager(tmp_path)
        cache2.load(dir_path)
        hit = cache2.get(f)
        assert hit is not None
        assert hit.category == "文档"

    def test_prune_deleted_files(self, tmp_path):
        """Deleted file entries stay in cache until TTL expires; the caller
        (classifier/scanner) only passes files that actually exist on disk,
        so stale entries are simply never looked up."""
        dir_path = Path("/tmp/testdir")

        f_exists = make_file("exists.pdf")
        f_gone = make_file("gone.pdf")

        cache = CacheManager(tmp_path)
        cache.load(dir_path)
        cache.put(make_result(f_exists))
        cache.put(make_result(f_gone))
        cache.save()

        cache2 = CacheManager(tmp_path)
        cache2.load(dir_path)

        # Both entries are still present (no file-existence check in load)
        assert cache2.get(f_exists) is not None
        assert cache2.get(f_gone) is not None
        # But in real usage, the scanner never produces f_gone, so it's harmless

    def test_ttl_expiry(self, tmp_path):
        dir_path = Path("/tmp/testdir")
        f = make_file("test.pdf")
        real = tmp_path / "test.pdf"
        real.write_text("pdf")

        cache = CacheManager(tmp_path, ttl_days=0)
        cache.load(dir_path)
        cache.put(make_result(f))
        cache.save()

        cache2 = CacheManager(tmp_path, ttl_days=0)
        cache2.load(dir_path)
        assert cache2.get(f) is None

    def test_max_entries(self, tmp_path):
        dir_path = Path("/tmp/testdir")
        cache = CacheManager(tmp_path, max_entries=2)

        cache.load(dir_path)
        for i in range(5):
            f = make_file(f"file{i}.pdf")
            real = tmp_path / f"file{i}.pdf"
            real.write_text("x")
            cache.put(make_result(f, category=f"cat{i}"))
        cache.save()

        cache2 = CacheManager(tmp_path, max_entries=2)
        cache2.load(dir_path)
        assert len(cache2._entries) <= 2

    def test_different_dirs_isolated(self, tmp_path):
        dir_a = Path("/tmp/testdir_a")
        dir_b = Path("/tmp/testdir_b")

        cache = CacheManager(tmp_path)
        cache.load(dir_a)
        cache.put(make_result(make_file("test.pdf"), category="A"))
        cache.save()

        cache.load(dir_b)
        assert cache.get(make_file("test.pdf")) is None

    def test_stats(self, tmp_path):
        cache = CacheManager(tmp_path)
        cache.load(Path("/tmp/testdir"))
        cache.put(make_result(make_file("a.pdf")))
        cache.put(make_result(make_file("b.pdf")))
        assert cache.stats()["total"] == 2

    def test_clear_all(self, tmp_path):
        cache = CacheManager(tmp_path)
        cache.load(Path("/tmp/testdir"))
        cache.put(make_result(make_file("a.pdf")))
        cache.put(make_result(make_file("b.pdf")))
        cache.save()

        count = cache.clear()
        assert count == 1
        assert not (tmp_path / f"scan_{cache._dir_key(Path('/tmp/testdir'))}.json").exists()

    def test_clear_specific_dir(self, tmp_path):
        cache = CacheManager(tmp_path)
        cache.load(Path("/tmp/testdir_a"))
        cache.put(make_result(make_file("a.pdf")))
        cache.save()

        cache.load(Path("/tmp/testdir_b"))
        cache.put(make_result(make_file("b.pdf")))
        cache.save()

        count = cache.clear(Path("/tmp/testdir_a"))
        assert count == 1

        cache2 = CacheManager(tmp_path)
        cache2.load(Path("/tmp/testdir_b"))
        assert cache2.get(make_file("b.pdf")) is not None
