from scenario.builder import build_scenario
from scenario.model import TreeShape, Growth, Revenue, CommissionConfig
from decimal import Decimal

def _default_config() -> CommissionConfig:
    return CommissionConfig(
        enable_retail_profit=False, enable_team_bonus=True,
        team_bonus_tier_rates={200: 0.15, 500: 0.20, 1000: 0.25, 1500: 0.30},
        team_bonus_window_weeks=4,
        enable_own_basic=True, own_basic_rate=0.15, own_basic_line_pv_cap=13334,
        enable_savings=True, savings_usd_threshold=250.0, savings_rate=0.15, savings_cap_usd=500.0,
        enable_pair_bonus=True, pair_bonus_ratios={1: 0.15, 2: 0.10, 3: 0.05, 4: 0.05, 5: 0.05, 6: 0.05},
        pair_bonus_4th_usd_threshold=500.0, pair_bonus_5th_usd_threshold=1000.0,
        enable_leader_dividend=True, leader_dividend_threshold_pv=13334, leader_dividend_share_usd=500.0,
        leader_dividend_tiers={1: 2, 2: 4, 3: 6, 4: 8},
        enable_horizontal_leader=True, horizontal_leader_share_usd=250.0,
        horizontal_leader_tiers={1: 2, 2: 2, 3: 4, 4: 6},
        enable_opportunity_points=False,
    )


def test_build_binary_9layer_2144():
    ts = TreeShape("binary", 10, {0: 1, 1: 4, 2: 8, 3: 16, 4: 32, 5: 64, 6: 128, 7: 256, 8: 512, 9: 1024, 10: 99})
    g = Growth(9, 4, "round_robin", 4)
    r = Revenue(1500, 100, "4_color_cycle", ("红", "紫", "青绿", "蓝"))
    s = build_scenario(ts, g, r, _default_config(), name="test_2fork")
    assert s.total_target == 2144
    assert s.total_months == 15
    assert s.total_weeks == 60


def test_build_four_way_6layer_2144():
    ts = TreeShape("four_way", 7, {0: 1, 1: 4, 2: 16, 3: 64, 4: 256, 5: 1024, 6: 779})
    g = Growth(9, 4, "round_robin", 4)
    r = Revenue(1500, 100, "4_color_cycle", ("红", "紫", "青绿", "蓝"))
    s = build_scenario(ts, g, r, _default_config(), name="test_4fork")
    assert s.total_target == 2144


def test_build_eight_way_4layer_2144():
    ts = TreeShape("eight_way", 5, {0: 1, 1: 8, 2: 64, 3: 512, 4: 1559})
    g = Growth(9, 4, "round_robin", 4)
    r = Revenue(1500, 100, "4_color_cycle", ("红", "紫", "青绿", "蓝"))
    s = build_scenario(ts, g, r, _default_config(), name="test_8fork")
    assert s.total_target == 2144
