"""PR #72 v2: 5 子区 P/L 配对 × 15%, 每条 commission line cap 13334 PV
PR2 收尾关键优化: compute_own_basic_table_for_month 1 次算全网 2144 节点 ownBasic
单节点 API compute_own_basic_for_node 维持兼容, 但内部调全网表 + 选单节点
"""
from __future__ import annotations
from decimal import Decimal
from typing import Dict, List

from scenario.model import Scenario


def _get_children_map(scenario: Scenario) -> Dict[int, list]:
    """构 children_map {parent_bfs: [child_bfs, ...]}"""
    from scenario.builder import _build_bfs_tree
    nodes = _build_bfs_tree(scenario.tree_shape)
    cm: Dict[int, list] = {}
    for n in nodes.values():
        if n["parent_bfs"] >= 0:
            cm.setdefault(n["parent_bfs"], []).append(n["bfs_id"])
    return cm


def _get_slot_child(children_map: Dict[int, list], nodes: Dict[int, dict], bfs_id: int, slot: int):
    """找 bfs_id 子中 slot_line_id == slot 的那个"""
    for c in children_map.get(bfs_id, []):
        if nodes[c]["slot_line_id"] == slot:
            return c
    return None


def compute_own_basic_table_for_month(scenario: Scenario, month: int) -> Dict[int, Decimal]:
    """PR2 收尾: 1 次算 month 月全网每个节点的 own_basic
    关键优化: 1 次后序遍历算 subtree_pv_table, 然后 1 次遍历算 2144 个节点的 own_basic
    Returns: {bfs_id: own_basic_usd}
    """
    cache_key = ("own_basic_table", id(scenario), month)
    if not hasattr(compute_own_basic_table_for_month, "_cache"):
        compute_own_basic_table_for_month._cache = {}  # type: ignore
    cache = compute_own_basic_table_for_month._cache  # type: ignore
    if cache_key in cache:
        return cache[cache_key]

    from scenario.builder import _build_bfs_tree
    from scenario._pv import compute_monthly_pv

    nodes = _build_bfs_tree(scenario.tree_shape)
    children_map = _get_children_map(scenario)
    total_months = max(month + 1, scenario.total_months)
    monthly_pv, _ = compute_monthly_pv(scenario, total_months)

    cap = scenario.commission_config.own_basic_line_pv_cap
    rate = Decimal(str(scenario.commission_config.own_basic_rate))

    # 1 次后序遍历算 month 月所有节点 subtree_pv
    subtree_pv_table: Dict[int, int] = {}
    for node in sorted(nodes.values(), key=lambda n: -n["level"]):
        bfs = node["bfs_id"]
        own = monthly_pv[month].get(bfs, 0)
        child_total = sum(subtree_pv_table.get(c, 0) for c in children_map.get(bfs, []))
        subtree_pv_table[bfs] = own + child_total

    # 1 次遍历算所有节点 own_basic
    result: Dict[int, Decimal] = {}
    for bfs_id in nodes.keys():
        child_pvs: List[int] = []
        for slot in range(1, 6):
            child = _get_slot_child(children_map, nodes, bfs_id, slot)
            if child is not None:
                child_pvs.append(subtree_pv_table[child])
            else:
                child_pvs.append(0)
        sorted_pvs = sorted(child_pvs, reverse=True)
        p_pv = sorted_pvs[0]
        l_pvs = sorted_pvs[1:]
        p_capped = min(p_pv, cap)
        l_capped = [min(p, cap) for p in l_pvs]
        pair = min(p_capped, sum(l_capped))
        result[bfs_id] = (Decimal(pair) * rate).quantize(Decimal("0.0001"))

    cache[cache_key] = result
    return result


def compute_own_basic_for_node(scenario: Scenario, bfs_id: int, month: int) -> Decimal:
    """单节点 API: 内部用全网表 (缓存), O(1) 查表"""
    table = compute_own_basic_table_for_month(scenario, month)
    return table.get(bfs_id, Decimal("0.0000"))
