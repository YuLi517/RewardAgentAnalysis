"""scenario PV 计算测试 (PR1 Task 3)"""
from scenario.builder import build_scenario
from scenario.model import TreeShape, Growth, Revenue, CommissionConfig
from decimal import Decimal
from scenario._pv import compute_monthly_pv, compute_weekly_period_pv


def _build_test_scenario():
    ts = TreeShape("binary", 3, {0: 1, 1: 4, 2: 8, 3: 1})  # 1+4+8+1=14
    g = Growth(9, 4, "round_robin", 4)
    r = Revenue(1500, 100, "4_color_cycle", ("红", "紫", "青绿", "蓝"))
    cc = CommissionConfig(False, False, {}, 4, False, Decimal("0.15"), 13334, False, 250.0, 0.15, 500.0, False, {}, 500.0, 1000.0, False, 13334, 500.0, {}, False, 250.0, {}, False)
    return build_scenario(ts, g, r, cc, name="test_pv")


def test_monthly_pv_join_month_for_l3_node():
    s = _build_test_scenario()
    # L3 节点 bfs_id=13 (L0=0, L1=1-4, L2=5-12, L3=13)
    monthly_pv, _ = compute_monthly_pv(s, total_months=3)
    # L3 节点 join_month=0 (默认), 所以 month=0 cumulative=1500
    assert monthly_pv[0].get(13, 0) == 1500
    # month=1 L3 没续费 (color 红, 月 1 是紫, 不续费)
    assert monthly_pv[1].get(13, 0) == 1500
    # month=2 是青绿, 也不续费
    assert monthly_pv[2].get(13, 0) == 1500


def test_weekly_period_pv_l3_only_first_week():
    s = _build_test_scenario()
    weekly_pv, weekly_period_pv = compute_weekly_period_pv(s, total_weeks=8)
    # L3 节点 join_week=0, 加入周 1500PV (period)
    assert weekly_period_pv[0].get(13, 0) == 1500
    # week 1-3 期间 period_pv=0 (没续费)
    assert weekly_period_pv[1].get(13, 0) == 0
    assert weekly_period_pv[3].get(13, 0) == 0
    # weekly_pv 是累计: week 0 之后都是 1500
    assert weekly_pv[0].get(13, 0) == 1500
    assert weekly_pv[1].get(13, 0) == 1500  # 累计不变
    assert weekly_pv[3].get(13, 0) == 1500  # 累计不变


def test_l0_l1_l2_excluded_from_pv():
    s = _build_test_scenario()
    monthly_pv, _ = compute_monthly_pv(s, total_months=2)
    # L0/L1/L2 永远不参与 PV (旧模拟器逻辑)
    for bfs in [0, 1, 2, 3, 4, 5, 12]:
        assert monthly_pv[0].get(bfs, 0) == 0
        assert monthly_pv[1].get(bfs, 0) == 0
