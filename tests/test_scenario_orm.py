"""PR3 Task 1: Scenario ORM 验证 (40 列 + 不破坏旧表)"""
import os
import tempfile
from sqlalchemy import create_engine, inspect

from models import Base, Scenario, OrderItem, Member


def test_scenario_orm_40_columns():
    """验证 Scenario ORM 有 40 列"""
    cols = [c.name for c in Scenario.__table__.columns]
    assert len(cols) == 40, f"Scenario 应有 40 列, 实际 {len(cols)}"
    # 关键列存在
    for must in ["id", "name", "created_at", "tree_fork_type", "tree_max_level",
                 "cc_enable_own_basic", "cc_own_basic_rate",
                 "total_target", "total_weeks", "total_months"]:
        assert must in cols, f"缺少关键列: {must}"


def test_scenario_create_table_no_regression():
    """创表: scenarios + 6 旧表全部成功 (不破坏其他 ORM)"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = None
    try:
        engine = create_engine(f"sqlite:///{path}")
        Base.metadata.create_all(engine)
        insp = inspect(engine)
        tables = sorted(insp.get_table_names())
        # 7 张表都创建
        for must in ["scenarios", "order_items", "members", "messages",
                     "sessions", "pv_ledger", "commission_periods"]:
            assert must in tables, f"缺少表: {must}"
        # scenarios 40 列
        sc_cols = [c["name"] for c in insp.get_columns("scenarios")]
        assert len(sc_cols) == 40
    finally:
        if engine:
            engine.dispose()
        try:
            os.unlink(path)
        except (PermissionError, OSError):
            pass  # Windows 文件锁, 忽略


def test_scenario_to_dict_roundtrip():
    """验证 to_dict() 能反序列化 JSON 字段 (模拟 read 路径)"""
    import json
    # 直接构造 ORM 实例 (绕开 save, 只测 to_dict)
    sc = Scenario(
        id=1, name="test", created_at="2026-08-07T10:00:00",
        tree_fork_type="binary", tree_max_level=10,
        tree_layer_counts_json=json.dumps({0: 1, 1: 4, 2: 8}),
        growth_nodes_per_region_per_week=9, growth_n_regions=4,
        growth_join_strategy="round_robin", growth_weeks_per_month=4,
        revenue_initial_pv=1500, revenue_monthly_renew_pv=100,
        revenue_color_rule="4_color_cycle",
        revenue_color_names_json=json.dumps(["红", "紫", "青绿", "蓝"]),
        cc_enable_retail_profit=False, cc_enable_team_bonus=True,
        cc_team_bonus_tier_rates_json=json.dumps({200: 0.15, 500: 0.20}),
        cc_team_bonus_window_weeks=4,
        cc_enable_own_basic=True, cc_own_basic_rate=0.15,
        cc_own_basic_line_pv_cap=13334,
        cc_enable_savings=True, cc_savings_usd_threshold=250.0,
        cc_savings_rate=0.15, cc_savings_cap_usd=500.0,
        cc_enable_pair_bonus=True,
        cc_pair_bonus_ratios_json=json.dumps({1: 0.15, 2: 0.10}),
        cc_pair_bonus_4th_usd_threshold=500.0, cc_pair_bonus_5th_usd_threshold=1000.0,
        cc_enable_leader_dividend=True, cc_leader_dividend_threshold_pv=13334,
        cc_leader_dividend_share_usd=500.0,
        cc_leader_dividend_tiers_json=json.dumps({1: 2}),
        cc_enable_horizontal_leader=True, cc_horizontal_leader_share_usd=250.0,
        cc_horizontal_leader_tiers_json=json.dumps({1: 2}),
        cc_enable_opportunity_points=False,
        total_target=2144, total_weeks=60, total_months=15,
    )
    d = sc.to_dict()
    assert d["name"] == "test"
    assert d["tree_shape"]["fork_type"] == "binary"
    assert d["tree_shape"]["layer_counts"] == {0: 1, 1: 4, 2: 8}
    assert d["revenue"]["color_names"] == ["红", "紫", "青绿", "蓝"]
    assert d["commission_config"]["team_bonus_tier_rates"] == {200: 0.15, 500: 0.20}
    assert d["commission_config"]["pair_bonus_ratios"] == {1: 0.15, 2: 0.10}
    assert d["total_target"] == 2144
