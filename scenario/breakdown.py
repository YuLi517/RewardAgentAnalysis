"""scenario 单节点单月 commission breakdown 组装 (PR2 收尾版 + P1.5 性能优化)
关键优化 (P1.5):
- own_basic / pair_bonus / team_bonus / savings / leader / horizontal / retail / opportunity
  8 张全网表 (1 次后序遍历算全网 2144 节点), breakdown 改用查表替代循环单节点
- 跟 own_basic PR2 round 3 模式一致
v1.0.12: 加 1代4 商品价值 (one_gen_four, 第 9 种报酬, 父节点凑齐 4 子 = 95 PV)
"""
from __future__ import annotations
from decimal import Decimal
from typing import Dict, List, Tuple

from scenario.model import Scenario, CommissionBreakdown
from scenario.builder import _build_bfs_tree
from scenario.commission.own_basic import compute_own_basic_for_node, compute_own_basic_table_for_month
from scenario.commission.pair_bonus import compute_ancestor_share_dict
from scenario.commission.team_bonus import compute_team_bonus_table_for_month
from scenario.commission.savings import compute_savings_table_for_month
from scenario.commission.leader import compute_leader_dividend_table_for_month
from scenario.commission.horizontal import compute_horizontal_table_for_month
from scenario.commission.retail_profit import compute_retail_profit_table_for_month
from scenario.commission.opportunity import compute_opportunity_table_for_month
from scenario.commission.one_gen_four import compute_one_gen_four_table_for_month
from scenario.commission._helpers import clear_all_caches


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
    """组装 9 种报酬 + 累计 + 触发门槛 (P1.5: 改用 8 张全网表查表, v1.0.12 加 1代4)

    性能优化 (跟 PR2 round 3 模式一致):
    - 1. ownBasic 全网表 (已有 compute_own_basic_table_for_month)
    - 2. pair_bonus 全网表 (compute_ancestor_share_dict)
    - 3-8. 6 个新 *_table_for_month (P1.5 新加)
    - 9. one_gen_four 全网表 (v1.0.12 新加, 父节点凑齐 4 子 = 95 PV)
    - breakdown 改用 .get(bfs_id, 0) 查表, 替代循环 2144 节点 6 个单节点函数

    Returns:
        CommissionBreakdown(bfs_id, month, own_basic, pair_bonus, ..., one_gen_four, total, ip_chain, is_optimized, cumulative)
    """
    cc = scenario.commission_config

    # 1. 算全网 ownBasic (缓存)
    own_basic_dict = compute_own_basic_table_for_month(scenario, month)
    own_basic = own_basic_dict.get(bfs_id, Decimal("0"))

    # 2. 算 pair_bonus 分布表 (缓存)
    if cc.enable_pair_bonus:
        pair_bonus_table = _compute_pair_bonus_table(scenario, month, own_basic_dict)
        pair_bonus = pair_bonus_table.get(bfs_id, Decimal("0"))
    else:
        pair_bonus = Decimal("0")

    # 3. team_bonus (P1.5: 全网表查表)
    if cc.enable_team_bonus:
        team_bonus_table = compute_team_bonus_table_for_month(scenario, month)
        team_bonus = team_bonus_table.get(bfs_id, Decimal("0"))
    else:
        team_bonus = Decimal("0")

    # 4. savings (P1.5: 全网表查表, 内部复用 own_basic 全网表)
    if cc.enable_savings:
        savings_table = compute_savings_table_for_month(scenario, month)
        savings = savings_table.get(bfs_id, Decimal("0"))
    else:
        savings = Decimal("0")

    # 5-7. leader / horizontal / retail (P1.5: 全网表查表)
    if cc.enable_leader_dividend:
        leader_table = compute_leader_dividend_table_for_month(scenario, month)
        leader = leader_table.get(bfs_id, Decimal("0"))
    else:
        leader = Decimal("0")

    if cc.enable_horizontal_leader:
        horiz_table = compute_horizontal_table_for_month(scenario, month)
        horiz = horiz_table.get(bfs_id, Decimal("0"))
    else:
        horiz = Decimal("0")

    if cc.enable_retail_profit:
        retail_table = compute_retail_profit_table_for_month(scenario, month)
        retail = retail_table.get(bfs_id, Decimal("0"))
    else:
        retail = Decimal("0")

    # 8. opportunity (P1.5: 全网表查表, stub 全 0)
    if cc.enable_opportunity_points:
        points_table = compute_opportunity_table_for_month(scenario, month)
        points = points_table.get(bfs_id, 0)
    else:
        points = 0

    # 9. one_gen_four (v1.0.12: 全网表查表, 父节点凑齐 4 子 = 95 PV 固定)
    # 业务 always on, 不挂 enable flag (跟 opportunity 一样的处理)
    one_gen_four_table = compute_one_gen_four_table_for_month(scenario, month)
    one_gen_four = one_gen_four_table.get(bfs_id, Decimal("0"))

    total = own_basic + pair_bonus + team_bonus + savings + leader + horiz + retail + Decimal(points) + one_gen_four

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
        one_gen_four_usd=one_gen_four,
        total_usd=total,
        ip_chain_status=[],
        is_optimized_region=False,
        cumulative_to_date_usd=total,
    )


def clear_caches():
    """清所有 breakdown 缓存 (测试间清理)"""
    if hasattr(_compute_pair_bonus_table, "_cache"):
        _compute_pair_bonus_table._cache = {}  # type: ignore
    # P1.5: own_basic 全网表 + 6 个新 table_for_month cache
    for fn in (
        compute_own_basic_table_for_month,
        compute_team_bonus_table_for_month,
        compute_savings_table_for_month,
        compute_leader_dividend_table_for_month,
        compute_horizontal_table_for_month,
        compute_retail_profit_table_for_month,
        compute_opportunity_table_for_month,
    ):
        if hasattr(fn, "_cache"):
            fn._cache = {}  # type: ignore
    clear_all_caches()
