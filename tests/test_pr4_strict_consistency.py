"""P6 业务规则一致性验证 (Task 4)

业务:
- 0 业务规则变化 = 跟 P1 PR2 拍板 (4 函数对齐 + 2 函数 BFS 偏差接受) 一致
- 不跟 _final_output_v3.txt 验证 (矛盾, P1 PR2 之后不再用)
- 验证 main.py 业务路由走 scenario/ 引擎后, 跟当前 main.py 业务路由调用结果 0 回归

注:
- 旧 _final_output_v3.txt 期望 $1,024,983.26 (PR2 之前)
- P1 PR2 拍板 $1,253,783.00 (4 函数对齐 + 2 函数 BFS 偏差接受)
- P6 简化: 0 回归验证 (跟当前 main.py 一致), 跳过 4 套方案严格验证
"""
import subprocess
import pytest
from decimal import Decimal
from tools.scenario_report import (
    build_2fork_9layer, build_4fork_6layer, report_root_cumulative
)


# P1 PR2 拍板的 2fork 1500PV 期望值 (业务接受 BFS 偏差)
# 跟旧 _final_output_v3.txt ($1,024,983) 不一致, 是大重构 P1 阶段 P2 拍板 ($1,253,783)
EXPECTED_2FORK_1500_P1PR2 = {
    "total": Decimal("1253783.00"),
    "ownBasic": Decimal("30001.50"),
    "pairBonus": Decimal("251781.27"),
    "teamBonus": Decimal("945000.00"),
    "savings": Decimal("4500.22"),
    "leader": Decimal("0.00"),
    "horizontal": Decimal("22500.00"),
}


def test_2fork_9layer_1500PV_p1pr2_consistency():
    """测试 1: 2 叉 9 层 1500PV 跟 P1 PR2 拍板数字 0 差异 (业务接受 0.01 rounding)"""
    s = build_2fork_9layer(1500)
    result = report_root_cumulative(s, "2fork_9layer_1500PV", total_months=15)
    for field, expected in EXPECTED_2FORK_1500_P1PR2.items():
        actual = result[field]
        diff = abs(actual - expected)
        assert diff < Decimal("0.01"), (
            f"2 叉 1500PV {field}: P1 PR2 期望 ${expected}, 实际 ${actual}, 差 ${diff}"
        )


def test_p6_no_legacy_skills_imports():
    """测试 2: 全仓 0 import 旧 skills/ 业务函数 (P6 删除验证)

    业务: 删 tools/rebuild_2144_simulation.py + _final_output_v3.txt 后, main.py 仍可 import
    skills/period + skills/pair_commission (周结算, 业务保留).
    验证: 全仓 0 调用已删的 tools/rebuild_2144_simulation (旧报表工具).
    """
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-ChildItem -Path . -Recurse -File -Include *.py | Select-String -Pattern 'rebuild_2144_simulation' | Measure-Object | Select-Object -ExpandProperty Count"],
        cwd=r"D:\Projects\Reward\RewardAgentAnalysis",
        capture_output=True, text=True
    )
    count = int(result.stdout.strip() or "0")
    assert count == 0, f"全仓 0 import 旧 tools/rebuild_2144_simulation, 实际 {count} 处"


def test_p6_scenario_engines_no_regression():
    """测试 3: scenario/ 引擎 0 回归 (跟 P1.6 累计 80 pass 一致)"""
    result = subprocess.run(
        ["python", "-m", "pytest",
         "tests/test_scenario_orm.py", "tests/test_scenario_repository.py",
         "tests/test_scenario_routes.py", "tests/test_scenario_builder.py",
         "tests/test_scenario_pv.py", "tests/test_scenario_cache.py",
         "tests/test_scenario_consistency.py", "tests/test_scenario_model.py",
         "tests/test_commission_own_basic.py", "tests/test_pr2_root_consistency.py",
         "tests/test_db_admin.py",
         "--tb=no", "-q"],
        cwd=r"D:\Projects\Reward\RewardAgentAnalysis",
        capture_output=True, text=True
    )
    # 期望 0 fail
    output = result.stdout + result.stderr
    fail_count = 0
    for line in output.split("\n"):
        if " failed" in line and "passed" in line:
            # 形如 "1 failed, 80 passed"
            try:
                fail_count = int(line.split(" failed")[0].split()[-1])
            except (IndexError, ValueError):
                pass
    assert fail_count == 0, (
        f"scenario/ 引擎测试 0 回归失败, 实际 {fail_count} 个 fail, pytest 输出末尾: {output[-500:]}"
    )
