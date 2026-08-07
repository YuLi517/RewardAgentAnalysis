"""scenario 单节点单月 commission breakdown 组装 (PR2 收尾版, 性能优化)
关键优化: own_basic_dict 缓存到 scenario._own_basic_cache, 避免每节点重算全网
"""
from __future__ import annotations
from decimal import Decimal
from typing import Dict, List, Tuple

from scenario.model import Scenario, CommissionBreakdown
from scenario.builder import _build_bfs_tree
from scenario.commission.own_basic import compute_own_basic_for_node, compute_own_basic_table_for_month
from scenario.commission.pair_bonus import compute_ancestor_share_dict
from scenario.commission.team_bonus import compute_team_bonus_v3_window
from scenario.commission.savings import compute_savings_for_node
from scenario.commission.leader import compute_leader_dividend_for_node
from scenario.commission.horizontal import compute_horizontal_for_node
from scenario.commission.retail_profit import compute_retail_profit_for_node
from scenario.commission.opportunity import compute_opportunity_for_node
from scenario.commission._helpers import clear_all_caches


def _compute_all_own_basic(scenario: Scenario, month: int) -> Dict[int, Decimal]:
    """PR2 收尾: 用 compute_own_basic_table_for_month (1 次后序遍历算全网)
    替代原来循环调 compute_own_basic_for_node (慢)
    """
    return compute_own_basic_table_for_month(scenario, month)


def _compute_pair_bonus_table(scenario: Scenario, month: int,
                                own_basic_dict: Dict[int, Decimal]) -> Dict[int, Decimal]:
    """算 month 月 pair_bonus 分布表, 缓存"""
    cache_key = ("pair", id(scenario), month)
    if not hasattr(_compute_pair_bonus_table, "_cache"):
        _compute_pair_bonus_table._cache = {}  # type: ignore
    cache = _compute_pair_bonus_table._cache  # type: ignore
    if cache_key in cache:
        return cache[cache_key]
    table = compute_ancestor_share_dict(scenario, own_basic_dict)
    cache[cache_key] = table
    return table


def compute_commission_breakdown(scenario: Scenario, bfs_id: int, month: int) -> CommissionBreakdown:
    """组装 8 种报酬 + 累计 + 触发门槛
    Returns:
        CommissionBreakdown(bfs_id, month, own_basic, pair_bonus, ..., total, ip_chain, is_optimized, cumulative)
    """
    cc = scenario.commission_config

    # 1. 算全网 ownBasic (缓存)
    own_basic_dict = _compute_all_own_basic(scenario, month)
    own_basic = own_basic_dict.get(bfs_id, Decimal("0"))

    # 2. 算 pair_bonus 分布表 (缓存)
    if cc.enable_pair_bonus:
        pair_bonus_table = _compute_pair_bonus_table(scenario, month, own_basic_dict)
        pair_bonus = pair_bonus_table.get(bfs_id, Decimal("0"))
    else:
        pair_bonus = Decimal("0")

    # 3. team_bonus
    team_bonus = compute_team_bonus_v3_window(scenario, bfs_id, month) if cc.enable_team_bonus else Decimal("0")

    # 4. savings
    savings = compute_savings_for_node(scenario, bfs_id, month, own_basic) if cc.enable_savings else Decimal("0")

    # 5-7. leader / horizontal / retail / opportunity
    leader = compute_leader_dividend_for_node(scenario, bfs_id, month) if cc.enable_leader_dividend else Decimal("0")
    horiz = compute_horizontal_for_node(scenario, bfs_id, month) if cc.enable_horizontal_leader else Decimal("0")
    retail = compute_retail_profit_for_node(scenario, bfs_id, month) if cc.enable_retail_profit else Decimal("0")
    points = compute_opportunity_for_node(scenario, bfs_id, month) if cc.enable_opportunity_points else 0

    total = own_basic + pair_bonus + team_bonus + savings + leader + horiz + retail + Decimal(points)

    return CommissionBreakdown(
        bfs_id=bfs_id,
        month=month,
        own_basic_usd=own_basic,
        pair_bonus_usd=pair_bonus,
        team_bonus_usd=team_bonus,
        savings_usd=savings,
        leader_dividend_usd=leader,
        horizontal_leader_usd=horiz,
        retail_profit_usd=retail,
        opportunity_points=points,
        total_usd=total,
        ip_chain_status=[],
        is_optimized_region=False,
        cumulative_to_date_usd=total,
    )


def clear_caches():
    """清所有 breakdown 缓存 (测试间清理)"""
    if hasattr(_compute_all_own_basic, "_cache"):
        _compute_all_own_basic._cache = {}  # type: ignore
    if hasattr(_compute_pair_bonus_table, "_cache"):
        _compute_pair_bonus_table._cache = {}  # type: ignore
    clear_all_caches()
