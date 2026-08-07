# P6 旧运营兼容层 — Design Spec (P1 PR4 实施)

**Goal:** 把 main.py 业务路由切到 scenario/ 引擎, 删旧 `tools/rebuild_2144_simulation.py` 和旧 `skills/` 业务函数, 跑**严格**数字一致性验证 (跟旧 `_final_output_v3.txt` 0 差异). 大重构 P1 阶段 最后一项收官.

**Architecture:** 1 PR 完成 3 件事:
1. 改 main.py 业务路由走 `scenario/breakdown.compute_commission_breakdown` (替代 `skills/pair_commission._settle_node`)
2. 删旧 `tools/rebuild_2144_simulation.py` + `skills/pair_commission.py` + `skills/skill_5_lib.py` + `skills/period.py`
3. 跑全量对比 (2 叉/4 叉/8 叉/1000PV) 跟旧模拟器数字严格一致

**Tech Stack:** pytest + subprocess, 0 新依赖.

**Spec 父**: `docs/superpowers/specs/2026-08-07-p1-scenario-engine-design.md` §4.4 + 退出标准 §5.3
**Plan 父**: `docs/superpowers/plans/2026-08-07-p1-pr4-migration-verify.md` (P1 PR4 plan, 17KB, 跟 P6 范围一致)

---

## 1. 业务定位

```
作为 招商/路演运营
我想 旧业务路由 (commission preview, settle_period) 切到新 scenario/ 引擎
为了 旧前端仍能工作, 但数字跟新前端一致, 0 业务规则变化
```

**核心问题**:
- main.py 业务路由 (commission preview / settle_period / tree view) 还走 `skills/pair_commission._settle_node`
- 旧 `tools/rebuild_2144_simulation.py` 跟 `scenario/ 引擎` 双轨
- 旧 `skills/pair_commission.py` 是 P1 PR1 之前的代码, 业务规则跟新 scenario/ 引擎一致, 但代码重复
- 旧前端 (index.html) 走 main.py 业务路由, 跟 scenario/ 引擎独立

**核心价值**:
- 删旧 4 文件 (`tools/rebuild_2144_simulation.py` + 3 skills/ 文件), 代码减重 30%+
- main.py 业务路由切到 scenario/ 引擎, 复用 P1.5+P1.6 性能优化 (1st call 0-200ms)
- 0 业务规则变化 (数字跟旧 _final_output_v3.txt 严格 0 差异)
- 大重构 P1 阶段 100% 收官

## 2. 范围 (In/Out)

### In Scope (P6, 1.5-2 天, 5-6 commit)
- main.py 业务路由改走 scenario/ 引擎
- 写 `tools/scenario_report.py` (新报表工具, 替代旧 rebuild_2144_simulation.py)
- 写 `tools/_verify_p1_pr4_consistency.py` (全量对比脚本, 2 叉/4 叉/8 叉/1000PV)
- 写 `tests/test_pr4_strict_consistency.py` (严格数字一致性, 0 差异)
- 删旧 4 文件 (`tools/rebuild_2144_simulation.py` + `tools/_final_output_v3.txt` + 3 skills/ 文件)
- 跑全量对比, 数字严格 0 差异
- AGENTS.md §6.4 PR4 状态 + §5 业务规则更新

### Out of Scope
- main.py 业务路由 API 改路径 / 改参数 (保持完全兼容)
- 旧前端 index.html 改 (继续走 main.py, 业务路由内部换)
- scenario/ 引擎 API 改 (保持 P1 PR1 拍板一致)
- skills/ 其他工具函数 (skill_5_lib.py 是旧版, period.py 是 PR1 之前)
- 业务规则变化 (数字严格 0 差异, 0 业务规则变化)

## 3. 当前 main.py 业务路由 (P6 实施前)

| 业务路由 | 当前调用 | 改后调用 |
|---|---|---|
| `/api/commission-preview` | `skills/pair_commission._settle_node` | `scenario.breakdown.compute_commission_breakdown` |
| `/api/settle-period` | `skills/pair_commission._settle_period` | `scenario.breakdown.compute_commission_breakdown` 循环 |
| `/api/tree-view` | `main.py._build_tree_from_db` (旧) | `scenario.builder._build_bfs_tree` (新) |
| `/api/commission-cases` | `skills/period` | `scenario.overview.compute_month_overview` |

**核心原则**:
- API 路径不变, 参数不变, 返回值字段名不变
- 内部实现从 `skills/` 改到 `scenario/`
- 0 业务规则变化 (数字严格 0 差异)

## 4. 优化方案 (5 步骤)

### 4.1 备份当前状态 + 准备回滚点 (1 commit, 含在 Task 1)

**目标**: 备份 + 回滚点, 任何 0.01 差异都不合并.

```bash
git checkout -b backup-before-p6
git checkout main
cp data/rewarddb.db data/rewarddb.db.bak-before-p6-2026-08-07
```

### 4.2 写新 tools/scenario_report.py (1 commit)

**目标**: 替代旧 `tools/rebuild_2144_simulation.py`, 调 scenario/ 引擎出 Root 15 月累计.

**复 P1 PR4 plan §Task 2 完整 Step 1 + Step 2 模板**:
```python
"""业务场景报表生成器 (P6, 替代旧 tools/rebuild_2144_simulation.py)
调 scenario/ 库, 跑 15 月报表, 跟旧 _final_output_v3.txt 严格一致
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
from scenario.overview import compute_month_overview


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
    ts = TreeShape("binary", 10, {0: 1, 1: 4, 2: 8, 3: 16, 4: 32, 5: 64, 6: 128, 7: 256, 8: 512, 9: 1024, 10: 99})
    g = Growth(9, 4, "round_robin", 4)
    r = Revenue(initial_pv, 100, "4_color_cycle", ("红", "紫", "青绿", "蓝"))
    return build_scenario(ts, g, r, _default_config(), name=f"2fork_9layer_{initial_pv}pv")


def build_4fork_6layer(initial_pv: int = 1500) -> "Scenario":
    ts = TreeShape("four_way", 7, {0: 1, 1: 4, 2: 16, 3: 64, 4: 256, 5: 1024, 6: 779})
    g = Growth(9, 4, "round_robin", 4)
    r = Revenue(initial_pv, 100, "4_color_cycle", ("红", "紫", "青绿", "蓝"))
    return build_scenario(ts, g, r, _default_config(), name=f"4fork_6layer_{initial_pv}pv")


def build_8fork_4layer(initial_pv: int = 1500) -> "Scenario":
    ts = TreeShape("eight_way", 5, {0: 1, 1: 8, 2: 64, 3: 512, 4: 1559})
    g = Growth(9, 4, "round_robin", 4)
    r = Revenue(initial_pv, 100, "4_color_cycle", ("红", "紫", "青绿", "蓝"))
    return build_scenario(ts, g, r, _default_config(), name=f"8fork_4layer_{initial_pv}pv")


def report_root_cumulative(scenario, name: str, total_months: int = 15):
    """跑 total_months 月, 累加 Root 8 种报酬"""
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
    s_2fork = build_2fork_9layer(1500)
    r2 = report_root_cumulative(s_2fork, "2fork_9layer_1500PV", total_months=15)
    s_4fork = build_4fork_6layer(1500)
    r4 = report_root_cumulative(s_4fork, "4fork_6layer_1500PV", total_months=15)
    s_8fork = build_8fork_4layer(1500)
    r8 = report_root_cumulative(s_8fork, "8fork_4layer_1500PV", total_months=15)
    s_2fork_1000 = build_2fork_9layer(1000)
    r2_1000 = report_root_cumulative(s_2fork_1000, "2fork_9layer_1000PV", total_months=15)


if __name__ == "__main__":
    main()
```

### 4.3 main.py 业务路由改 scenario/ (1 commit)

**目标**: 4 个业务路由内部换实现, API 路径/参数/返回不变.

| 业务路由 | 改前 | 改后 |
|---|---|---|
| `/api/commission-preview` | `from skills.pair_commission import _settle_node` | `from scenario.breakdown import compute_commission_breakdown` |
| `/api/settle-period` | `_settle_node(scenario_id, month, bfs_id)` | `compute_commission_breakdown(scenario, bfs_id, month)` |
| `/api/tree-view` | `main.py._build_tree_from_db` (dict) | `scenario.builder._build_bfs_tree` (scenario.tree_shape) |
| `/api/commission-cases` | `from skills.period import ...` | `from scenario.overview import compute_month_overview` |

**核心原则**:
- API 路径不变 (`/api/commission-preview`, `/api/settle-period`, ...)
- 请求参数不变 (scenario_id / month / bfs_id)
- 返回值字段名不变 (own_basic / pair_bonus / total / ...)

### 4.4 删旧 4 文件 (1 commit)

**目标**: 删旧 skills/ 业务函数 + tools/rebuild_2144_simulation.py, 代码减重 30%+.

```bash
git rm skills/pair_commission.py
git rm skills/skill_5_lib.py
git rm skills/period.py
git rm tools/rebuild_2144_simulation.py
git rm tools/_final_output_v3.txt
```

**注意**:
- 删之前先 grep 全仓, 确认没别处 import 旧 skills/ 函数
- main.py 业务路由改完 + 测试通过, 才能删
- 删完跑全量测试, 0 回归

### 4.5 严格数字一致性验证 (1 commit)

**目标**: 写 `tests/test_pr4_strict_consistency.py`, 4 套方案跟旧 _final_output_v3.txt 0 差异.

**复 P1 PR4 plan §Task 7 模板**:
```python
"""P6 严格数字一致性验证

业务:
- 4 套方案: 2 叉 9 层 1500PV / 4 叉 6 层 1500PV / 8 叉 4 层 1500PV / 2 叉 9 层 1000PV
- 跟旧 tools/_final_output_v3.txt Root 15 月累计数字严格 0 差异
- 任何 0.01 偏差测试 fail
"""
import pytest
from decimal import Decimal
from tools.scenario_report import (
    build_2fork_9layer, build_4fork_6layer, build_8fork_4layer,
    report_root_cumulative
)


# 旧 _final_output_v3.txt 期望值 (从历史 PR 拍板)
EXPECTED_2FORK_1500 = {
    "total": Decimal("..."),  # 实际值从旧 _final_output_v3.txt 读
    "ownBasic": Decimal("..."),
    "pairBonus": Decimal("..."),
    "teamBonus": Decimal("..."),
    "savings": Decimal("..."),
    "leader": Decimal("..."),
    "horizontal": Decimal("..."),
}

EXPECTED_4FORK_1500 = {...}
EXPECTED_8FORK_1500 = {...}
EXPECTED_2FORK_1000 = {...}


def test_2fork_9layer_1500PV_strict_consistency():
    """测试 1: 2 叉 9 层 1500PV Root 15 月累计, 0 差异"""
    s = build_2fork_9layer(1500)
    result = report_root_cumulative(s, "2fork_9layer_1500PV", total_months=15)
    for field, expected in EXPECTED_2FORK_1500.items():
        actual = result[field]
        diff = abs(actual - expected)
        assert diff < Decimal("0.01"), f"2 叉 1500PV {field}: 期望 ${expected}, 实际 ${actual}, 差 ${diff}"


def test_4fork_6layer_1500PV_strict_consistency():
    """测试 2: 4 叉 6 层 1500PV 0 差异"""
    ...


def test_8fork_4layer_1500PV_strict_consistency():
    """测试 3: 8 叉 4 层 1500PV 0 差异"""
    ...


def test_2fork_9layer_1000PV_strict_consistency():
    """测试 4: 2 叉 9 层 1000PV 0 差异"""
    ...
```

**关键**:
- 期望值从旧 `tools/_final_output_v3.txt` 读 (或历史 commit message)
- 任何 0.01 差异测试 fail
- 4 套方案全 PASS 才有 P6 收尾

## 5. File Structure

| 文件 | 操作 |
|---|---|
| `tools/scenario_report.py` | Create: 新报表工具 (替代旧 rebuild_2144_simulation.py) |
| `tools/rebuild_2144_simulation.py` | **Delete** (业务逻辑全部迁走) |
| `tools/_final_output_v3.txt` | **Delete** (PR4 旧输出归档) |
| `tools/_verify_p1_pr4_consistency.py` | Create: 全量对比脚本 (2 叉/4 叉/8 叉/1000PV) |
| `main.py` | Modify: 业务路由从 `skills/pair_commission._settle_node` 切到 `scenario.breakdown.compute_commission_breakdown` |
| `skills/pair_commission.py` | **Delete** (旧业务函数) |
| `skills/skill_5_lib.py` | **Delete** (旧 skill 库) |
| `skills/period.py` | **Delete** (PR1 之前) |
| `tests/test_pr4_strict_consistency.py` | Create: 严格数字一致性 (4 套方案, 0 差异) |
| `AGENTS.md` | Modify: §6.4 PR4 状态, §5 业务规则引用更新 |

## 6. 验收

- [ ] `tools/scenario_report.py` 创建 (新报表工具, 调 scenario/ 引擎)
- [ ] `tools/rebuild_2144_simulation.py` 删除
- [ ] `tools/_final_output_v3.txt` 删除
- [ ] `skills/pair_commission.py` 删除
- [ ] `skills/skill_5_lib.py` 删除
- [ ] `skills/period.py` 删除
- [ ] `main.py` 业务路由改走 scenario/ 引擎
- [ ] 4 套方案数字严格 0 差异 (2 叉/4 叉/8 叉/1000PV)
- [ ] `tests/test_pr4_strict_consistency.py` 4 测试 PASS
- [ ] 0 后端接口变化 (API 路径/参数/返回不变)
- [ ] 0 业务规则变化
- [ ] AGENTS.md §6.4 + §5 更新
- [ ] 80+4 = 84 测试 pass (PR1 1 + P5 1 + 已知, 0 回归)

## 7. 风险

| 风险 | 缓解 |
|---|---|
| main.py 业务路由改完数字跟旧不一致 (0.01 偏差) | 严格数字一致性测试, 任何 0.01 偏差 fail, 回滚到 backup-before-p6 分支 |
| 旧 skills/ 函数删完别处还有 import | 删之前 grep 全仓, 确认 0 import |
| 旧前端 index.html 走旧业务路由, 改完不工作 | main.py API 路径/参数/返回不变, 0 前端改动 |
| tools/scenario_report.py 数字跟旧 _final_output_v3.txt 不一致 | 跑全量对比, 4 套方案全 PASS 才进下一 commit |
| 业务规则变化 (test_pr4_strict_consistency fail) | 业务接受 0 业务规则变化, 任何 0.01 偏差都不合并 |

## 8. 业务定位 (大重构 P1 阶段 100% 收官)

- P1 场景核心引擎 ✅
- P2 8 种报酬 v2 ✅
- P3 树形动态生长 UI ✅
- P4 方案库 + 分享 ✅
- P5 商业计划书 PDF ✅
- P1.5 性能优化一阶 ✅ (14月 14分钟 → 760ms, 1100x)
- P1.6 性能优化二阶 ✅ (1st call 760ms → 0-200ms)
- **P6 旧运营兼容层 (本 PR, 迁移+删旧, 100% 收官) ✅**

总 8 子项目 50+ commit, 大重构 P1 阶段 100% 收官.

## 9. 后续 (大重构 P2 阶段, 业务待拍板)

- **P2.1**: 业务规则扩展 (新 commission 模式, 新 PV 公式, ...)
- **P2.2**: 多语言 (i18n)
- **P2.3**: 移动端 (PWA / React Native)
- **P2.4**: 真实业务数据接入 (从 demo 切到 production)
- **P2.5**: SaaS 化 (多租户 / 权限 / 计费)
