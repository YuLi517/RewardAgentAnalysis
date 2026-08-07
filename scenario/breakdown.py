"""scenario 单节点单月 commission breakdown 组装 (PR2 Task 8)"""
from __future__ import annotations
from decimal import Decimal
from typing import List, Tuple

from scenario.model import Scenario, CommissionBreakdown
from scenario.commission.own_basic import compute_own_basic_for_node
from scenario.commission.pair_bonus import compute_pair_bonus_for_node
from scenario.commission.team_bonus import compute_team_bonus_for_node
from scenario.commission.savings import compute_savings_for_node
from scenario.commission.leader import compute_leader_dividend_for_node
from scenario.commission.horizontal import compute_horizontal_for_node
from scenario.commission.retail_profit import compute_retail_profit_for_node
from scenario.commission.opportunity import compute_opportunity_for_node


def compute_commission_breakdown(scenario: Scenario, bfs_id: int, month: int) -> CommissionBreakdown:
    """组装 8 种报酬 + 累计 + 触发门槛
    Returns:
        CommissionBreakdown(bfs_id, month, own_basic, pair_bonus, ..., total, ip_chain, is_optimized, cumulative)
    """
    cc = scenario.commission_config

    own_basic = compute_own_basic_for_node(scenario, bfs_id, month) if cc.enable_own_basic else Decimal("0")
    pair_bonus = compute_pair_bonus_for_node(scenario, bfs_id, month) if cc.enable_pair_bonus else Decimal("0")
    team_bonus = compute_team_bonus_for_node(scenario, bfs_id, month) if cc.enable_team_bonus else Decimal("0")
    savings = compute_savings_for_node(scenario, bfs_id, month, own_basic) if cc.enable_savings else Decimal("0")
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
        ip_chain_status=[],  # PR2 stub
        is_optimized_region=False,  # PR2 stub
        cumulative_to_date_usd=total,  # PR3 加跨月累计
    )
