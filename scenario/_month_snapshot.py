"""P1.5: MonthSnapshot dataclass — 某月 8 报酬全网表 + 总览 (缓存精度)

业务 (P1.5):
- 1 MonthSnapshot ≈ 280KB (2144 节点 × 8 表 × 16 字节)
- LRU maxsize=15, 14 月全缓存 + 1 预热
- 第 2 次查询 0 延迟 (LRU 命中)
- 跟 scenario/breakdown.py compute_commission_breakdown 8 表查询保持一致
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict


@dataclass(frozen=True)
class MonthSnapshot:
    """某月 8 报酬全网表 + 总览 (P1.5 缓存精度, 算 1 次存 LRU)

    8 张全网表 + 1 张总览 (8 报酬合计), 算 1 次存, 避免重复 sum
    """
    month: int
    own_basic_table: Dict[int, Decimal]
    pair_bonus_table: Dict[int, Decimal]
    team_bonus_table: Dict[int, Decimal]
    savings_table: Dict[int, Decimal]
    leader_table: Dict[int, Decimal]
    horizontal_table: Dict[int, Decimal]
    retail_table: Dict[int, Decimal]
    opportunity_table: Dict[int, int]    # opportunity 是积分, 不是 USD
    # 总览 (8 报酬合计), 算 1 次存, 避免重复 sum
    overview: Dict[str, Decimal]


def build_month_snapshot(scenario, month: int) -> MonthSnapshot:
    """算 month 月 8 张表 + 总览, 1 次算 1 个 MonthSnapshot

    注: 调用 8 个 table_for_month 函数, 跟 breakdown.py 保持一致
    """
    from scenario.commission.own_basic import compute_own_basic_table_for_month
    from scenario.commission.pair_bonus import compute_ancestor_share_dict
    from scenario.commission.team_bonus import compute_team_bonus_table_for_month
    from scenario.commission.savings import compute_savings_table_for_month
    from scenario.commission.leader import compute_leader_dividend_table_for_month
    from scenario.commission.horizontal import compute_horizontal_table_for_month
    from scenario.commission.retail_profit import compute_retail_profit_table_for_month
    from scenario.commission.opportunity import compute_opportunity_table_for_month

    cc = scenario.commission_config
    own_basic_table = compute_own_basic_table_for_month(scenario, month) if cc.enable_own_basic else {}
    pair_bonus_table = compute_ancestor_share_dict(scenario, own_basic_table) if cc.enable_pair_bonus else {}
    team_bonus_table = compute_team_bonus_table_for_month(scenario, month) if cc.enable_team_bonus else {}
    savings_table = compute_savings_table_for_month(scenario, month) if cc.enable_savings else {}
    leader_table = compute_leader_dividend_table_for_month(scenario, month) if cc.enable_leader_dividend else {}
    horizontal_table = compute_horizontal_table_for_month(scenario, month) if cc.enable_horizontal_leader else {}
    retail_table = compute_retail_profit_table_for_month(scenario, month) if cc.enable_retail_profit else {}
    opportunity_table = compute_opportunity_table_for_month(scenario, month) if cc.enable_opportunity_points else {}

    # 算总览 (8 报酬合计, 跑 1 次)
    from scenario.builder import _build_bfs_tree
    nodes = _build_bfs_tree(scenario.tree_shape)
    aggregate: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for bfs_id in nodes.keys():
        aggregate["ownBasic"] += own_basic_table.get(bfs_id, Decimal("0"))
        aggregate["pairBonus"] += pair_bonus_table.get(bfs_id, Decimal("0"))
        aggregate["teamBonus"] += team_bonus_table.get(bfs_id, Decimal("0"))
        aggregate["savings"] += savings_table.get(bfs_id, Decimal("0"))
        aggregate["leader"] += leader_table.get(bfs_id, Decimal("0"))
        aggregate["horizontal"] += horizontal_table.get(bfs_id, Decimal("0"))
        aggregate["retail"] += retail_table.get(bfs_id, Decimal("0"))
    aggregate["total"] = (
        aggregate["ownBasic"] + aggregate["pairBonus"] + aggregate["teamBonus"]
        + aggregate["savings"] + aggregate["leader"] + aggregate["horizontal"]
        + aggregate["retail"]
    )

    return MonthSnapshot(
        month=month,
        own_basic_table=own_basic_table,
        pair_bonus_table=pair_bonus_table,
        team_bonus_table=team_bonus_table,
        savings_table=savings_table,
        leader_table=leader_table,
        horizontal_table=horizontal_table,
        retail_table=retail_table,
        opportunity_table=opportunity_table,
        overview=dict(aggregate),
    )
