"""scenario 当月全网 commission 总览 (PR2 Task 8)"""
from __future__ import annotations
from collections import defaultdict
from decimal import Decimal
from typing import Dict

from scenario.model import Scenario
from scenario.builder import _build_bfs_tree
from scenario.breakdown import compute_commission_breakdown


def compute_month_overview(scenario: Scenario, month: int) -> Dict[str, Decimal]:
    """当月全网 8 种报酬合计
    Returns:
        Dict {
            "ownBasic": Decimal,
            "pairBonus": Decimal,
            "teamBonus": Decimal,
            "savings": Decimal,
            "leader": Decimal,
            "horizontal": Decimal,
            "retail": Decimal,
            "total": Decimal,
        }
    """
    nodes = _build_bfs_tree(scenario.tree_shape)
    total_months = max(month + 1, scenario.total_months)
    aggregate = defaultdict(lambda: Decimal("0"))
    for bfs_id in nodes.keys():
        cb = compute_commission_breakdown(scenario, bfs_id=bfs_id, month=month)
        aggregate["ownBasic"] += cb.own_basic_usd
        aggregate["pairBonus"] += cb.pair_bonus_usd
        aggregate["teamBonus"] += cb.team_bonus_usd
        aggregate["savings"] += cb.savings_usd
        aggregate["leader"] += cb.leader_dividend_usd
        aggregate["horizontal"] += cb.horizontal_leader_usd
        aggregate["retail"] += cb.retail_profit_usd
        aggregate["total"] += cb.total_usd
    return dict(aggregate)
