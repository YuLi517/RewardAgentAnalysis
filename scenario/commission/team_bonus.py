"""PR #71 + 选项 B (2026-08-07): 团队培育奖金 4 档精确匹配 + 前 4 周订单窗口
迁移自旧 tools/rebuild_2144_simulation.py:compute_team_bonus_v3_window
"""
from __future__ import annotations
from decimal import Decimal
from typing import Dict, List

from scenario.model import Scenario
from scenario.commission._helpers import (
    get_nodes_and_children, subtree_pv_at_month, clear_all_caches,
)
from scenario._pv import compute_weekly_period_pv


def collect_period_pvs_windowed(scenario: Scenario, root_bfs: int, month: int,
                                  weekly_period_pv: List[Dict[int, int]]) -> List[int]:
    """PR2 收尾 round 3: 递归收集 root_bfs 5 子区 subtree 中, 4 周窗口内 own period_pv
    业务: 节点 own period_pv 只在"加入后前 4 个业务周"内才计入父节点培育金
    PR2 收尾关键 (round 3):
      - builder 现在 L3+ join_week 排周 (4 大区 round_robin)
      - 节点 own PV = 1500 在 join_week 那一周, 后续 4 周 0 (续费 100 不命中 4 档)
      - month = m 时, 只算 join_month == m 的节点 (4 周窗口整月)
      - 业务上: 父节点 m 月收集体是 m 月新加入 (join_month=m) 的 L3+ 子孙 own 1500
    """
    cc = scenario.commission_config
    _, children_map = get_nodes_and_children(scenario)
    nodes, _ = get_nodes_and_children(scenario)
    pvs: List[int] = []

    def _walk(bfs_id: int):
        node = nodes[bfs_id]
        # 4 周窗口检查: month - join_month < 1 (PR #71 业务)
        if month - node["join_month"] >= 1:
            return  # 出窗口
        # 节点 own PV = weekly_period_pv[node.join_week][bfs_id]
        own = weekly_period_pv[node["join_week"]].get(bfs_id, 0) if 0 <= node["join_week"] < len(weekly_period_pv) else 0
        if own > 0:
            pvs.append(own)
        # 5 子区 (slot 1-5) 都递归
        for c in children_map.get(bfs_id, []):
            if nodes[c]["slot_line_id"] <= 5:
                _walk(c)

    for c in children_map.get(root_bfs, []):
        if nodes[c]["slot_line_id"] <= 5:
            _walk(c)
    return pvs


def compute_team_bonus_v3_window(scenario: Scenario, bfs_id: int, month: int) -> Decimal:
    """PR #71 + 选项 B: 4 档精确匹配 + 4 周窗口
    业务:
      - 节点 (含 root) 拿 1区/2区 subtree 中新成员 own period_pv 的培育金
      - 4 档精确匹配: {200: 0.15, 500: 0.20, 1000: 0.25, 1500: 0.30}
      - 4 周窗口: 只算"加入后前 4 周"内的 PV
    """
    cc = scenario.commission_config
    tier_rates = cc.team_bonus_tier_rates
    if not tier_rates:
        return Decimal("0.0000")

    # 算周度 period_pv (4 周窗口需要)
    total_weeks = (scenario.total_months + 1) * 4
    _, weekly_period_pv = compute_weekly_period_pv(scenario, total_weeks)

    pvs = collect_period_pvs_windowed(scenario, bfs_id, month, weekly_period_pv)
    bonus = Decimal("0")
    for pv in pvs:
        rate = tier_rates.get(pv, 0.0)
        if rate > 0:
            bonus += Decimal(int(pv)) * Decimal(str(rate))
    return bonus.quantize(Decimal("0.0001"))


def compute_team_bonus_for_node(scenario: Scenario, bfs_id: int, month: int) -> Decimal:
    """单节点 API: 跟 v3_window 一样 (收尾后统一接口)"""
    return compute_team_bonus_v3_window(scenario, bfs_id, month)
