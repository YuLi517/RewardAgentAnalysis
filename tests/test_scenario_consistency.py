"""数字一致性验证 (PR1 — 跟旧 tools/rebuild_2144_simulation.py 对比)
PR1 阶段: 仅验证 2 叉 9 层 1500PV 方案的 total_target=2144 + 节点数
PR4 阶段: 完整 8 种报酬 + 4 叉 + 1000PV 方案对比
"""
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


def test_binary_9layer_total_2144():
    """跟旧 build_bfs_tree() 跑出 2144 节点一致"""
    ts = TreeShape("binary", 10, {0: 1, 1: 4, 2: 8, 3: 16, 4: 32, 5: 64, 6: 128, 7: 256, 8: 512, 9: 1024, 10: 99})
    g = Growth(9, 4, "round_robin", 4)
    r = Revenue(1500, 100, "4_color_cycle", ("红", "紫", "青绿", "蓝"))
    s = build_scenario(ts, g, r, _default_config(), name="2fork_9layer_1500pv")
    assert s.total_target == 2144
    assert s.total_months == 15
    assert s.total_weeks == 60


def test_layer_counts_sum_equals_total():
    """各层节点数 sum = total_target"""
    layer_counts = {0: 1, 1: 4, 2: 8, 3: 16, 4: 32, 5: 64, 6: 128, 7: 256, 8: 512, 9: 1024, 10: 99}
    assert sum(layer_counts.values()) == 2144


def test_bfs_node_count_matches_layer_counts():
    """builder 构出来的节点数 == sum(layer_counts)"""
    from scenario.builder import _build_bfs_tree
    ts = TreeShape("binary", 10, {0: 1, 1: 4, 2: 8, 3: 16, 4: 32, 5: 64, 6: 128, 7: 256, 8: 512, 9: 1024, 10: 99})
    nodes = _build_bfs_tree(ts)
    assert len(nodes) == 2144
    # 按 level 分组, 验证每层节点数
    from collections import Counter
    level_counts = Counter(n["level"] for n in nodes.values())
    assert level_counts[0] == 1
    assert level_counts[1] == 4
    assert level_counts[2] == 8
    assert level_counts[10] == 99
