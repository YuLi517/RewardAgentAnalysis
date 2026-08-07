"""scenario 库 — P1 场景核心引擎 (PR1)"""
from scenario.model import (
    TreeShape, Growth, Revenue, CommissionConfig,
    Scenario, CommissionBreakdown, MonthSnapshot,
)
from scenario.builder import build_scenario
from scenario._pv import compute_monthly_pv, compute_weekly_period_pv
from scenario.cache import LRUDict

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
]
