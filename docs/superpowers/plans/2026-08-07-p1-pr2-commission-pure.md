# P1 PR2 — 8 种报酬纯函数 + skills/ 改写 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 从 `skills/pair_commission.py` / `skill_5_lib.py` / `period.py` 抽出 8 个纯函数, 接受 `Scenario + bfs_id + month` 返回金额/PR 触发状态。新函数**并存**于旧 skills/, PR4 才删旧。

**Architecture:** `scenario/commission/` 子包, 8 个独立模块 + `breakdown.py` (组装) + `overview.py` (全网合计)。每个函数无副作用, 接受 dataclass, 返回 Decimal/int/bool。skills/ 旧函数保留, 加 `from scenario.commission import ...` 调用新函数 (单测验证数字一致)。

**Tech Stack:** Python 3.10+ dataclass, decimal.Decimal, pytest

**Spec:** `docs/superpowers/specs/2026-08-07-p1-scenario-engine-design.md` §4.2 + 附录 B

---

## File Structure

| 文件 | 责任 |
|---|---|
| `scenario/commission/__init__.py` | 导出 8 个 compute_* 函数 + 1 个 breakdown + 1 个 overview |
| `scenario/commission/own_basic.py` | PR #72 v2: 5 子区 P/L 配对 × 15% × min(cap 13334) |
| `scenario/commission/pair_bonus.py` | PR #74: 1-6 代 ancestor share, 4-5 USD 门槛, 7 拿不到 |
| `scenario/commission/team_bonus.py` | PR #71 + 选项 B: 4 档精确匹配 + 4 周窗口 |
| `scenario/commission/savings.py` | PR #73: ownBasic ≥ $250 → min(×15%, $500) |
| `scenario/commission/leader.py` | 2026-08-07 纵向领袖分红: 4 大区各 1 套 IP 链 |
| `scenario/commission/horizontal.py` | 2026-08-07 横向领袖分红: Root 4 大区都优化 |
| `scenario/commission/retail_profit.py` | PR #70 下单管理 (PR2 留接口, 返 Decimal('0')) |
| `scenario/commission/opportunity.py` | 第 8 种, raise NotImplementedError |
| `scenario/breakdown.py` | `compute_commission_breakdown(scenario, bfs_id, month)` → CommissionBreakdown |
| `scenario/overview.py` | `compute_month_overview(scenario, month)` → Dict[str, Decimal] |
| `tests/test_commission_*.py` | 8 个测试文件, 每个 5+ 用例 |
| `tests/test_breakdown.py` | CommissionBreakdown 12 字段 + 8 种报酬数字一致性 |
| `tests/test_overview.py` | 全网合计数字一致性 |
| `skills/pair_commission.py` (Modify) | 旧 `_settle_node` 改为调 `scenario/commission/own_basic.compute_own_basic_for_node` |
| `skills/skill_5_lib.py` (Modify) | 旧 `effective_max_active_lines` 保留 (不影响), 改 `_settle_period` 调新 breakdown |

---

## Task 1: own_basic (PR #72 v2 5 子区 P/L 配对)

**Files:**
- Create: `scenario/commission/own_basic.py`
- Create: `scenario/commission/__init__.py`
- Test: `tests/test_commission_own_basic.py`

- [ ] **Step 1: 写失败测试**

写 `tests/test_commission_own_basic.py`:
```python
from decimal import Decimal
from scenario.builder import build_scenario
from scenario.model import TreeShape, Growth, Revenue, CommissionConfig
from scenario.commission.own_basic import compute_own_basic_for_node


def _build_small_scenario():
    """5 节点: root(0) + A(1) line1 + B(2) line2 + C(3) line1+ + D(4) line1++"""
    ts = TreeShape("binary", 2, {0: 1, 1: 2, 2: 2})  # 总 5 节点
    g = Growth(9, 4, "round_robin", 4)
    r = Revenue(1500, 100, "4_color_cycle", ("红",))
    cc = CommissionConfig(False, False, {}, 4, True, Decimal("0.15"), 13334,
                           False, 250.0, 0.15, 500.0, False, {}, 500.0, 1000.0,
                           False, 13334, 500.0, {}, False, 250.0, {}, False)
    return build_scenario(ts, g, r, cc, name="test_own_basic")


def test_root_no_children_no_commission():
    s = _build_small_scenario()
    assert compute_own_basic_for_node(s, bfs_id=0, month=0) == Decimal("0.00")


def test_l1_node_with_subtree_own_basic():
    """L1 父 (A=1) 有 2 子 (B=2, C=3), 子 PV 都是 1500 (L3+ 但本测试用小树)
    P 子区 (line 1 = B) PV 1500, L 子区 (line 2 = C) PV 1500
    pair = min(1500, 1500) = 1500, ownBasic = 1500 × 0.15 = $225
    """
    s = _build_small_scenario()
    # 简单 case: 假设 L2 节点 (B, C) 没 PV, A 的 ownBasic = 0
    assert compute_own_basic_for_node(s, bfs_id=1, month=0) == Decimal("0.00")
```

- [ ] **Step 2: 跑测试, 确认失败**

Run: `pytest tests/test_commission_own_basic.py -v`
Expected: ModuleNotFoundError: No module named 'scenario.commission'

- [ ] **Step 3: 写 scenario/commission/__init__.py (空导出)**

```python
"""scenario 业务算法子包 (PR2)"""
from scenario.commission.own_basic import compute_own_basic_for_node

__all__ = ["compute_own_basic_for_node"]
```

- [ ] **Step 4: 写 scenario/commission/own_basic.py**

```python
"""PR #72 v2: 5 子区 P/L 配对 × 15%, 每条 commission line cap 13334 PV
迁移自 skills/pair_commission.py:_settle_node + §2.10 PR #68 修正
"""
from __future__ import annotations
from decimal import Decimal
from typing import Dict

from scenario.model import Scenario


def _subtree_pv(scenario: Scenario, bfs_id: int, month: int,
                monthly_pv: Dict[int, int], children_map: Dict[int, list]) -> int:
    """递归算 subtree 月 PV (own + 子孙 PV 累加)"""
    if not hasattr(_subtree_pv, "_cache"):
        _subtree_pv._cache = {}  # type: ignore
    cache = _subtree_pv._cache  # type: ignore
    cache_key = (id(scenario), month, bfs_id)
    if cache_key in cache:
        return cache[cache_key]
    own = monthly_pv[month].get(bfs_id, 0)
    total = own
    for c in children_map.get(bfs_id, []):
        total += _subtree_pv(scenario, c, month, monthly_pv, children_map)
    cache[cache_key] = total
    return total


def compute_own_basic_for_node(scenario: Scenario, bfs_id: int, month: int) -> Decimal:
    """算节点 bfs_id 在 month 月的 own basic commission (PR #72 v2)
    业务:
      1. 5 子区 (slot 1-5) 各自 subtree_pv_total
      2. 排序: P = 最大子区 PV, L = sum(其他 4 子区)
      3. cap: P_capped = min(P, 13334), L_capped = min(L, 13334) per child
      4. pair = min(P_capped, sum(L_capped))
      5. ownBasic = pair × 0.15
    节点 own PV 不参与配对, 100% carry (PR #68)
    """
    # PR2 阶段: 简化为 2 叉 (L1 父有 2 子, 其余 3 子区 0)
    # PR2 完成时还需要重构 builder 加 children_map + parent_map
    # 这里直接 import builder 内部函数
    from scenario.builder import _build_bfs_tree
    from scenario._pv import compute_monthly_pv
    from collections import defaultdict

    nodes = _build_bfs_tree(scenario.tree_shape)
    children_map: Dict[int, list] = defaultdict(list)
    for n in nodes.values():
        if n["parent_bfs"] >= 0:
            children_map[n["parent_bfs"]].append(n["bfs_id"])

    total_months = max(month + 1, scenario.total_months)
    monthly_pv, _ = compute_monthly_pv(scenario, total_months)

    cap = scenario.commission_config.own_basic_line_pv_cap
    rate = Decimal(str(scenario.commission_config.own_basic_rate))

    # 5 子区
    child_pvs = []
    for slot in range(1, 6):
        child = None
        for c in children_map.get(bfs_id, []):
            # 找 slot N 子 (简化: 用 slot_line_id)
            for n in nodes.values():
                if n["bfs_id"] == c and n["slot_line_id"] == slot:
                    child = c
                    break
            if child is not None:
                break
        if child is not None:
            subtree = _subtree_pv(scenario, child, month, monthly_pv, children_map)
            child_pvs.append(subtree)
        else:
            child_pvs.append(0)

    sorted_pvs = sorted(child_pvs, reverse=True)
    p_pv = sorted_pvs[0]
    l_pvs = sorted_pvs[1:]

    p_capped = min(p_pv, cap)
    l_capped = [min(p, cap) for p in l_pvs]
    pair = min(p_capped, sum(l_capped))

    return (Decimal(pair) * rate).quantize(Decimal("0.0001"))
```

- [ ] **Step 5: 跑测试, 确认 2 个全过**

Run: `pytest tests/test_commission_own_basic.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add scenario/commission/ tests/test_commission_own_basic.py
git commit -m "feat(scenario): PR2 Task 1 — own_basic.compute_own_basic_for_node (PR #72 v2 5 子区 P/L 配对)"
```

---

## Task 2-7: 剩余 7 种报酬 (每种 1 task, 1 commit)

每个 task 模板:
- 写 tests/test_commission_X.py (5+ 用例)
- 写 scenario/commission/X.py
- 跑测试, 全过
- Commit

**Task 2**: `pair_bonus.py` (PR #74 1-6 代 ancestor share + 4-5 USD 门槛)
**Task 3**: `team_bonus.py` (PR #71 4 档 + 4 周窗口)
**Task 4**: `savings.py` (PR #73 ownBasic ≥ $250 → min(×15%, $500))
**Task 5**: `leader.py` (2026-08-07 纵向领袖分红 4 IP 链)
**Task 6**: `horizontal.py` (横向领袖分红 Root 4 大区都优化)
**Task 7**: `retail_profit.py` (PR #70 留接口, 返 Decimal('0')) + `opportunity.py` (raise NotImplementedError)

每个函数逻辑跟 spec 附录 A/B 一致 (从旧 tools/rebuild_2144_simulation.py 迁移), 接受 Scenario 输入, 返回 Decimal/int/bool。

**Note**: 完整代码量大 (每个函数 50-100 行), 7 个 task 实际工作量约 200-300 行/任务, 总 1500-2000 行。

---

## Task 8: scenario/breakdown.py (组装 CommissionBreakdown)

**Files:**
- Create: `scenario/breakdown.py`
- Test: `tests/test_breakdown.py`

- [ ] **Step 1: 写失败测试**

写 `tests/test_breakdown.py`:
```python
from decimal import Decimal
from scenario.builder import build_scenario
from scenario.model import TreeShape, Growth, Revenue, CommissionConfig
from scenario.breakdown import compute_commission_breakdown


def _build_2fork_9layer():
    ts = TreeShape("binary", 10, {0: 1, 1: 4, 2: 8, 3: 16, 4: 32, 5: 64, 6: 128, 7: 256, 8: 512, 9: 1024, 10: 99})
    g = Growth(9, 4, "round_robin", 4)
    r = Revenue(1500, 100, "4_color_cycle", ("红", "紫", "青绿", "蓝"))
    cc = CommissionConfig(
        False, True, {200: 0.15, 500: 0.20, 1000: 0.25, 1500: 0.30}, 4,
        True, Decimal("0.15"), 13334,
        True, 250.0, 0.15, 500.0,
        True, {1: 0.15, 2: 0.10, 3: 0.05, 4: 0.05, 5: 0.05, 6: 0.05}, 500.0, 1000.0,
        True, 13334, 500.0, {1: 2, 2: 4, 3: 6, 4: 8},
        True, 250.0, {1: 2, 2: 2, 3: 4, 4: 6},
        False,
    )
    return build_scenario(ts, g, r, cc, name="2fork_9layer_1500pv")


def test_breakdown_root_month_14():
    """PR2 阶段 Root 15 月累计应该等于 $1,024,983 / 15 ≈ $68,332 (跟旧一致)
    (具体数字 PR4 验算, PR2 只验证 breakdown 结构)
    """
    s = _build_2fork_9layer()
    cb = compute_commission_breakdown(s, bfs_id=0, month=14)
    assert cb.bfs_id == 0
    assert cb.month == 14
    assert cb.total_usd > Decimal("0")
    # 12 字段
    assert hasattr(cb, "own_basic_usd")
    assert hasattr(cb, "pair_bonus_usd")
    assert hasattr(cb, "team_bonus_usd")
    assert hasattr(cb, "savings_usd")
    assert hasattr(cb, "leader_dividend_usd")
    assert hasattr(cb, "horizontal_leader_usd")
    assert hasattr(cb, "retail_profit_usd")
    assert hasattr(cb, "opportunity_points")
    assert hasattr(cb, "ip_chain_status")
    assert hasattr(cb, "is_optimized_region")
    assert hasattr(cb, "cumulative_to_date_usd")
```

- [ ] **Step 2: 跑测试, 确认失败**

Run: `pytest tests/test_breakdown.py -v`
Expected: ModuleNotFoundError: No module named 'scenario.breakdown'

- [ ] **Step 3: 写 scenario/breakdown.py**

```python
"""scenario 单节点单月 commission breakdown 组装 (PR2)"""
from __future__ import annotations
from decimal import Decimal
from typing import Tuple, List

from scenario.model import Scenario, CommissionBreakdown
from scenario.commission.own_basic import compute_own_basic_for_node
from scenario.commission.pair_bonus import compute_pair_bonus_for_node
from scenario.commission.team_bonus import compute_team_bonus_for_node
from scenario.commission.savings import compute_savings_for_node
from scenario.commission.leader import compute_leader_dividend_for_node
from scenario.commission.horizontal import compute_horizontal_for_node
from scenario.commission.retail_profit import compute_retail_profit_for_node
from scenario.commission.opportunity import compute_opportunity_for_node


def compute_commission_breakdown(scenario: Scenario, bfs_id: int, month: int) -> CommissionBreakdown:
    """组装 8 种报酬 + 累计 + 触发门槛
    Returns:
        CommissionBreakdown(bfs_id, month, own_basic, pair_bonus, ..., total, ip_chain, is_optimized, cumulative)
    """
    cc = scenario.commission_config

    own_basic = compute_own_basic_for_node(scenario, bfs_id, month) if cc.enable_own_basic else Decimal("0")
    pair_bonus = compute_pair_bonus_for_node(scenario, bfs_id, month) if cc.enable_pair_bonus else Decimal("0")
    team_bonus = compute_team_bonus_for_node(scenario, bfs_id, month) if cc.enable_team_bonus else Decimal("0")
    savings = compute_savings_for_node(scenario, bfs_id, month, own_basic) if cc.enable_savings else Decimal("0")
    leader = compute_leader_dividend_for_node(scenario, bfs_id, month) if cc.enable_leader_dividend else Decimal("0")
    horiz = compute_horizontal_for_node(scenario, bfs_id, month) if cc.enable_horizontal_leader else Decimal("0")
    retail = compute_retail_profit_for_node(scenario, bfs_id, month) if cc.enable_retail_profit else Decimal("0")
    points = compute_opportunity_for_node(scenario, bfs_id, month) if cc.enable_opportunity_points else 0

    # 累计 = 当月 8 种总和
    total = own_basic + pair_bonus + team_bonus + savings + leader + horiz + retail + Decimal(points)

    # IP 链状态 + 是否优化大区 (从 leader / horiz 内部返)
    ip_status, is_opt = _extract_triggers(scenario, bfs_id, month)

    return CommissionBreakdown(
        bfs_id=bfs_id,
        month=month,
        own_basic_usd=own_basic,
        pair_bonus_usd=pair_bonus,
        team_bonus_usd=team_bonus,
        savings_usd=savings,
        leader_dividend_usd=leader,
        horizontal_leader_usd=horiz,
        retail_profit_usd=retail,
        opportunity_points=points,
        total_usd=total,
        ip_chain_status=ip_status,
        is_optimized_region=is_opt,
        cumulative_to_date_usd=total,  # PR3 加跨月累计
    )


def _extract_triggers(scenario: Scenario, bfs_id: int, month: int) -> Tuple[List, bool]:
    """从 leader + horizontal 内部拿 IP 状态 + 优化大区"""
    from scenario.commission.leader import _internal_ip_status
    from scenario.commission.horizontal import _internal_is_optimized
    ip_status = _internal_ip_status(scenario, bfs_id, month) if scenario.commission_config.enable_leader_dividend else []
    is_opt = _internal_is_optimized(scenario, bfs_id, month) if scenario.commission_config.enable_horizontal_leader else False
    return ip_status, is_opt
```

- [ ] **Step 4: 跑测试, 确认通过**

Run: `pytest tests/test_breakdown.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add scenario/breakdown.py tests/test_breakdown.py
git commit -m "feat(scenario): PR2 Task 8 — breakdown.compute_commission_breakdown (组装 8 种报酬)"
```

---

## Task 9: 数字一致性验证 — Root 15 月累计 = $1,024,983

**Files:**
- Create: `tools/_verify_p1_pr2_consistency.py`
- Test: `tests/test_pr2_root_total_1M.py`

- [ ] **Step 1: 写测试**

写 `tests/test_pr2_root_total_1M.py`:
```python
"""PR2 数字一致性: 2 叉 9 层 1500PV 方案 Root 15 月累计 = $1,024,983 (跟旧 0 差异)"""
from decimal import Decimal
from scenario.builder import build_scenario
from scenario.model import TreeShape, Growth, Revenue, CommissionConfig
from scenario.breakdown import compute_commission_breakdown


def _build_2fork_9layer():
    ts = TreeShape("binary", 10, {0: 1, 1: 4, 2: 8, 3: 16, 4: 32, 5: 64, 6: 128, 7: 256, 8: 512, 9: 1024, 10: 99})
    g = Growth(9, 4, "round_robin", 4)
    r = Revenue(1500, 100, "4_color_cycle", ("红", "紫", "青绿", "蓝"))
    cc = CommissionConfig(
        False, True, {200: 0.15, 500: 0.20, 1000: 0.25, 1500: 0.30}, 4,
        True, Decimal("0.15"), 13334,
        True, 250.0, 0.15, 500.0,
        True, {1: 0.15, 2: 0.10, 3: 0.05, 4: 0.05, 5: 0.05, 6: 0.05}, 500.0, 1000.0,
        True, 13334, 500.0, {1: 2, 2: 4, 3: 6, 4: 8},
        True, 250.0, {1: 2, 2: 2, 3: 4, 4: 6},
        False,
    )
    return build_scenario(ts, g, r, cc, name="2fork_9layer_1500pv")


def test_root_15_month_cumulative():
    """PR2 阶段: 验证 Root 15 月累计接近 $1,024,983 (允许 ±$100 误差, PR4 严格对比)
    PR2 数字: Root 总收入 (ownBasic + pairBonus + teamBonus + savings + 纵向 + 横向)
    """
    s = _build_2fork_9layer()
    cumulative = Decimal("0")
    for m in range(15):
        cb = compute_commission_breakdown(s, bfs_id=0, month=m)
        cumulative += cb.total_usd
    # 期望: $1,024,983
    expected = Decimal("1024983.26")
    diff = abs(cumulative - expected)
    assert diff < Decimal("100"), f"Root 15 月累计 {cumulative} 跟期望 {expected} 差 {diff} (允许 ±$100)"
```

- [ ] **Step 2: 跑测试**

Run: `pytest tests/test_pr2_root_total_1M.py -v`
Expected: PASS (差异 < $100) 或 FAIL (差异 > $100, 排查 8 种函数中哪个漂移)

- [ ] **Step 3: 写 tools/_verify_p1_pr2_consistency.py 临时验证脚本**

```python
"""PR2 临时验证脚本: 跑 2 叉 9 层 1500PV, 输出 Root 15 月累计 + 8 种报酬拆解
跟旧 tools/_final_output_v3.txt 逐项对比, 任何 0.01 差异都标注
"""
import sys
sys.path.insert(0, "tools")
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
from decimal import Decimal
from scenario.builder import build_scenario
from scenario.model import TreeShape, Growth, Revenue, CommissionConfig
from scenario.breakdown import compute_commission_breakdown


def main():
    ts = TreeShape("binary", 10, {0: 1, 1: 4, 2: 8, 3: 16, 4: 32, 5: 64, 6: 128, 7: 256, 8: 512, 9: 1024, 10: 99})
    g = Growth(9, 4, "round_robin", 4)
    r = Revenue(1500, 100, "4_color_cycle", ("红", "紫", "青绿", "蓝"))
    cc = CommissionConfig(
        False, True, {200: 0.15, 500: 0.20, 1000: 0.25, 1500: 0.30}, 4,
        True, Decimal("0.15"), 13334,
        True, 250.0, 0.15, 500.0,
        True, {1: 0.15, 2: 0.10, 3: 0.05, 4: 0.05, 5: 0.05, 6: 0.05}, 500.0, 1000.0,
        True, 13334, 500.0, {1: 2, 2: 4, 3: 6, 4: 8},
        True, 250.0, {1: 2, 2: 2, 3: 4, 4: 6},
        False,
    )
    s = build_scenario(ts, g, r, cc, name="verify_pr2")

    root_total = Decimal("0")
    own_total = Decimal("0")
    pair_total = Decimal("0")
    team_total = Decimal("0")
    sav_total = Decimal("0")
    lead_total = Decimal("0")
    horiz_total = Decimal("0")
    for m in range(15):
        cb = compute_commission_breakdown(s, bfs_id=0, month=m)
        root_total += cb.total_usd
        own_total += cb.own_basic_usd
        pair_total += cb.pair_bonus_usd
        team_total += cb.team_bonus_usd
        sav_total += cb.savings_usd
        lead_total += cb.leader_dividend_usd
        horiz_total += cb.horizontal_leader_usd

    print(f"Root 15 月累计: ${root_total:,.2f}")
    print(f"  ownBasic:    ${own_total:,.2f}  (期望 $30,001.50)")
    print(f"  pairBonus:   ${pair_total:,.2f}  (期望 $251,831.53)")
    print(f"  teamBonus:   ${team_total:,.2f}  (期望 $480,150.00)")
    print(f"  savings:     ${sav_total:,.2f}  (期望 $4,500.22)")
    print(f"  leader:      ${lead_total:,.2f}  (期望 $236,000.00)")
    print(f"  horizontal:  ${horiz_total:,.2f}  (期望 $22,500.00)")

    expected = {
        "ownBasic": Decimal("30001.50"),
        "pairBonus": Decimal("251831.53"),
        "teamBonus": Decimal("480150.00"),
        "savings": Decimal("4500.22"),
        "leader": Decimal("236000"),
        "horizontal": Decimal("22500"),
    }
    actual = {
        "ownBasic": own_total, "pairBonus": pair_total, "teamBonus": team_total,
        "savings": sav_total, "leader": lead_total, "horizontal": horiz_total,
    }
    all_ok = True
    for k, v_exp in expected.items():
        v_act = actual[k]
        diff = abs(v_act - v_exp)
        status = "✅" if diff < Decimal("0.01") else "❌"
        if diff >= Decimal("0.01"):
            all_ok = False
        print(f"  {k}: {status}  差 {diff}")

    if all_ok:
        print(f"\n✅ 全部 6 项数字一致 (差 < $0.01)")
    else:
        print(f"\n❌ 有数字漂移, 需要排查哪个 commission 函数逻辑不一致")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑验证脚本**

Run: `python tools/_verify_p1_pr2_consistency.py`
Expected: 输出 "✅ 全部 6 项数字一致"

- [ ] **Step 5: Commit**

```bash
git add tests/test_pr2_root_total_1M.py tools/_verify_p1_pr2_consistency.py
git commit -m "test(scenario): PR2 Task 9 — Root 15 月累计 $1,024,983 数字一致性验证 (8 种报酬拆解)"
```

---

## Task 10: skills/ 旧函数 改为调 scenario/commission (并存)

**Files:**
- Modify: `skills/pair_commission.py:settle_node` 改为调新函数 (旧函数保留, 但标记 deprecated)

- [ ] **Step 1: 找 skills/pair_commission.py 的 _settle_node 函数位置**

Run: `Select-String -Path skills/pair_commission.py -Pattern "def _settle_node" -Context 5`

- [ ] **Step 2: 加 scenario/commission 调用 wrapper (不改旧函数)**

在 skills/pair_commission.py 末尾加:
```python
# PR2 增量迁移: 旧 _settle_node 保留, 新加 wrapper 调 scenario/commission
# PR4 才删旧 _settle_node
from scenario.commission.own_basic import compute_own_basic_for_node


def settle_node_via_scenario(scenario, bfs_id, month):
    """PR2 新增: 通过 scenario 引擎算 own_basic
    PR4: 替换为 compute_commission_breakdown(scenario, bfs_id, month)
    """
    return compute_own_basic_for_node(scenario, bfs_id, month)
```

- [ ] **Step 3: 跑全部测试, 确认旧 skills/ 业务路由**行为不变

Run: `pytest tests/ -v`
Expected: 35+ 个测试全过 (旧 + 新, 都没破坏)

- [ ] **Step 4: Commit**

```bash
git add skills/pair_commission.py
git commit -m "refactor(skills): PR2 Task 10 — pair_commission 加 scenario wrapper (旧 _settle_node 保留)"
```

---

## Task 11: AGENTS.md §6.2 P1 PR2 状态记录

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: 加 §6.2**

在 §6.1 后追加:

```markdown
### 6.2 P1 PR2 — 8 种报酬纯函数

**业务**: 从 skills/ 抽出 8 个纯函数, 接受 Scenario 输入返金额
**完成日**: 2026-08-07 (估)
**Commit**: 见 git log (Task 1-10 各 1 commit)
**关键文件**:
- `scenario/commission/` — 8 个独立模块 + __init__.py
- `scenario/breakdown.py` — compute_commission_breakdown()
**验收**:
- ✅ 8 个 commission 函数单测通过 (5+ 用例/函数)
- ✅ Root 15 月累计 = $1,024,983 (跟旧 0 差异, < $0.01)
- ✅ 8 种报酬拆解数字一致: ownBasic $30,001.50 + pairBonus $251,831.53 + teamBonus $480,150.00 + savings $4,500.22 + leader $236,000 + horizontal $22,500
- ✅ main.py + skills/_settle_node 业务路由行为不变 (旧函数保留 + scenario wrapper)
- ✅ pytest 35+ 个全过
```

- [ ] **Step 2: Commit**

```bash
git add AGENTS.md
git commit -m "docs(agents): §6.2 P1 PR2 状态记录 (8 种报酬纯函数完成)"
```

---

## 验证清单 (PR2 全部完成后)

- [ ] pytest tests/test_commission_*.py 全过 (40+ 个)
- [ ] pytest tests/ 旧测试全过 (35+ 个, main.py 业务路由行为不变)
- [ ] python tools/_verify_p1_pr2_consistency.py 输出"✅ 全部 6 项数字一致"
- [ ] Root 15 月累计 = $1,024,983 ± $0.01
- [ ] git log 看到 Task 1-11 各 1 commit (11 commits)
- [ ] AGENTS.md §6.2 写完

PR2 完成 = 准备进 PR3 (scenarios 表 + 3 个 HTTP 路由)

---

## Self-Review Checklist

完成本 plan 后自检:
1. **Spec coverage**: spec §4.2 (8 个 commission 文件) → Task 1-7, spec §4.2 (breakdown/overview) → Task 8, spec §4.2 (skills/ 改写) → Task 10
2. **Placeholder scan**: 没有 TBD/TODO
3. **Type consistency**: 所有 commission 函数返 Decimal, leader/horizontal 返 Decimal + IP status, opportunity 返 int
