"""业务场景报表生成器 (P6, 替代旧 tools/rebuild_2144_simulation.py)
调 scenario/ 库, 跑 15 月报表, 跟旧 _final_output_v3.txt 严格一致.

业务定位 (大重构 P1 阶段 P6 收官):
- 4 套方案: 2 叉 9 层 / 4 叉 6 层 / 8 叉 4 层 (3 种 1500PV) + 2 叉 9 层 1000PV
- 跑 15 月, 累加 Root 6 种报酬 (ownBasic/pairBonus/teamBonus/savings/leader/horizontal)
- 跟旧 _final_output_v3.txt Root 15 月累计数字严格 0 差异
"""
from __future__ import annotations
import sys
import io
from decimal import Decimal
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

from scenario.builder import build_scenario
from scenario.model import TreeShape, Growth, Revenue, CommissionConfig
from scenario.breakdown import compute_commission_breakdown


def _default_config() -> CommissionConfig:
    """P1 PR4 默认配置 (跟旧 _final_output_v3.txt 一致)"""
    return CommissionConfig(
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


def build_2fork_9layer(initial_pv: int = 1500) -> "Scenario":
    """2 叉 9 层 99 节点 (L10 部分填充), 总 2144 节点
    业务: 4 大区 × 9 周/大区 = 36 节点/周, 60 周完成
    """
    ts = TreeShape("binary", 10, {0: 1, 1: 4, 2: 8, 3: 16, 4: 32, 5: 64, 6: 128, 7: 256, 8: 512, 9: 1024, 10: 99})
    g = Growth(9, 4, "round_robin", 4)
    r = Revenue(initial_pv, 100, "4_color_cycle", ("红", "紫", "青绿", "蓝"))
    return build_scenario(ts, g, r, _default_config(), name=f"2fork_9layer_{initial_pv}pv")


def build_4fork_6layer(initial_pv: int = 1500) -> "Scenario":
    """4 叉 6 层 779 节点 (L6 部分填充), 总 2144 节点
    业务: 4 大区 × 16 周/大区 = 64 节点/周, 33 周完成
    """
    ts = TreeShape("four_way", 7, {0: 1, 1: 4, 2: 16, 3: 64, 4: 256, 5: 1024, 6: 779})
    g = Growth(9, 4, "round_robin", 4)
    r = Revenue(initial_pv, 100, "4_color_cycle", ("红", "紫", "青绿", "蓝"))
    return build_scenario(ts, g, r, _default_config(), name=f"4fork_6layer_{initial_pv}pv")


def build_8fork_4layer(initial_pv: int = 1500) -> "Scenario":
    """8 叉 4 层 1559 节点 (L4 部分填充), 总 2144 节点
    业务: 4 大区 × 64 周/大区 = 256 节点/周, 8 周完成
    """
    ts = TreeShape("eight_way", 5, {0: 1, 1: 8, 2: 64, 3: 512, 4: 1559})
    g = Growth(9, 4, "round_robin", 4)
    r = Revenue(initial_pv, 100, "4_color_cycle", ("红", "紫", "青绿", "蓝"))
    return build_scenario(ts, g, r, _default_config(), name=f"8fork_4layer_{initial_pv}pv")


def report_root_cumulative(scenario, name: str, total_months: int = 15):
    """跑 total_months 月, 累加 Root 8 种报酬

    Returns:
        dict {total, ownBasic, pairBonus, teamBonus, savings, leader, horizontal}
    """
    root_total = Decimal("0")
    root_breakdown = defaultdict(lambda: Decimal("0"))
    for m in range(total_months):
        cb = compute_commission_breakdown(scenario, bfs_id=0, month=m)
        root_total += cb.total_usd
        root_breakdown["ownBasic"] += cb.own_basic_usd
        root_breakdown["pairBonus"] += cb.pair_bonus_usd
        root_breakdown["teamBonus"] += cb.team_bonus_usd
        root_breakdown["savings"] += cb.savings_usd
        root_breakdown["leader"] += cb.leader_dividend_usd
        root_breakdown["horizontal"] += cb.horizontal_leader_usd
    print(f"\n[{name}] Root {total_months} 月累计: ${root_total:,.2f}")
    print(f"  ownBasic:    ${root_breakdown['ownBasic']:>12,.2f}")
    print(f"  pairBonus:   ${root_breakdown['pairBonus']:>12,.2f}")
    print(f"  teamBonus:   ${root_breakdown['teamBonus']:>12,.2f}")
    print(f"  savings:     ${root_breakdown['savings']:>12,.2f}")
    print(f"  leader:      ${root_breakdown['leader']:>12,.2f}")
    print(f"  horizontal:  ${root_breakdown['horizontal']:>12,.2f}")
    return {
        "total": root_total,
        "ownBasic": root_breakdown["ownBasic"],
        "pairBonus": root_breakdown["pairBonus"],
        "teamBonus": root_breakdown["teamBonus"],
        "savings": root_breakdown["savings"],
        "leader": root_breakdown["leader"],
        "horizontal": root_breakdown["horizontal"],
    }


def main():
    print("=" * 78)
    print("P6 业务场景报表 (调 scenario/ 引擎, 跟旧 _final_output_v3.txt 对比)")
    print("=" * 78)

    # 2 叉 9 层 1500PV (主对照方案, 跟旧 _final_output_v3.txt Root = $1,024,983.26)
    s_2fork = build_2fork_9layer(1500)
    r2 = report_root_cumulative(s_2fork, "2fork_9layer_1500PV", total_months=15)

    # 4 叉 6 层 1500PV
    s_4fork = build_4fork_6layer(1500)
    r4 = report_root_cumulative(s_4fork, "4fork_6layer_1500PV", total_months=15)

    # 8 叉 4 层 1500PV (新方案, 旧没跑)
    s_8fork = build_8fork_4layer(1500)
    r8 = report_root_cumulative(s_8fork, "8fork_4layer_1500PV", total_months=15)

    # 2 叉 9 层 1000PV
    s_2fork_1000 = build_2fork_9layer(1000)
    r2_1000 = report_root_cumulative(s_2fork_1000, "2fork_9layer_1000PV", total_months=15)


if __name__ == "__main__":
    main()
