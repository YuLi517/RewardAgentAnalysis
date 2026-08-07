"""第 8 种: 机遇积分 (用户 2026-08-07 拍板第 8 种报酬方式)
PR2 阶段: stub 返 0 (业务规则未拍板, raise NotImplementedError when enabled)
P1.5: 加 compute_opportunity_table_for_month stub 全网表
"""
from typing import Dict

from scenario.model import Scenario


def compute_opportunity_for_node(scenario: Scenario, bfs_id: int, month: int) -> int:
    """PR2 stub: 返 0. 业务规则用户未拍板, 启用时 raise NotImplementedError"""
    if scenario.commission_config.enable_opportunity_points:
        raise NotImplementedError(
            "机遇积分 (第 8 种) 业务规则用户未拍板, 暂未实现. 业务上下文: 用户 2026-08-07 brainstorming"
        )
    return 0


def compute_opportunity_table_for_month(scenario: Scenario, month: int) -> Dict[int, int]:
    """P1.5: stub 全网表 (机遇积分未实现, 全 0)"""
    if scenario.commission_config.enable_opportunity_points:
        raise NotImplementedError(
            "机遇积分 (第 8 种) 业务规则用户未拍板, 暂未实现. 业务上下文: 用户 2026-08-07 brainstorming"
        )

    cache_key = ("opportunity_table", id(scenario), month)
    if not hasattr(compute_opportunity_table_for_month, "_cache"):
        compute_opportunity_table_for_month._cache = {}  # type: ignore
    cache = compute_opportunity_table_for_month._cache  # type: ignore
    if cache_key in cache:
        return cache[cache_key]

    from scenario.builder import _build_bfs_tree
    nodes = _build_bfs_tree(scenario.tree_shape)
    result = {bid: 0 for bid in nodes.keys()}
    cache[cache_key] = result
    return result
