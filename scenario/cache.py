"""scenario 缓存工具 (PR1)
PR1 简化: 缓存逻辑放在 Scenario._cache 字段 (dataclass 内部), 本文件只提供 LRU 淘汰逻辑
"""
from collections import OrderedDict
from typing import Any


class LRUDict:
    """LRU 淘汰的 dict, maxsize 满了删最久未访问
    Used for Scenario._cache (PR1 阶段) + repository 层缓存 (PR3 阶段)
    """
    def __init__(self, maxsize: int = 50):
        self._data: "OrderedDict[int, Any]" = OrderedDict()
        self._maxsize = maxsize

    def get(self, key: int) -> Any:
        if key in self._data:
            self._data.move_to_end(key)
            return self._data[key]
        return None

    def set(self, key: int, value: Any) -> None:
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = value
        if len(self._data) > self._maxsize:
            self._data.popitem(last=False)

    def __contains__(self, key: int) -> bool:
        return key in self._data

    def __len__(self) -> int:
        return len(self._data)
