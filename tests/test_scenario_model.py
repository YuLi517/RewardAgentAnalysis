from scenario.model import TreeShape, Growth, Revenue, CommissionConfig, Scenario, CommissionBreakdown
from scenario._month_snapshot import MonthSnapshot  # P1.5: 月快照 dataclass 已迁到 _month_snapshot
from decimal import Decimal
import pytest


def test_tree_shape_is_frozen():
    ts = TreeShape(fork_type="binary", max_level=9, layer_counts={0: 1, 1: 4})
    with pytest.raises(Exception):  # FrozenInstanceError
        ts.fork_type = "four_way"


def test_growth_defaults():
    g = Growth(nodes_per_region_per_week=9, n_regions=4, join_strategy="round_robin", weeks_per_month=4)
    assert g.weeks_per_month == 4


def test_revenue_color_names_tuple():
    r = Revenue(initial_pv=1500, monthly_renew_pv=100, color_rule="4_color_cycle", color_names=("红", "紫", "青绿", "蓝"))
    assert r.color_names[0] == "红"


def test_commission_config_all_8_toggles():
    cc = CommissionConfig(
        enable_retail_profit=True, enable_team_bonus=True,
        team_bonus_tier_rates={200: 0.15}, team_bonus_window_weeks=4,
        enable_own_basic=True, own_basic_rate=0.15, own_basic_line_pv_cap=13334,
        enable_savings=True, savings_usd_threshold=250.0, savings_rate=0.15, savings_cap_usd=500.0,
        enable_pair_bonus=True, pair_bonus_ratios={1: 0.15}, pair_bonus_4th_usd_threshold=500.0, pair_bonus_5th_usd_threshold=1000.0,
        enable_leader_dividend=True, leader_dividend_threshold_pv=13334, leader_dividend_share_usd=500.0, leader_dividend_tiers={1: 2},
        enable_horizontal_leader=True, horizontal_leader_share_usd=250.0, horizontal_leader_tiers={1: 2},
        enable_opportunity_points=False,
    )
    assert cc.enable_opportunity_points is False


def test_scenario_id_optional():
    s = Scenario(
        id=None, name="test",
        tree_shape=TreeShape("binary", 9, {0: 1}), growth=Growth(9, 4, "round_robin", 4),
        revenue=Revenue(1500, 100, "4_color_cycle", ("红",)),
        commission_config=CommissionConfig(False, False, {}, 4, False, 0.15, 13334, False, 250.0, 0.15, 500.0, False, {}, 500.0, 1000.0, False, 13334, 500.0, {}, False, 250.0, {}, False),
        total_target=2144, total_weeks=60, total_months=15,
    )
    assert s.id is None


def test_commission_breakdown_has_12_fields():
    cb = CommissionBreakdown(
        bfs_id=0, month=0,
        own_basic_usd=Decimal("0"), pair_bonus_usd=Decimal("0"), team_bonus_usd=Decimal("0"), savings_usd=Decimal("0"),
        leader_dividend_usd=Decimal("0"), horizontal_leader_usd=Decimal("0"),
        retail_profit_usd=Decimal("0"), opportunity_points=0, total_usd=Decimal("0"),
        ip_chain_status=[], is_optimized_region=False, cumulative_to_date_usd=Decimal("0"),
    )
    assert cb.bfs_id == 0


def test_month_snapshot_aggregate():
    """P1.5: MonthSnapshot 8 表 + overview (跟 PR2 旧 nodes_state + aggregate 字段不同)"""
    from scenario._month_snapshot import MonthSnapshot
    ms = MonthSnapshot(
        month=0,
        own_basic_table={}, pair_bonus_table={}, team_bonus_table={},
        savings_table={}, leader_table={}, horizontal_table={},
        retail_table={}, opportunity_table={},
        overview={"ownBasic": Decimal("100.0")},
    )
    assert ms.overview["ownBasic"] == Decimal("100.0")


def test_scenario_cache_is_lru():
    """P1.5: Scenario._cache 是 LRUDict maxsize=15"""
    from scenario.cache import LRUDict
    s = Scenario(
        id=None, name="test",
        tree_shape=TreeShape("binary", 9, {0: 1, 1: 4}), growth=Growth(9, 4, "round_robin", 4),
        revenue=Revenue(1500, 100, "4_color_cycle", ("红",)),
        commission_config=CommissionConfig(False, False, {}, 4, False, 0.15, 13334, False, 250.0, 0.15, 500.0, False, {}, 500.0, 1000.0, False, 13334, 500.0, {}, False, 250.0, {}, False),
        total_target=2144, total_weeks=60, total_months=15,
    )
    assert isinstance(s._cache, LRUDict)
    assert s._cache._maxsize == 15
