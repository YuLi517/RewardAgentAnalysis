"""P1.5 Task 5: 性能基准测试

业务:
- 测试 1: 14 月 × 8 报酬 矩阵 ≤ 10s
- 测试 2: 2 次查询 (有缓存) ≤ 100ms
- 测试 3: 4 scenario 对比 ≤ 30s (P3 PR3 场景)

注: 跑性能测试前先清缓存
"""
import time
import pytest
from scenario.builder import build_scenario
from scenario.model import TreeShape, Growth, Revenue, CommissionConfig
from scenario.parallel import compute_overview_all_parallel
from scenario.breakdown import clear_caches
from scenario.commission._helpers import clear_all_caches


def make_scenario(scenario_id=None):
    """构 2144 节点 scenario (跟 P3 PR1 默认值一致)"""
    tree = TreeShape(fork_type="binary", max_level=10, layer_counts={
        0: 1, 1: 4, 2: 8, 3: 16, 4: 32, 5: 64, 6: 128, 7: 256, 8: 512, 9: 1024, 10: 99
    })
    growth = Growth(nodes_per_region_per_week=9, n_regions=4, join_strategy="round_robin", weeks_per_month=4)
    revenue = Revenue(initial_pv=1500, monthly_renew_pv=100, color_rule="round_robin",
                     color_names=("绿", "黄", "蓝", "紫"))
    cc = CommissionConfig(
        enable_retail_profit=True, enable_team_bonus=True,
        team_bonus_tier_rates={200: 0.15, 500: 0.20, 1000: 0.25, 1500: 0.30},
        team_bonus_window_weeks=4, enable_own_basic=True, own_basic_rate=0.15,
        own_basic_line_pv_cap=13334, enable_savings=True, savings_usd_threshold=500,
        savings_rate=0.10, savings_cap_usd=2000, enable_pair_bonus=True,
        pair_bonus_ratios={1: 0.15, 2: 0.10, 3: 0.05, 4: 0.05, 5: 0.05, 6: 0.05, 7: 0.05},
        pair_bonus_4th_usd_threshold=2000, pair_bonus_5th_usd_threshold=2000,
        enable_leader_dividend=True, leader_dividend_threshold_pv=50000,
        leader_dividend_share_usd=1000, leader_dividend_tiers={1: 10, 2: 8, 3: 6},
        enable_horizontal_leader=True, horizontal_leader_share_usd=500,
        horizontal_leader_tiers={1: 8, 2: 6, 3: 4}, enable_opportunity_points=True
    )
    return build_scenario(tree, growth, revenue, cc, name=f"perf_test_{scenario_id or 0}")


@pytest.fixture(autouse=True)
def clear_caches_fixture():
    clear_caches()
    clear_all_caches()
    yield
    clear_caches()
    clear_all_caches()


def test_overview_all_14_months_under_10s():
    """测试 1: 14 月 × 8 报酬 矩阵 ≤ 10s (P1.5 核心指标)"""
    s = make_scenario(1)
    t0 = time.time()
    matrix = compute_overview_all_parallel(s, total_months=14)
    elapsed = time.time() - t0
    assert elapsed < 10.0, f"14 月应 ≤ 10s, 实际 {elapsed:.2f}s"
    assert len(matrix["months"]) == 15
    assert len(matrix["fields"]) == 8
    # 跟 PR2 route 返的 4 字段接口一致: matrix["matrix"][f][m]
    assert all(matrix["matrix"][f][m] is not None for f in matrix["fields"] for m in matrix["months"])


def test_overview_all_2nd_call_under_100ms():
    """测试 2: 2 次查询 (有缓存) ≤ 100ms (LRU 验证)"""
    s = make_scenario(2)
    compute_overview_all_parallel(s, total_months=14)  # 第 1 次
    t0 = time.time()
    matrix = compute_overview_all_parallel(s, total_months=14)  # 第 2 次, LRU 命中
    elapsed = time.time() - t0
    assert elapsed < 0.1, f"2 次查询应 ≤ 100ms, 实际 {elapsed:.2f}s"


def test_overview_all_4_scenarios_under_30s():
    """测试 3: 4 scenario 对比 ≤ 30s (P3 PR3 场景)"""
    scenarios = [make_scenario(i) for i in range(4)]
    t0 = time.time()
    for s in scenarios:
        compute_overview_all_parallel(s, total_months=14)
    elapsed = time.time() - t0
    assert elapsed < 30.0, f"4 scenario 应 ≤ 30s, 实际 {elapsed:.2f}s"
