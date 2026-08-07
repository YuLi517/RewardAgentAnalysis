"""PR #72 v2: 5 子区 P/L 配对 × 15%, 每条 commission line cap 13334 PV
迁移自 skills/pair_commission.py:_settle_node + §2.10 PR #68 修正
"""
from __future__ import annotations
from decimal import Decimal
from typing import Dict, List

from scenario.model import Scenario


def _subtree_pv(scenario: Scenario, bfs_id: int, month: int,
                monthly_pv: List[Dict[int, int]], children_map: Dict[int, list]) -> int:
    """递归算 subtree 月 PV (own + 子孙 PV 累加)"""
    cache_key = (id(scenario), month, bfs_id)
    if not hasattr(_subtree_pv, "_cache"):
        _subtree_pv._cache = {}  # type: ignore
    cache = _subtree_pv._cache  # type: ignore
    if cache_key in cache:
        return cache[cache_key]
    own = monthly_pv[month].get(bfs_id, 0)
    total = own
    for c in children_map.get(bfs_id, []):
        total += _subtree_pv(scenario, c, month, monthly_pv, children_map)
    cache[cache_key] = total
    return total


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


def compute_own_basic_for_node(scenario: Scenario, bfs_id: int, month: int) -> Decimal:
    """算节点 bfs_id 在 month 月的 own basic commission (PR #72 v2)
    业务:
      1. 5 子区 (slot 1-5) 各自 subtree_pv_total
      2. 排序: P = 最大子区 PV, L = sum(其他 4 子区)
      3. cap: P_capped = min(P, 13334), L_capped = min(L, 13334) per child
      4. pair = min(P_capped, sum(L_capped))
      5. ownBasic = pair × 0.15
    节点 own PV 不参与配对, 100% carry (PR #68)
    """
    from scenario.builder import _build_bfs_tree
    from scenario._pv import compute_monthly_pv

    nodes = _build_bfs_tree(scenario.tree_shape)
    children_map = _get_children_map(scenario)
    total_months = max(month + 1, scenario.total_months)
    monthly_pv, _ = compute_monthly_pv(scenario, total_months)

    cap = scenario.commission_config.own_basic_line_pv_cap
    rate = Decimal(str(scenario.commission_config.own_basic_rate))

    # 5 子区 (slot 1-5)
    child_pvs: List[int] = []
    for slot in range(1, 6):
        child = _get_slot_child(children_map, nodes, bfs_id, slot)
        if child is not None:
            subtree = _subtree_pv(scenario, child, month, monthly_pv, children_map)
            child_pvs.append(subtree)
        else:
            child_pvs.append(0)

    sorted_pvs = sorted(child_pvs, reverse=True)
    p_pv = sorted_pvs[0]
    l_pvs = sorted_pvs[1:]

    p_capped = min(p_pv, cap)
    l_capped = [min(p, cap) for p in l_pvs]
    pair = min(p_capped, sum(l_capped))

    # 清缓存 (avoid memory leak across scenarios)
    _subtree_pv._cache = {}  # type: ignore

    return (Decimal(pair) * rate).quantize(Decimal("0.0001"))
