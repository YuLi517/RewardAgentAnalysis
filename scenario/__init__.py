"""scenario 库 — P1 场景核心引擎 (PR1+PR2+P1.5)"""
from scenario.model import (
    TreeShape, Growth, Revenue, CommissionConfig,
    Scenario, CommissionBreakdown,
)
from scenario._month_snapshot import MonthSnapshot  # P1.5: 8 表 + overview (新结构, 从 _month_snapshot import)
from scenario.builder import build_scenario
from scenario._pv import compute_monthly_pv, compute_weekly_period_pv
from scenario.cache import LRUDict
from scenario.breakdown import compute_commission_breakdown
from scenario.overview import compute_month_overview
from scenario.commission import (
    compute_own_basic_for_node,
    compute_pair_bonus_for_node,
    compute_team_bonus_for_node,
    compute_savings_for_node,
    compute_leader_dividend_for_node,
    compute_horizontal_for_node,
    compute_retail_profit_for_node,
    compute_opportunity_for_node,
)

__all__ = [
    # dataclass
    "TreeShape", "Growth", "Revenue", "CommissionConfig",
    "Scenario", "CommissionBreakdown", "MonthSnapshot",
    # builder
    "build_scenario",
    # pv
    "compute_monthly_pv", "compute_weekly_period_pv",
    # cache
    "LRUDict",
    # breakdown + overview (PR2)
    "compute_commission_breakdown", "compute_month_overview",
    # commission 8 functions (PR2)
    "compute_own_basic_for_node", "compute_pair_bonus_for_node",
    "compute_team_bonus_for_node", "compute_savings_for_node",
    "compute_leader_dividend_for_node", "compute_horizontal_for_node",
    "compute_retail_profit_for_node", "compute_opportunity_for_node",
]
