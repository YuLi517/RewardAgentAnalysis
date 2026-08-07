"""PR2 数字一致性验证: 2 叉 9 层 1500PV Root 15 月累计
PR2 阶段 own_basic 已实现, 7 种函数 stub 返 0
- 期望: Root 15 月 ownBasic 累计 = 旧 $30,001.50
- 其他 7 种都是 0 (stub)
- 总 commission = $30,001.50 (跟旧 Root 总 $1,024,983 差 $994,981.50 是因为 7 种 stub)

PR2 收尾 (后续 task 2-7) 实现 7 种函数后, Root 累计应等于 $1,024,983.26
"""
from decimal import Decimal
from scenario.builder import build_scenario
from scenario.model import TreeShape, Growth, Revenue, CommissionConfig
from scenario.breakdown import compute_commission_breakdown
from scenario.overview import compute_month_overview


def _build_2fork_9layer():
    ts = TreeShape("binary", 10, {0: 1, 1: 4, 2: 8, 3: 16, 4: 32, 5: 64, 6: 128, 7: 256, 8: 512, 9: 1024, 10: 99})
    g = Growth(9, 4, "round_robin", 4)
    r = Revenue(1500, 100, "4_color_cycle", ("红", "紫", "青绿", "蓝"))
    cc = CommissionConfig(
        enable_retail_profit=False, enable_team_bonus=True,
        team_bonus_tier_rates={200: 0.15, 500: 0.20, 1000: 0.25, 1500: 0.30},
        team_bonus_window_weeks=4,
        enable_own_basic=True, own_basic_rate=Decimal("0.15"), own_basic_line_pv_cap=13334,
        enable_savings=True, savings_usd_threshold=250.0, savings_rate=0.15, savings_cap_usd=500.0,
        enable_pair_bonus=True, pair_bonus_ratios={1: 0.15, 2: 0.10, 3: 0.05, 4: 0.05, 5: 0.05, 6: 0.05},
        pair_bonus_4th_usd_threshold=500.0, pair_bonus_5th_usd_threshold=1000.0,
        enable_leader_dividend=True, leader_dividend_threshold_pv=13334, leader_dividend_share_usd=500.0,
        leader_dividend_tiers={1: 2, 2: 4, 3: 6, 4: 8},
        enable_horizontal_leader=True, horizontal_leader_share_usd=250.0,
        horizontal_leader_tiers={1: 2, 2: 2, 3: 4, 4: 6},
        enable_opportunity_points=False,
    )
    return build_scenario(ts, g, r, cc, name="2fork_9layer_1500pv")


def test_root_own_basic_cumulative():
    """PR2 阶段 Root 15 月 ownBasic 累计应等于旧 $30,001.50
    (其他 7 种 stub 返 0, 不影响 own_basic 验证)
    """
    s = _build_2fork_9layer()
    cumulative = Decimal("0")
    for m in range(15):
        cb = compute_commission_breakdown(s, bfs_id=0, month=m)
        cumulative += cb.own_basic_usd
    expected = Decimal("30001.50")
    diff = abs(cumulative - expected)
    assert diff < Decimal("0.01"), f"Root 15 月 ownBasic 累计 {cumulative} 跟期望 {expected} 差 {diff}"


def test_root_other_commission_stub_zero():
    """PR2 阶段 7 种 stub 函数都返 0, 累计应该全是 0"""
    s = _build_2fork_9layer()
    for m in range(15):
        cb = compute_commission_breakdown(s, bfs_id=0, month=m)
        assert cb.pair_bonus_usd == Decimal("0")
        assert cb.team_bonus_usd == Decimal("0")
        assert cb.savings_usd == Decimal("0")
        assert cb.leader_dividend_usd == Decimal("0")
        assert cb.horizontal_leader_usd == Decimal("0")
        assert cb.retail_profit_usd == Decimal("0")
        assert cb.opportunity_points == 0


def test_root_total_equals_own_basic_now():
    """PR2 阶段 Root total = ownBasic (其他 7 种都 stub 0)"""
    s = _build_2fork_9layer()
    cumulative_total = Decimal("0")
    for m in range(15):
        cb = compute_commission_breakdown(s, bfs_id=0, month=m)
        cumulative_total += cb.total_usd
    # 期望等于 ownBasic 累计 ($30,001.50)
    assert abs(cumulative_total - Decimal("30001.50")) < Decimal("0.01")


def test_root_breakdown_structure():
    """breakdown 12 字段结构验证"""
    s = _build_2fork_9layer()
    cb = compute_commission_breakdown(s, bfs_id=0, month=0)
    assert cb.bfs_id == 0
    assert cb.month == 0
    assert isinstance(cb.own_basic_usd, Decimal)
    assert isinstance(cb.pair_bonus_usd, Decimal)
    assert isinstance(cb.team_bonus_usd, Decimal)
    assert isinstance(cb.savings_usd, Decimal)
    assert isinstance(cb.leader_dividend_usd, Decimal)
    assert isinstance(cb.horizontal_leader_usd, Decimal)
    assert isinstance(cb.retail_profit_usd, Decimal)
    assert isinstance(cb.opportunity_points, int)
    assert isinstance(cb.total_usd, Decimal)
    assert isinstance(cb.ip_chain_status, list)
    assert isinstance(cb.is_optimized_region, bool)
    assert isinstance(cb.cumulative_to_date_usd, Decimal)


def test_overview_aggregates_all_nodes():
    """overview 跑全网节点累计 (含 ownBasic 非 0 节点 + stub 0 节点)"""
    s = _build_2fork_9layer()
    overview = compute_month_overview(s, month=14)
    assert "ownBasic" in overview
    assert "pairBonus" in overview
    assert "teamBonus" in overview
    assert "savings" in overview
    assert "leader" in overview
    assert "horizontal" in overview
    assert "retail" in overview
    assert "total" in overview
    # ownBasic 全网累计 > Root ownBasic (其他节点也有 ownBasic)
    assert overview["ownBasic"] > Decimal("0")
    # 其他 7 种都是 0 (stub)
    assert overview["pairBonus"] == Decimal("0")
    assert overview["teamBonus"] == Decimal("0")
    assert overview["savings"] == Decimal("0")
    assert overview["leader"] == Decimal("0")
    assert overview["horizontal"] == Decimal("0")
    assert overview["retail"] == Decimal("0")
    assert overview["total"] == overview["ownBasic"]  # PR2 阶段
