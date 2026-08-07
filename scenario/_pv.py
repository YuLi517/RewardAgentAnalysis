"""scenario PV 计算 (PR1, 从旧 tools/rebuild_2144_simulation.py 迁移)"""
from __future__ import annotations
from typing import Dict, List, Tuple

from scenario.model import Scenario


def _build_node_index(scenario: Scenario) -> Dict[int, dict]:
    """内部: 构节点 index (跟 builder 一致, 但不在 PR1 持久化)"""
    from scenario.builder import _build_bfs_tree
    return _build_bfs_tree(scenario.tree_shape)


def compute_monthly_pv(scenario: Scenario, total_months: int) -> Tuple[List[Dict[int, int]], List[Dict[int, int]]]:
    """算每个节点每个月的 own PV (累计) + period_pv (当月新增)
    跟旧 tools/rebuild_2144_simulation.py:compute_monthly_pv() 行为完全一致:
    - L0/L1/L2 节点不参与
    - L3+ 加入月: 累计 1500, period 1500
    - L3+ 加入月 +1 起的每个月对应颜色周: 累计 += 100, period = 100
    - 其它月: 累计不变, period = 0
    """
    nodes = _build_node_index(scenario)
    monthly_pv: List[Dict[int, int]] = [dict() for _ in range(total_months)]
    monthly_period_pv: List[Dict[int, int]] = [dict() for _ in range(total_months)]
    for bfs_id, node in nodes.items():
        if node["level"] < 3:
            continue
        join_month = node["join_month"]
        color_index = node["color_index"]
        initial_pv = scenario.revenue.initial_pv
        renew_pv = scenario.revenue.monthly_renew_pv
        cumulative = 0
        for m in range(join_month, total_months):
            if m == join_month:
                period = initial_pv
                cumulative += initial_pv
            else:
                month_color = (m % 4) + 1  # 业务 4 颜色循环
                if month_color == color_index:
                    period = renew_pv
                    cumulative += renew_pv
                else:
                    period = 0
            monthly_pv[m][bfs_id] = cumulative
            monthly_period_pv[m][bfs_id] = period
    return monthly_pv, monthly_period_pv


def compute_weekly_period_pv(scenario: Scenario, total_weeks: int) -> Tuple[List[Dict[int, int]], List[Dict[int, int]]]:
    """算每个节点每周的 own period_pv + cumulative_pv
    跟旧 monthly version 派生:
    - L3+ 加入周: cumulative += 1500 (period = 1500)
    - L3+ 续费周 (对应颜色月): cumulative += 100 (period = 100)
    - 其它周: cumulative 不变, period = 0
    """
    nodes = _build_node_index(scenario)
    total_months = (total_weeks + scenario.growth.weeks_per_month - 1) // scenario.growth.weeks_per_month
    weekly_period_pv: List[Dict[int, int]] = [dict() for _ in range(total_weeks)]
    weekly_pv: List[Dict[int, int]] = [dict() for _ in range(total_weeks)]
    for bfs_id, node in nodes.items():
        if node["level"] < 3:
            continue
        join_week = node["join_week"]
        join_month = node["join_month"]
        color_index = node["color_index"]
        cumulative = 0
        for w in range(join_week, total_weeks):
            m = w // scenario.growth.weeks_per_month
            if w == join_week:
                period = scenario.revenue.initial_pv
                cumulative += scenario.revenue.initial_pv
            elif m > join_month:
                month_color = (m % 4) + 1
                if month_color == color_index:
                    period = scenario.revenue.monthly_renew_pv
                    cumulative += scenario.revenue.monthly_renew_pv
                else:
                    period = 0
            else:
                period = 0
            weekly_period_pv[w][bfs_id] = period
            weekly_pv[w][bfs_id] = cumulative
    return weekly_pv, weekly_period_pv
