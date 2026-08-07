"""2026-08-07 横向领袖分红: Root 4 大区都优化
迁移自旧 tools/rebuild_2144_simulation.py:compute_horizontal_leader_dividend
业务:
  - Root 节点 = IP1, Root 4 大区 (region 1-4) 算 IP 4 条线
  - 触发: Root 4 大区 (4 条线) 都 4 周 ≥ 13,334 PV
  - 份数: 1 大区=2, 2 大区=2 (前 2 不算), 3 大区=4, 4 大区=6
  - 每份 $250
"""
from __future__ import annotations
from decimal import Decimal
from typing import Dict

from scenario.model import Scenario
from scenario.commission._helpers import (
    get_nodes_and_children, subtree_pv_at_month,
)
from scenario._pv import compute_monthly_pv


def compute_horizontal_for_node(scenario: Scenario, bfs_id: int, month: int) -> Decimal:
    """算 bfs_id 在 month 月拿的横向领袖分红 USD
    业务: 只 Root (bfs_id=0) 拿, 其他节点 0
    """
    if bfs_id != 0:
        return Decimal("0.00")
    cc = scenario.commission_config
    threshold_pv = cc.leader_dividend_threshold_pv  # 跟纵向同步
    monthly_threshold = threshold_pv * 4  # 53336

    # 算 Root 4 大区各自月 PV
    total_months = max(month + 1, scenario.total_months)
    monthly_pv, _ = compute_monthly_pv(scenario, total_months)

    per_region_ok: Dict[int, bool] = {}
    for region in [1, 2, 3, 4]:
        sp = subtree_pv_at_month(scenario, region, month, monthly_pv)
        per_region_ok[region] = sp >= monthly_threshold

    optimized = sum(1 for ok in per_region_ok.values() if ok)
    if optimized >= 4:
        shares = 6
    elif optimized >= 3:
        shares = 4
    elif optimized >= 1:
        shares = 2
    else:
        shares = 0
    return (Decimal(shares) * Decimal(str(cc.horizontal_leader_share_usd))).quantize(Decimal("0.01"))


def compute_horizontal_table_for_month(scenario: Scenario, month: int) -> Dict[int, Decimal]:
    """P1.5: 1 次算全网 2144 节点 horizontal_leader

    关键优化:
    - 1 次算 horizontal_leader_dividend (根节点拿, 其他返 0)
    - 1 次遍历 2144 节点, root 给值, 其他 0
    - LRU 缓存 (compute_horizontal_table_for_month._cache)
    """
    cache_key = ("horizontal_table", id(scenario), month)
    if not hasattr(compute_horizontal_table_for_month, "_cache"):
        compute_horizontal_table_for_month._cache = {}  # type: ignore
    cache = compute_horizontal_table_for_month._cache  # type: ignore
    if cache_key in cache:
        return cache[cache_key]

    from scenario.builder import _build_bfs_tree
    nodes = _build_bfs_tree(scenario.tree_shape)
    # 1 次算 horizontal 状态 (root 拿, 其他 0)
    root_value = compute_horizontal_for_node(scenario, bfs_id=0, month=month)

    result: Dict[int, Decimal] = {}
    for bfs_id in nodes.keys():
        if bfs_id == 0:
            result[bfs_id] = root_value
        else:
            result[bfs_id] = Decimal("0.00")
    cache[cache_key] = result
    return result


def compute_horizontal_leader_dividend(scenario: Scenario, month: int) -> dict:
    """PR2 收尾: 横向分红全月状态"""
    cc = scenario.commission_config
    threshold_pv = cc.leader_dividend_threshold_pv
    monthly_threshold = threshold_pv * 4
    total_months = max(month + 1, scenario.total_months)
    monthly_pv, _ = compute_monthly_pv(scenario, total_months)

    per_region_ok: Dict[int, bool] = {}
    for region in [1, 2, 3, 4]:
        sp = subtree_pv_at_month(scenario, region, month, monthly_pv)
        per_region_ok[region] = sp >= monthly_threshold
    optimized = sum(1 for ok in per_region_ok.values() if ok)
    if optimized >= 4:
        shares = 6
    elif optimized >= 3:
        shares = 4
    elif optimized >= 1:
        shares = 2
    else:
        shares = 0
    return {
        "total_shares": shares,
        "total_usd": (Decimal(shares) * Decimal(str(cc.horizontal_leader_share_usd))).quantize(Decimal("0.01")),
        "optimized_count": optimized,
        "per_region_ok": per_region_ok,
    }
