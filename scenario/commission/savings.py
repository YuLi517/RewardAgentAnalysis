"""PR #73: 储蓄奖金
ownBasic ≥ $250 → savings = min(ownBasic × 15%, $500)
P1.5: 加 compute_savings_table_for_month 全网表 (跟 own_basic 模式一致)
"""
from decimal import Decimal
from typing import Dict

from scenario.model import Scenario


def compute_savings_for_node(scenario: Scenario, bfs_id: int, month: int,
                              own_basic_usd: Decimal) -> Decimal:
    """PR #73: savings = min(ownBasic × 15%, $500) if ownBasic ≥ $250
    注: breakdown.py 已经传 own_basic_usd 进来, 这里只算阈值/cap
    """
    cc = scenario.commission_config
    if own_basic_usd < Decimal(str(cc.savings_usd_threshold)):
        return Decimal("0.0000")
    s = min(
        own_basic_usd * Decimal(str(cc.savings_rate)),
        Decimal(str(cc.savings_cap_usd))
    )
    return s.quantize(Decimal("0.0001"))


def compute_savings_table_for_month(scenario: Scenario, month: int) -> Dict[int, Decimal]:
    """P1.5: 1 次算全网 2144 节点 savings (基于 own_basic 全网表 + 阈值/cap)

    关键优化:
    - 1 次拿 own_basic 全网表 (compute_own_basic_table_for_month, 已缓存)
    - 1 次遍历 2144 节点, apply 阈值 + cap
    - LRU 缓存 (compute_savings_table_for_month._cache)
    """
    cache_key = ("savings_table", id(scenario), month)
    if not hasattr(compute_savings_table_for_month, "_cache"):
        compute_savings_table_for_month._cache = {}  # type: ignore
    cache = compute_savings_table_for_month._cache  # type: ignore
    if cache_key in cache:
        return cache[cache_key]

    from scenario.builder import _build_bfs_tree
    from scenario.commission.own_basic import compute_own_basic_table_for_month

    cc = scenario.commission_config
    threshold = Decimal(str(cc.savings_usd_threshold))
    rate = Decimal(str(cc.savings_rate))
    cap = Decimal(str(cc.savings_cap_usd))

    own_basic_table = compute_own_basic_table_for_month(scenario, month)
    nodes = _build_bfs_tree(scenario.tree_shape)
    result: Dict[int, Decimal] = {}
    for bfs_id in nodes.keys():
        ob = own_basic_table.get(bfs_id, Decimal("0"))
        if ob < threshold:
            result[bfs_id] = Decimal("0.0000")
        else:
            result[bfs_id] = min(ob * rate, cap).quantize(Decimal("0.0001"))

    cache[cache_key] = result
    return result
