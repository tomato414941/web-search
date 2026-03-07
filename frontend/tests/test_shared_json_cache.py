import logging

from frontend.services.shared_json_cache import SharedJsonTtlCache


def test_shared_json_cache_reads_shared_entry_after_memory_clear(tmp_path):
    cache = SharedJsonTtlCache(
        str(tmp_path / "shared-cache.json"),
        logger=logging.getLogger("test.shared_json_cache"),
        label="test cache",
    )
    cache.set({"value": 1}, 30)

    cache.clear_memory()
    cached = cache.get_shared(validator=lambda data: isinstance(data, dict))

    assert cached == {"value": 1}


def test_shared_json_cache_honors_cache_key(tmp_path):
    cache = SharedJsonTtlCache(
        str(tmp_path / "shared-cache.json"),
        logger=logging.getLogger("test.shared_json_cache"),
        label="test cache",
    )
    cache.set([{"value": 1}], 30, cache_key=[{"name": "default"}])

    cached = cache.get_shared(
        cache_key=[{"name": "other"}],
        validator=lambda data: isinstance(data, list),
    )

    assert cached is None


def test_shared_json_cache_clear_removes_file_and_memory(tmp_path):
    cache = SharedJsonTtlCache(
        str(tmp_path / "shared-cache.json"),
        logger=logging.getLogger("test.shared_json_cache"),
        label="test cache",
    )
    cache.set({"value": 1}, 30)

    cache.clear()

    assert not tmp_path.joinpath("shared-cache.json").exists()
    assert cache.get_memory() is None
