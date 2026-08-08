"""scenario commission 内部 helpers (PR2 收尾 + v1.0.16 节点表持久化)
共享子树 PV 计算, children_map 缓存
v1.0.16: 优先查 DB scenario_nodes 表, fallback 动态算
"""
from __future__ import annotations
from typing import Dict, List, Optional

from scenario.model import Scenario


def get_nodes_and_children(scenario: Scenario) -> tuple:
    """返 (nodes, children_map) — 内部 cache 防重复 build

    v1.0.16 业务:
      - 优先从 DB scenario_nodes 表读 (持久化, 业务稳定)
      - fallback: _build_bfs_tree 动态算 (旧 scenario 没 nodes 表数据)
      - 内存 LRU cache 防重复查 DB

    Returns:
        nodes: Dict[bfs_id, dict] (含 level/parent_bfs/slot_line_id/region_id/...)
        children_map: Dict[parent_bfs, List[child_bfs]]
    """
    cache_key = id(scenario)
    if not hasattr(get_nodes_and_children, "_cache"):
        get_nodes_and_children._cache = {}  # type: ignore
    cache = get_nodes_and_children._cache  # type: ignore
    if cache_key in cache:
        return cache[cache_key]

    # v1.0.16: 优先查 DB (持久化节点表)
    nodes = None
    if getattr(scenario, "id", None):
        try:
            from database import SessionLocal
            from scenario.nodes import load_scenario_nodes
            db = SessionLocal()
            try:
                nodes = load_scenario_nodes(db, scenario.id)
            finally:
                db.close()
        except Exception:
            # 业务上 DB 失败时 fallback 动态算
            nodes = None

    if nodes is None:
        # Fallback: 动态算 (旧 scenario 没 nodes 表数据, 或 DB 失败)
        from scenario.builder import _build_bfs_tree
        nodes = _build_bfs_tree(scenario.tree_shape)

    children_map: Dict[int, list] = {}
    for n in nodes.values():
        if n["parent_bfs"] >= 0:
            children_map.setdefault(n["parent_bfs"], []).append(n["bfs_id"])
    cache[cache_key] = (nodes, children_map)
    return nodes, children_map


def get_parent_map(scenario: Scenario) -> Dict[int, int]:
    """返 {bfs_id: parent_bfs}"""
    nodes, _ = get_nodes_and_children(scenario)
    return {bid: n["parent_bfs"] for bid, n in nodes.items() if n["parent_bfs"] >= 0}


def subtree_pv_at_month(scenario: Scenario, bfs_id: int, month: int,
                          monthly_pv: List[Dict[int, int]]) -> int:
    """递归算 bfs_id subtree 月 PV (own + 子孙 PV 累加)"""
    cache_key = (id(scenario), month, bfs_id)
    if not hasattr(subtree_pv_at_month, "_cache"):
        subtree_pv_at_month._cache = {}  # type: ignore
    cache = subtree_pv_at_month._cache  # type: ignore
    if cache_key in cache:
        return cache[cache_key]
    _, children_map = get_nodes_and_children(scenario)
    own = monthly_pv[month].get(bfs_id, 0)
    total = own
    for c in children_map.get(bfs_id, []):
        total += subtree_pv_at_month(scenario, c, month, monthly_pv)
    cache[cache_key] = total
    return total


def clear_all_caches():
    """清所有内部 cache (测试间清理, 防 memory leak)"""
    if hasattr(get_nodes_and_children, "_cache"):
        get_nodes_and_children._cache = {}  # type: ignore
    if hasattr(subtree_pv_at_month, "_cache"):
        subtree_pv_at_month._cache = {}  # type: ignore
