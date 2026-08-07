"""scenario LRU 缓存测试 (PR1 Task 4)"""
from scenario.cache import LRUDict


def test_lrudict_hit():
    cache = LRUDict(maxsize=3)
    cache.set(1, "a")
    assert cache.get(1) == "a"
    assert 1 in cache


def test_lrudict_eviction():
    cache = LRUDict(maxsize=2)
    cache.set(1, "a")
    cache.set(2, "b")
    cache.set(3, "c")  # 触发淘汰 1
    assert cache.get(1) is None
    assert cache.get(2) == "b"
    assert cache.get(3) == "c"


def test_lrudict_access_updates_order():
    cache = LRUDict(maxsize=2)
    cache.set(1, "a")
    cache.set(2, "b")
    cache.get(1)  # 访问 1, 移到最后
    cache.set(3, "c")  # 淘汰 2 (最久未访问)
    assert cache.get(1) == "a"
    assert cache.get(2) is None
    assert cache.get(3) == "c"


def test_lrudict_overwrite():
    cache = LRUDict(maxsize=3)
    cache.set(1, "a")
    cache.set(1, "b")  # 覆盖
    assert cache.get(1) == "b"
    assert len(cache) == 1


def test_lrudict_maxsize_zero():
    """maxsize=0 行为: set 后立即淘汰 (边写边淘汰)"""
    cache = LRUDict(maxsize=0)
    cache.set(1, "a")
    assert cache.get(1) is None
    assert len(cache) == 0
