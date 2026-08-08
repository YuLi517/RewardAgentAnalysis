"""v1.0.14 (2026-08-08): 1代4 4子锁定 (DB JSON 持久化)

业务动机 (用户 2026-08-08):
  - 之前 v1.0.12/v1.0.13 每次算 1代4 都动态 BFS 凑齐 4 子, 用户担心:
    1. 每次 BFS 都有"找 4 子"逻辑, 算法 bug / cache 状态可能让 4 子集合微变
    2. 出错难定位 (debug 时 4 子是动态, 前后 2 次跑结果可能不同)
  - 拍板: 4 子关系 = scenario 树形属性, 跟 layer_counts 一样持久化
    1. scenario POST 时预计算全网 4 子 + M_first, 写入 one_gen_four_locks_json
    2. 1代4 计算 = 查表 locks, 0 BFS, 0 误差
    3. 旧 134 scenario 没这字段, lazy backfill (首次 GET 时算 + UPDATE)

设计:
  - locks[bfs_id] = {"subs": [4 sub bfs_ids], "m_first": int}
  - 叶子节点不存 (subs 为空 / 不在 locks 里)
  - 凑不齐 4 子的父节点不存 (4 子最少条件不满足)
  - 序列化: {bfs_id: {subs: [...], m_first: N}, ...} 一行 JSON
  - 反序列化: 同上, 缺字段 fallback None

性能:
  - 1 次 BFS 算全网 2144 节点 4 子关系, < 100ms (跟 v1.0.13 一样)
  - 1代4 后续 query 0 BFS, 0 重算, 0 误差
  - 跟 P1.5 一样复用 LRU cache, 1st query 后命中 0 延迟
"""
from __future__ import annotations
import json
from typing import Dict, List, Optional, Tuple

from scenario.model import Scenario
from scenario.commission._helpers import get_nodes_and_children


# locks 格式版本 (后续 schema 变化时加 version 字段做兼容)
LOCKS_VERSION = 1


def _bfs_collect_n_nodes(scenario: Scenario, root_bfs: int, n: int) -> List[int]:
    """BFS 走 root_bfs 长出树, 凑齐 n 个最近子节点 (BFS 距离优先, slot 1-5 顺序)
    跟 one_gen_four.py 里的同名函数一致, 独立拷贝避免循环引用
    """
    from collections import deque
    nodes, children_map = get_nodes_and_children(scenario)
    if root_bfs not in nodes:
        return []
    collected: List[int] = []
    queue: deque = deque()
    own_children = children_map.get(root_bfs, [])
    own_children_sorted = sorted(own_children, key=lambda c: nodes[c]["slot_line_id"])
    for c in own_children_sorted:
        queue.append(c)
    while queue and len(collected) < n:
        cur = queue.popleft()
        collected.append(cur)
        cur_children = children_map.get(cur, [])
        cur_children_sorted = sorted(cur_children, key=lambda c: nodes[c]["slot_line_id"])
        for cc in cur_children_sorted:
            queue.append(cc)
    return collected


def compute_one_gen_four_locks(scenario: Scenario) -> Dict[int, Dict]:
    """全网 1次 BFS, 算所有父节点 (非叶) 的 4 子锁定

    业务 (v1.0.14):
      - 每个非叶父节点, 跑 BFS 凑齐 4 个最近子
      - 凑齐 4 子 → locks[parent] = {"subs": [4 bfs_ids], "m_first": max(join_month of 4 子)}
      - 凑不齐 / 叶子 → 不存 (locks 字典里没有这个 parent)
    """
    nodes, children_map = get_nodes_and_children(scenario)
    locks: Dict[int, Dict] = {}
    for bfs_id in nodes.keys():
        if not children_map.get(bfs_id):
            continue  # 叶子不参与
        subs = _bfs_collect_n_nodes(scenario, bfs_id, 4)
        if len(subs) < 4:
            continue  # 凑不齐 4 子
        # 凑齐月份 M_first = 4 子中 max(join_month)
        m_first = max(nodes[c]["join_month"] for c in subs)
        locks[bfs_id] = {"subs": subs, "m_first": m_first}
    return locks


def serialize_locks(locks: Dict[int, Dict]) -> str:
    """locks dict → JSON string (DB 存储格式)
    格式: {"version": 1, "locks": {bfs_id_str: {"subs": [int, ...], "m_first": int}}}
    """
    return json.dumps({
        "version": LOCKS_VERSION,
        "locks": {str(bfs_id): {"subs": lock["subs"], "m_first": lock["m_first"]}
                  for bfs_id, lock in locks.items()},
    }, ensure_ascii=False)


def deserialize_locks(json_str: Optional[str]) -> Optional[Dict[int, Dict]]:
    """JSON string → locks dict (业务用 int key)
    None 或格式错误 → 返 None (调用方触发 backfill)
    """
    if not json_str:
        return None
    try:
        raw = json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return None
    version = raw.get("version", 1)
    if version != LOCKS_VERSION:
        # 未来 schema 变化时加迁移逻辑
        return None
    locks_raw = raw.get("locks", {})
    return {int(bfs_id): {"subs": lock["subs"], "m_first": lock["m_first"]}
            for bfs_id, lock in locks_raw.items()}


def get_lock_for_node(scenario: Scenario, bfs_id: int) -> Optional[Dict]:
    """单节点查 locks: scenario 内存 cache 优先, DB JSON 次之, 都没有触发 backfill

    业务 (v1.0.14):
      - 返回 {"subs": [4 ids], "m_first": int} 或 None
      - 优先 scenario._cache['one_gen_four_locks'] (P1.5 内存 LRU, 跨 query 复用)
      - 缺时读 DB one_gen_four_locks_json 字段
      - 都没有: 触发 lazy backfill (算全网 4 子 + UPDATE DB + 写 cache)
    """
    # 1. 内存 LRU cache (P1.5 模式, 1st query 写入, 后续 0 延迟)
    cache_key = "one_gen_four_locks"
    if not hasattr(scenario, "_cache") or scenario._cache is None:
        from scenario.cache import LRUDict
        scenario._cache = LRUDict(maxsize=15)
    locks = scenario._cache.get(cache_key) if hasattr(scenario._cache, "get") else None
    if locks is None:
        locks = {}
    if bfs_id in locks:
        return locks[bfs_id]
    # 2. DB JSON 字段 (持久化, 跨 server 重启)
    db_locks = _load_locks_from_db(scenario)
    if db_locks is not None:
        # 写回 cache
        scenario._cache.set(cache_key, db_locks)
        return db_locks.get(bfs_id)
    # 3. 都没有: 触发 backfill
    fresh_locks = compute_one_gen_four_locks(scenario)
    _persist_locks_to_db(scenario, fresh_locks)
    scenario._cache.set(cache_key, fresh_locks)
    return fresh_locks.get(bfs_id)


def _load_locks_from_db(scenario: Scenario) -> Optional[Dict[int, Dict]]:
    """从 DB 加载 locks (返 None if scenario 无 id 或 DB 字段 NULL)

    业务: scenario instance 必须是从 ScenarioRepository.load 来的 (有 _db_locks_json)
          或用户显式设了 _db_locks_json
    """
    json_str = getattr(scenario, "_db_locks_json", None)
    if json_str is None:
        return None
    return deserialize_locks(json_str)


def _persist_locks_to_db(scenario: Scenario, locks: Dict[int, Dict]) -> None:
    """locks → DB UPDATE (仅当 scenario 有 DB row)

    业务: lazy backfill 时调, 持久化避免下次重算
    """
    if not getattr(scenario, "id", None):
        return  # scenario 还没存 DB, 跳过
    json_str = serialize_locks(locks)
    from database import SessionLocal
    from models import Scenario as ScenarioORM
    db = SessionLocal()
    try:
        row = db.get(ScenarioORM, scenario.id)
        if row is not None:
            row.one_gen_four_locks_json = json_str
            db.commit()
            scenario._db_locks_json = json_str
    finally:
        db.close()
