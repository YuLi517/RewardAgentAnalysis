"""PR3 Task 2: migrate_add_scenarios_table 测试 (idempotent 创表)"""
import os
import tempfile
from sqlalchemy import create_engine, inspect, text

from tools.migrate_add_scenarios_table import upgrade


def test_upgrade_idempotent():
    """升级: 创建 scenarios 表; 重复调用不报错"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = None
    try:
        engine = create_engine(f"sqlite:///{path}")
        upgrade(engine)  # 第一次: 创表
        upgrade(engine)  # 第二次: 跳过 (表已存在)
        # 验证表存在
        insp = inspect(engine)
        tables = insp.get_table_names()
        assert "scenarios" in tables
        # 验证 40 列
        cols = insp.get_columns("scenarios")
        assert len(cols) == 40, f"应 40 列, 实际 {len(cols)}"
    finally:
        if engine:
            engine.dispose()
        try:
            os.unlink(path)
        except (PermissionError, OSError):
            pass  # Windows 文件锁


def test_upgrade_does_not_destroy_existing_data():
    """升级时, 如果表已有数据, 不能误删 (只跳过, 不 recreate)"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = None
    try:
        engine = create_engine(f"sqlite:///{path}")
        # 第一次: 创表 + 插一行
        upgrade(engine)
        with engine.begin() as conn:
            import json
            conn.execute(text(
                "INSERT INTO scenarios (name, created_at, tree_fork_type, tree_max_level, "
                "tree_layer_counts_json, growth_nodes_per_region_per_week, growth_n_regions, "
                "growth_join_strategy, growth_weeks_per_month, revenue_initial_pv, "
                "revenue_monthly_renew_pv, revenue_color_rule, revenue_color_names_json, "
                "cc_enable_retail_profit, cc_enable_team_bonus, cc_team_bonus_tier_rates_json, "
                "cc_team_bonus_window_weeks, cc_enable_own_basic, cc_own_basic_rate, "
                "cc_own_basic_line_pv_cap, cc_enable_savings, cc_savings_usd_threshold, "
                "cc_savings_rate, cc_savings_cap_usd, cc_enable_pair_bonus, "
                "cc_pair_bonus_ratios_json, cc_pair_bonus_4th_usd_threshold, "
                "cc_pair_bonus_5th_usd_threshold, cc_enable_leader_dividend, "
                "cc_leader_dividend_threshold_pv, cc_leader_dividend_share_usd, "
                "cc_leader_dividend_tiers_json, cc_enable_horizontal_leader, "
                "cc_horizontal_leader_share_usd, cc_horizontal_leader_tiers_json, "
                "cc_enable_opportunity_points, total_target, total_weeks, total_months) "
                "VALUES ('preexist', '2026-08-07T10:00:00', 'binary', 10, '{}', "
                "9, 4, 'round_robin', 4, 1500, 100, '4_color_cycle', '[]', "
                "0, 1, '{}', 4, 1, 0.15, 13334, 1, 250.0, 0.15, 500.0, 1, '{}', "
                "500.0, 1000.0, 1, 13334, 500.0, '{}', 1, 250.0, '{}', 0, 2144, 60, 15)"
            ))
        # 第二次: 跳过, 数据还在
        upgrade(engine)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT name FROM scenarios WHERE name = 'preexist'"))
            assert result.fetchone() is not None, "upgrade() 第二次调用不应删除数据"
    finally:
        if engine:
            engine.dispose()
        try:
            os.unlink(path)
        except (PermissionError, OSError):
            pass
