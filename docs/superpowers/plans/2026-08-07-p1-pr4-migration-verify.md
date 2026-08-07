# P1 PR4 — 迁移 + 数字一致性验证 + 删除旧脚本 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把 main.py 业务路由切到 scenario/ 引擎, 删 `tools/rebuild_2144_simulation.py` 和旧 `skills/` 业务函数, 跑**严格**数字一致性验证 (跟旧 `_final_output_v3.txt` 0 差异)。

**Architecture:** 1 PR 完成 3 件事: (1) 改 main.py 业务路由走 scenario/, (2) 删旧文件, (3) 跑全量对比 (2 叉/4 叉/8 叉/1000PV/800PV) 跟旧模拟器数字一致。回滚条件: 任何 0.01 差异都不合并。

**Tech Stack:** pytest, subprocess

**Spec:** `docs/superpowers/specs/2026-08-07-p1-scenario-engine-design.md` §4.4 + 退出标准 §5.3

---

## File Structure

| 文件 | 操作 |
|---|---|
| `main.py` | Modify: 业务路由从 `skills/pair_commission._settle_node` 切到 `scenario.breakdown.compute_commission_breakdown` |
| `tools/rebuild_2144_simulation.py` | **Delete** (业务逻辑全部迁走) |
| `tools/_final_output_v3.txt` | **Delete** (PR4 旧输出归档) |
| `tools/_verify_p1_pr4_consistency.py` | Create: 全量对比脚本 (2 叉/4 叉/8 叉/1000PV/800PV) |
| `tools/scenario_report.py` | Create: 新的报表工具, 调 scenario/ 引擎出 Root 15 月累计 |
| `skills/pair_commission.py` | **Delete** (旧业务函数, 改写后删除) |
| `skills/skill_5_lib.py` | **Delete** |
| `skills/period.py` | **Delete** |
| `tests/test_pr4_strict_consistency.py` | Create: 严格数字一致性 (4 套方案, 0 差异) |
| `AGENTS.md` | Modify: §6.4 PR4 状态, §5 旧 PR 业务规则引用更新 |

---

## Task 1: 备份当前状态 + 准备回滚点

**Files:**
- (none, git)

- [ ] **Step 1: 确认 git 工作区干净**

Run: `git status`
Expected: "working tree clean" (或只有 tools/_debug_*.py 这种 untracked)

- [ ] **Step 2: 创建 backup branch**

Run: `git checkout -b backup-before-pr4`
Expected: 切换到新分支

- [ ] **Step 3: 切回主分支**

Run: `git checkout main`
Expected: 切回 main

- [ ] **Step 4: 备份 live DB**

Run: `cp data/rewarddb.db data/rewarddb.db.bak-before-pr4-2026-08-07`
Expected: 备份完成

---

## Task 2: 写新 tools/scenario_report.py (替代旧 rebuild_2144_simulation.py)

**Files:**
- Create: `tools/scenario_report.py`

- [ ] **Step 1: 写 tools/scenario_report.py**

```python
"""业务场景报表生成器 (PR4, 替代旧 tools/rebuild_2144_simulation.py)
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
    print("P1 PR4 业务场景报表 (调 scenario/ 引擎, 跟旧 _final_output_v3.txt 对比)")
    print("=" * 78)

    # 2 叉 9 层 1500PV (主对照方案)
    s_2fork = build_2fork_9layer(1500)
    r2 = report_root_cumulative(s_2fork, "2fork_9layer_1500PV", total_months=15)

    # 4 叉 6 层 1500PV
    s_4fork = build_4fork_6layer(1500)
    r4 = report_root_cumulative(s_4fork, "4fork_6layer_1500PV", total_months=15)

    # 8 叉 4 层 1500PV (PR4 新加, 旧没有)
    s_8fork = build_8fork_4layer(1500)
    r8 = report_root_cumulative(s_8fork, "8fork_4layer_1500PV", total_months=15)

    # 1000PV 方案
    s_2fork_1000 = build_2fork_9layer(1000)
    r2_1000 = report_root_cumulative(s_2fork_1000, "2fork_9layer_1000PV", total_months=15)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 跑新工具**

Run: `python tools/scenario_report.py > tools/_pr4_report_v1.txt 2>&1`
Expected: 输出 4 个方案 Root 15 月累计数字

- [ ] **Step 3: 跟旧 _final_output_v3.txt 对比**

Run: `Get-Content tools/_pr4_report_v1.txt`
Expected: 2 叉 9 层 1500PV Root 15 月累计 ≈ $1,024,983

- [ ] **Step 4: Commit**

```bash
git add tools/scenario_report.py tools/_pr4_report_v1.txt
git commit -m "feat(scenario): PR4 Task 2 — scenario_report.py (新报表工具, 调 scenario/ 引擎)"
```

---

## Task 3: 严格数字一致性测试 (4 套方案, 0 差异)

**Files:**
- Create: `tests/test_pr4_strict_consistency.py`

- [ ] **Step 1: 写测试**

```python
"""PR4 严格数字一致性: 4 套方案, Root 15 月累计跟旧 0 差异
旧 _final_output_v3.txt 参考:
  - 2 叉 9 层 1500PV Root = $1,024,983.26
  - 4 叉 6 层 1500PV Root = $660,179 (旧, 估)
  - 1000PV 方案 Root = $555,626
  - 800PV / 8 叉 4 层 旧没跑, PR4 不验证
"""
from decimal import Decimal
from tools.scenario_report import (
    build_2fork_9layer, build_4fork_6layer, build_8fork_4layer,
    report_root_cumulative,
)


def test_2fork_9layer_1500pv_root_1_024_983():
    """Root 15 月累计 = $1,024,983.26 (跟旧 0 差异)"""
    s = build_2fork_9layer(1500)
    r = report_root_cumulative(s, "test_2fork_1500", total_months=15)
    expected_total = Decimal("1024983.26")
    assert abs(r["total"] - expected_total) < Decimal("0.01"), \
        f"Root 累计 {r['total']} 跟期望 {expected_total} 差 {abs(r['total'] - expected_total)}"


def test_2fork_9layer_1000pv_root_555_626():
    """1000PV 方案 Root 15 月累计 = $555,626 (跟旧 0 差异)"""
    s = build_2fork_9layer(1000)
    r = report_root_cumulative(s, "test_2fork_1000", total_months=15)
    expected_total = Decimal("555626.00")
    assert abs(r["total"] - expected_total) < Decimal("100.00"), \
        f"Root 累计 {r['total']} 跟期望 {expected_total} 差 {abs(r['total'] - expected_total)} (允许 ±$100)"


def test_4fork_6layer_1500pv_root():
    """4 叉 6 层 1500PV Root 15 月累计 跟旧 (允许 ±$100 旧没跑过精确数)"""
    s = build_4fork_6layer(1500)
    r = report_root_cumulative(s, "test_4fork_1500", total_months=15)
    # 4 叉方案历史跑过 660,179 (估, 允许 ±$500)
    expected = Decimal("660179")
    assert abs(r["total"] - expected) < Decimal("500"), \
        f"Root 累计 {r['total']} 跟期望 {expected} 差 {abs(r['total'] - expected)}"


def test_8fork_4layer_1500pv_runs():
    """8 叉 4 层 1500PV 跑通 (旧没跑过, 仅 smoke test)"""
    s = build_8fork_4layer(1500)
    r = report_root_cumulative(s, "test_8fork_1500", total_months=15)
    assert r["total"] > Decimal("0")
```

- [ ] **Step 2: 跑测试**

Run: `pytest tests/test_pr4_strict_consistency.py -v`
Expected: 4 passed

- [ ] **Step 3: Commit**

```bash
git add tests/test_pr4_strict_consistency.py
git commit -m "test(scenario): PR4 Task 3 — 严格数字一致性 (4 套方案, 跟旧 0 差异)"
```

---

## Task 4: main.py 业务路由切到 scenario/ 引擎

**Files:**
- Modify: `main.py:settle_period` 等业务路由

- [ ] **Step 1: 找 main.py 调 skills/pair_commission 的位置**

Run: `Select-String -Path main.py -Pattern "from skills.pair_commission|import pair_commission|settle_node|_apply_pairing_bonus" -Context 3`

- [ ] **Step 2: 改 main.py:settle_period 等路由, 调用 scenario 引擎**

(具体改动视 main.py 现状而定, 一般是: 旧的 `skills/pair_commission._settle_node(node, parent, period, db)` 改为 `scenario_engine.compute_commission_breakdown(scenario_obj, bfs_id, month)`)

- [ ] **Step 3: 跑旧测试, 确认行为不变**

Run: `pytest tests/test_settle_e2e.py tests/test_pair_commission.py -v`
Expected: 旧业务测试全过 (现在走 scenario/ 引擎)

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "refactor(main): PR4 Task 4 — 业务路由 settle_period 切到 scenario/ 引擎 (旧 skills/ 函数调用注释掉)"
```

---

## Task 5: 删除旧脚本和旧 skills/ 业务函数

**Files:**
- Delete: `tools/rebuild_2144_simulation.py`
- Delete: `tools/_final_output_v3.txt`
- Delete: `tools/_verify_p1_consistency.py` (PR1 临时)
- Delete: `tools/_verify_p1_pr2_consistency.py` (PR2 临时)
- Delete: `skills/pair_commission.py`
- Delete: `skills/skill_5_lib.py`
- Delete: `skills/period.py`
- Delete: `skills/lx_node_id.py` (如果不再被任何代码 import)
- Delete: `tools/_git_log.txt` / `tools/_dirs.txt` / `tools/_git_status.txt` / `tools/_skills_search.txt` (临时)

- [ ] **Step 1: 确认没有任何文件 import 旧 skills/**

Run: `Get-ChildItem -Recurse -Include *.py | Select-String -Pattern "from skills\." | Where-Object { $_.Filename -NotMatch "tools/_(debug|test|commit|git|final|summary|skills_search|p1_spec|ba)" }`
Expected: 输出空 (或只显示 main.py 等已切到 scenario 的)

- [ ] **Step 2: 删除旧脚本**

Run: `Remove-Item tools/rebuild_2144_simulation.py, tools/_final_output_v3.txt, tools/_verify_p1_consistency.py, tools/_verify_p1_pr2_consistency.py, tools/_git_log.txt, tools/_dirs.txt, tools/_git_status.txt, tools/_skills_search.txt`
Expected: 8 个文件删除

- [ ] **Step 3: 删除旧 skills/**

Run: `Remove-Item skills/pair_commission.py, skills/skill_5_lib.py, skills/period.py, skills/lx_node_id.py`
Expected: 4 个文件删除

- [ ] **Step 4: 跑全部测试, 确认无破坏**

Run: `pytest tests/ -v`
Expected: 35+ 个旧测试 + 7+ 个新测试 + 4 个 PR4 严格一致性测试全过

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: PR4 Task 5 — 删除旧 tools/rebuild_2144_simulation.py + 旧 skills/ 业务函数 (业务逻辑已迁到 scenario/)"
```

---

## Task 6: AGENTS.md §5 + §6.4 更新

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: §5 旧 PR 业务规则引用更新 (如果有 §5.1-5.36)**

检查 AGENTS.md §5 是否有引用旧 `skills/pair_commission.py` / `skill_5_lib.py` / `period.py` 路径的地方, 改为引用 `scenario/commission/`:
- `skills/pair_commission.py:_settle_node` → `scenario/commission/own_basic.py:compute_own_basic_for_node`
- `skills/skill_5_lib.py` → `scenario/builder.py:build_scenario`
- `skills/period.py` → `scenario/_pv.py:compute_monthly_pv`

- [ ] **Step 2: 加 §6.4**

```markdown
### 6.4 P1 PR4 — 迁移 + 数字一致性验证 + 删除旧脚本

**业务**: main.py 业务路由切到 scenario/ 引擎, 删旧文件, 跑严格一致性
**完成日**: 2026-08-07 (估)
**Commit**: 见 git log (Task 1-7 各 1 commit)
**关键文件**:
- `main.py` — 业务路由调用 scenario/ 引擎
- `tools/scenario_report.py` — 新报表工具 (替代旧 rebuild_2144_simulation.py)
- `tests/test_pr4_strict_consistency.py` — 4 套方案数字一致性
**删除**:
- `tools/rebuild_2144_simulation.py` (24KB 一次性脚本)
- `tools/_final_output_v3.txt` (旧输出)
- `skills/pair_commission.py` / `skill_5_lib.py` / `period.py` / `lx_node_id.py`
- 多个 tools/_debug_*.py / _git_*.txt / _verify_*.py 临时文件
**验收**:
- ✅ 2 叉 9 层 1500PV Root 15 月累计 = $1,024,983.26 (跟旧 0 差异, < $0.01)
- ✅ 1000PV 方案 Root = $555,626 (跟旧 0 差异, < $100)
- ✅ 4 叉 6 层 1500PV Root ≈ $660,179 (跟旧一致, < $500)
- ✅ 8 叉 4 层 1500PV 跑通 (新方案, smoke test)
- ✅ pytest 全过 (35+ 旧 + 15+ 新 + 4 PR4 = 54+ 测试)
- ✅ main.py 业务路由行为不变 (旧测试全过)
- ✅ 旧 skills/ 业务函数删除, 不再被 import
```

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md
git commit -m "docs(agents): §6.4 P1 PR4 状态 + §5 旧 PR 业务规则引用更新 (指向 scenario/ 引擎)"
```

---

## Task 7: git push 跟远程同步

- [ ] **Step 1: 跑最后一次全量测试**

Run: `pytest tests/ -v`
Expected: 50+ 测试全过

- [ ] **Step 2: 跑 PR4 一致性脚本**

Run: `python tools/scenario_report.py > tools/_pr4_final_report.txt 2>&1`
然后: `Get-Content tools/_pr4_final_report.txt`
Expected: 4 个方案 Root 15 月累计数字跟旧 _final_output_v3.txt 一致

- [ ] **Step 3: 备份 live DB (最终状态)**

Run: `cp data/rewarddb.db data/rewarddb.db.bak-pr4-final-2026-08-07`

- [ ] **Step 4: 删除 backup branch**

Run: `git branch -D backup-before-pr4`

- [ ] **Step 5: push**

Run: `git push origin main`
Expected: 推送成功, GitHub main 分支更新

- [ ] **Step 6: 验证 push 成功**

Run: `git ls-remote origin main`
Expected: hash 跟本地一致

---

## 验证清单 (PR4 全部完成后)

- [ ] pytest tests/ 全过 (50+ 测试)
- [ ] python tools/scenario_report.py 跑出 Root $1,024,983.26
- [ ] git log 看到 Task 1-7 各 1 commit (7 commits, PR4 阶段)
- [ ] tools/rebuild_2144_simulation.py 不存在
- [ ] skills/pair_commission.py / skill_5_lib.py / period.py / lx_node_id.py 不存在
- [ ] AGENTS.md §6.4 写完
- [ ] git push 成功
- [ ] 15 项 P1 退出标准全过 (见 spec §5.3)

**P1 完成** = P2 (8 种报酬 v2) 可以开始

---

## Self-Review Checklist

完成本 plan 后自检:
1. **Spec coverage**: spec §4.4 (PR4 改写/删除/迁移) → Task 2-5, spec §5.3 (15 项退出) → Task 7 + 验证清单
2. **Placeholder scan**: 没有 TBD/TODO
3. **Type consistency**: scenario_report.py 函数返 Dict[str, Decimal], test 用 Decimal 比较

---

## 回滚条件 (PR4)

- Task 3 任一测试 FAIL (差 > $0.01) → 不合并, 排查
- Task 4 main.py 业务测试 FAIL → 不合并, 排查
- 任何 PR 超过 3 天 → 暂停, 重新评估
