"""scenario 库 dataclass 定义 (PR1 + P1.5 缓存)"""
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from scenario._month_snapshot import MonthSnapshot
    from scenario.cache import LRUDict


@dataclass(frozen=True)
class TreeShape:
    """树形: 叉数 + 层级 + 节点数"""
    fork_type: str             # "binary" | "four_way" | "eight_way"
    max_level: int
    layer_counts: Dict[int, int]


@dataclass(frozen=True)
class Growth:
    """增长: 速度 + 加入顺序"""
    nodes_per_region_per_week: int
    n_regions: int
    join_strategy: str         # "round_robin" | "bfs" | "random"
    weeks_per_month: int


@dataclass(frozen=True)
class Revenue:
    """收入: PV + 颜色规则"""
    initial_pv: int
    monthly_renew_pv: int
    color_rule: str
    color_names: Tuple[str, ...]


@dataclass(frozen=True)
class CommissionConfig:
    """8 种报酬方式 + 参数"""
    enable_retail_profit: bool
    enable_team_bonus: bool
    team_bonus_tier_rates: Dict[int, float]
    team_bonus_window_weeks: int
    enable_own_basic: bool
    own_basic_rate: float
    own_basic_line_pv_cap: int
    enable_savings: bool
    savings_usd_threshold: float
    savings_rate: float
    savings_cap_usd: float
    enable_pair_bonus: bool
    pair_bonus_ratios: Dict[int, float]
    pair_bonus_4th_usd_threshold: float
    pair_bonus_5th_usd_threshold: float
    enable_leader_dividend: bool
    leader_dividend_threshold_pv: int
    leader_dividend_share_usd: float
    leader_dividend_tiers: Dict[int, int]
    enable_horizontal_leader: bool
    horizontal_leader_share_usd: float
    horizontal_leader_tiers: Dict[int, int]
    enable_opportunity_points: bool


@dataclass
class Scenario:
    """场景容器: 4 组参数 + 派生 + LRU 月级缓存 (P1.5)"""
    id: Optional[int]
    name: str
    tree_shape: TreeShape
    growth: Growth
    revenue: Revenue
    commission_config: CommissionConfig
    total_target: int
    total_weeks: int
    total_months: int
    # P1.5: LRU 缓存: month → MonthSnapshot (8 表 + 总览)
    # maxsize=15: 14 月全缓存 + 1 预热, 2 次查询 0 延迟
    # 引入延迟导入避免循环 (model.py 不 import 任何 commission/* 业务)
    _cache: "LRUDict[int, MonthSnapshot]" = field(
        default=None, repr=False, compare=False
    )

    def __post_init__(self):
        # LRUDict 不能在 default_factory 里直接用 (前置引用), 延后初始化
        if self._cache is None:
            from scenario.cache import LRUDict
            object.__setattr__(self, "_cache", LRUDict(maxsize=15))


@dataclass(frozen=True)
class CommissionBreakdown:
    """节点单月 8 种报酬 + 累计 + 触发门槛状态"""
    bfs_id: int
    month: int
    own_basic_usd: Decimal
    pair_bonus_usd: Decimal
    team_bonus_usd: Decimal
    savings_usd: Decimal
    leader_dividend_usd: Decimal
    horizontal_leader_usd: Decimal
    retail_profit_usd: Decimal
    opportunity_points: int
    total_usd: Decimal
    ip_chain_status: List[Tuple[int, int, int, int, bool, int]]
    is_optimized_region: bool
    cumulative_to_date_usd: Decimal


# MonthSnapshot 已迁到 scenario/_month_snapshot.py (P1.5 重构: 旧 nodes_state + aggregate → 新 8 表 + overview)
# 通过 scenario/__init__.py re-export 保持向后兼容
__all__ = [
    "TreeShape", "Growth", "Revenue", "CommissionConfig",
    "Scenario", "CommissionBreakdown",
    "MonthSnapshot",  # re-export from scenario._month_snapshot
]
