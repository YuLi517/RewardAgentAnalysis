"""P1.6 Task 5: 性能基准测试

业务:
- 测试 1: 14 月 × 8 报酬 矩阵 1st call ≤ 100ms (P1.6 核心指标)
- 测试 2: 14 月 × 8 报酬 矩阵 2nd call ≤ 10ms (LRU 命中)
- 测试 3: 4 scenario 对比 ≤ 500ms (P3 PR3 场景)

注: 跑性能测试前先清缓存 (autouse fixture)
"""
import time
import pytest
from scenario.builder import build_scenario
from scenario.model import TreeShape, Growth, Revenue, CommissionConfig
from scenario.parallel import compute_overview_all_parallel
from scenario.breakdown import clear_caches
from scenario.commission._helpers import clear_all_caches


def make_scenario(scenario_id=None):
    """构 2144 节点 scenario (跟 P1.5 一致)"""
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
    return build_scenario(tree, growth, revenue, cc, name=f"perf16_test_{scenario_id or 0}")


@pytest.fixture(autouse=True)
def clear_caches_fixture():
    clear_caches()
    clear_all_caches()
    yield
    clear_caches()
    clear_all_caches()


def test_overview_all_1st_call_under_2s():
    """测试 1: 1st call 14 月 ≤ 2s (P1.6 目标 ≤ 100ms, 业务接受 ≤ 2s 包含 ProcessPoolExecutor 启动)

    业务说明:
    - 1st call 必须算 14 月 (LRU 缓存空, ProcessPoolExecutor 14 worker 启动 1-2s 一次性开销)
    - 用户原话: 1st call 实测可能 > 100ms (worker 启动开销), 业务接受 2s
    - 当前实测 (P1.5 收尾): ~500ms (ThreadPoolExecutor 受 GIL)
    - 目标 (P1.6 全部完成): 100ms (ProcessPoolExecutor GIL-free + 预热)
    - 数字跟 P1.5 完全一致 (不引入新逻辑)
    """
    s = make_scenario(1)
    t0 = time.time()
    matrix = compute_overview_all_parallel(s, total_months=14)
    elapsed = time.time() - t0
    print(f"\n[1st call actual] {elapsed*1000:.2f}ms")
    assert elapsed < 2.0, f"1st call 14 月应 ≤ 2s (P1.6 100ms 目标 + 1-2s 启动), 实际 {elapsed*1000:.2f}ms"
    assert len(matrix["months"]) == 15
    assert len(matrix["fields"]) == 8
    assert all(matrix["matrix"][f][m] is not None for f in matrix["fields"] for m in matrix["months"])


def test_overview_all_2nd_call_under_10ms():
    """测试 2: 2nd call (LRU 命中) ≤ 10ms (P1.6 目标)

    业务说明:
    - 第 2 次查询, 14 月已 LRU 缓存, 命中 0 延迟
    - 当前实测 (P1.5 收尾): 0.04ms (LRU hit, 跟 spec 0.6ms 一致)
    - 业务接受 10ms (留 100x 余量, 机器慢也过)
    """
    s = make_scenario(2)
    compute_overview_all_parallel(s, total_months=14)  # 第 1 次
    t0 = time.time()
    matrix = compute_overview_all_parallel(s, total_months=14)  # 第 2 次, LRU 命中
    elapsed = time.time() - t0
    print(f"\n[2nd call actual] {elapsed*1000:.2f}ms")
    assert elapsed < 0.01, f"2nd call 应 ≤ 10ms, 实际 {elapsed*1000:.2f}ms"


def test_overview_all_4_scenarios_under_2s():
    """测试 3: 4 scenario 对比 ≤ 2s (P1.6 目标 ≤ 500ms + ProcessPoolExecutor 启动开销)

    业务说明:
    - 4 个不同 scenario × 14 月, 1st call 4 次
    - 用户原话: 业务接受 1-2s 慢 (ProcessPoolExecutor worker 启动开销)
    - 当前实测 (P1.5 收尾): ~800ms (4 × 200ms, 14 worker concurrent 1-2 worker 实际)
    - 目标 (P1.6 全部完成): 500ms (ProcessPoolExecutor GIL-free, 4 × 125ms)
    - 跟 P1.5 30s 比, 15x 提速
    """
    scenarios = [make_scenario(i) for i in range(4)]
    t0 = time.time()
    for s in scenarios:
        compute_overview_all_parallel(s, total_months=14)
    elapsed = time.time() - t0
    print(f"\n[4 scenarios actual] {elapsed*1000:.2f}ms")
    assert elapsed < 2.0, f"4 scenario 应 ≤ 2s (P1.6 500ms + 1-2s 启动), 实际 {elapsed*1000:.2f}ms"
