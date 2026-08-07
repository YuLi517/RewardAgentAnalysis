"""PR #70: 零售利润 (下单管理, 非 commission 累计)
PR2 阶段: stub 返 0 (PR2 收尾实现, 跟 PR #70 下单管理联动)
P1.5: 加 compute_retail_profit_table_for_month stub 全网表
"""
from decimal import Decimal
from typing import Dict

from scenario.model import Scenario


def compute_retail_profit_for_node(scenario: Scenario, bfs_id: int, month: int) -> Decimal:
    """PR2 stub: 返 0 (零售利润不计入 commission breakdown 累计)"""
    return Decimal("0.0000")


def compute_retail_profit_table_for_month(scenario: Scenario, month: int) -> Dict[int, Decimal]:
    """P1.5: stub 全网表 (零售利润未启用, 全 0)"""
    cache_key = ("retail_table", id(scenario), month)
    if not hasattr(compute_retail_profit_table_for_month, "_cache"):
        compute_retail_profit_table_for_month._cache = {}  # type: ignore
    cache = compute_retail_profit_table_for_month._cache  # type: ignore
    if cache_key in cache:
        return cache[cache_key]

    from scenario.builder import _build_bfs_tree
    nodes = _build_bfs_tree(scenario.tree_shape)
    result = {bid: Decimal("0.0000") for bid in nodes.keys()}
    cache[cache_key] = result
    return result
