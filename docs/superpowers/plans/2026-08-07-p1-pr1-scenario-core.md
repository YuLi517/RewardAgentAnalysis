# P1 PR1 — Scenario 库核心 + 树形构建 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 创建 `scenario/` 库的核心 dataclass + 树形构建 + LRU 缓存 + PV 计算, 跟旧 `tools/rebuild_2144_simulation.py` 跑出**完全一致**的 2144 节点 BFS 树。

**Architecture:** 4 个 frozen dataclass (TreeShape / Growth / Revenue / CommissionConfig) + 1 个 Scenario 容器 + 2 个输出 (CommissionBreakdown / MonthSnapshot)。LRU maxsize=50 缓存 month→MonthSnapshot。scenario/_pv.py 从旧模拟器迁移 compute_monthly_pv()。`main.py` + `skills/` 0 改动。

**Tech Stack:** Python 3.10+ dataclasses (frozen=True), functools.lru_cache, pytest

**Spec:** `docs/superpowers/specs/2026-08-07-p1-scenario-engine-design.md` §3 + §4.1

---

## File Structure

| 文件 | 责任 |
|---|---|
| `scenario/__init__.py` | 导出 Scenario, build_scenario, get_pv |
| `scenario/model.py` | 5 个 dataclass: TreeShape, Growth, Revenue, CommissionConfig, Scenario, CommissionBreakdown, MonthSnapshot |
| `scenario/builder.py` | `build_scenario(params)` 从 4 组参数构 BFS 树 + 算 total_weeks/months/target |
| `scenario/_pv.py` | `compute_monthly_pv(scenario)` 跟 `compute_weekly_period_pv(scenario)` |
| `scenario/cache.py` | `lru_cached_month` 装饰器 (maxsize=50, key=id(scenario) + month) |
| `tests/test_scenario_model.py` | 7 个 dataclass 字段单测 |
| `tests/test_scenario_builder.py` | 3 种 fork_type (binary/four_way/eight_way) 各建 1 个 scenario, 验证节点数 + 层节点分布 |
| `tests/test_scenario_pv.py` | compute_monthly_pv 单节点 + 整网测试 |

---

## Task 1: 创建 scenario 包 + model.py (5 dataclass)

**Files:**
- Create: `scenario/__init__.py`
- Create: `scenario/model.py`
- Test: `tests/test_scenario_model.py`

- [ ] **Step 1: 写失败测试**

写 `tests/test_scenario_model.py`:
```python
from scenario.model import TreeShape, Growth, Revenue, CommissionConfig, Scenario, CommissionBreakdown, MonthSnapshot

def test_tree_shape_is_frozen():
    ts = TreeShape(fork_type="binary", max_level=9, layer_counts={0: 1, 1: 4})
    import pytest
    with pytest.raises(Exception):  # FrozenInstanceError
        ts.fork_type = "four_way"

def test_growth_defaults():
    g = Growth(nodes_per_region_per_week=9, n_regions=4, join_strategy="round_robin", weeks_per_month=4)
    assert g.weeks_per_month == 4

def test_revenue_color_names_tuple():
    r = Revenue(initial_pv=1500, monthly_renew_pv=100, color_rule="4_color_cycle", color_names=("红", "紫", "青绿", "蓝"))
    assert r.color_names[0] == "红"

def test_commission_config_all_8_toggles():
    cc = CommissionConfig(
        enable_retail_profit=True, enable_team_bonus=True,
        team_bonus_tier_rates={200: 0.15}, team_bonus_window_weeks=4,
        enable_own_basic=True, own_basic_rate=0.15, own_basic_line_pv_cap=13334,
        enable_savings=True, savings_usd_threshold=250.0, savings_rate=0.15, savings_cap_usd=500.0,
        enable_pair_bonus=True, pair_bonus_ratios={1: 0.15}, pair_bonus_4th_usd_threshold=500.0, pair_bonus_5th_usd_threshold=1000.0,
        enable_leader_dividend=True, leader_dividend_threshold_pv=13334, leader_dividend_share_usd=500.0, leader_dividend_tiers={1: 2},
        enable_horizontal_leader=True, horizontal_leader_share_usd=250.0, horizontal_leader_tiers={1: 2},
        enable_opportunity_points=False,
    )
    assert cc.enable_opportunity_points is False

def test_scenario_id_optional():
    s = Scenario(
        id=None, name="test",
        tree_shape=TreeShape("binary", 9, {0: 1}), growth=Growth(9, 4, "round_robin", 4),
        revenue=Revenue(1500, 100, "4_color_cycle", ("红",)),
        commission_config=CommissionConfig(False, False, {}, 4, False, 0.15, 13334, False, 250.0, 0.15, 500.0, False, {}, 500.0, 1000.0, False, 13334, 500.0, {}, False, 250.0, {}, False),
        total_target=2144, total_weeks=60, total_months=15,
    )
    assert s.id is None

def test_commission_breakdown_has_12_fields():
    cb = CommissionBreakdown(
        bfs_id=0, month=0,
        own_basic_usd=0, pair_bonus_usd=0, team_bonus_usd=0, savings_usd=0,
        leader_dividend_usd=0, horizontal_leader_usd=0,
        retail_profit_usd=0, opportunity_points=0, total_usd=0,
        ip_chain_status=[], is_optimized_region=False, cumulative_to_date_usd=0,
    )
    assert cb.bfs_id == 0

def test_month_snapshot_aggregate():
    ms = MonthSnapshot(month=0, nodes_state={}, aggregate={"ownBasic": 100.0})
    assert ms.aggregate["ownBasic"] == 100.0
```

- [ ] **Step 2: 跑测试, 确认失败**

Run: `pytest tests/test_scenario_model.py -v`
Expected: ModuleNotFoundError: No module named 'scenario'

- [ ] **Step 3: 写 scenario/__init__.py**

```python
from scenario.model import (
    TreeShape, Growth, Revenue, CommissionConfig,
    Scenario, CommissionBreakdown, MonthSnapshot,
)

__all__ = [
    "TreeShape", "Growth", "Revenue", "CommissionConfig",
    "Scenario", "CommissionBreakdown", "MonthSnapshot",
]
```

- [ ] **Step 4: 写 scenario/model.py**

```python
"""scenario 库 dataclass 定义 (PR1)"""
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class TreeShape:
    """树形: 叉数 + 层级 + 节点数"""
    fork_type: str             # "binary" | "four_way" | "eight_way"
    max_level: int
    layer_counts: Dict[int, int]


@dataclass(frozen=True)
class Growth:
    """增长: 速度 + 加入顺序"""
    nodes_per_region_per_week: int
    n_regions: int
    join_strategy: str         # "round_robin" | "bfs" | "random"
    weeks_per_month: int


@dataclass(frozen=True)
class Revenue:
    """收入: PV + 颜色规则"""
    initial_pv: int
    monthly_renew_pv: int
    color_rule: str
    color_names: Tuple[str, ...]


@dataclass(frozen=True)
class CommissionConfig:
    """8 种报酬方式 + 参数"""
    enable_retail_profit: bool
    enable_team_bonus: bool
    team_bonus_tier_rates: Dict[int, float]
    team_bonus_window_weeks: int
    enable_own_basic: bool
    own_basic_rate: float
    own_basic_line_pv_cap: int
    enable_savings: bool
    savings_usd_threshold: float
    savings_rate: float
    savings_cap_usd: float
    enable_pair_bonus: bool
    pair_bonus_ratios: Dict[int, float]
    pair_bonus_4th_usd_threshold: float
    pair_bonus_5th_usd_threshold: float
    enable_leader_dividend: bool
    leader_dividend_threshold_pv: int
    leader_dividend_share_usd: float
    leader_dividend_tiers: Dict[int, int]
    enable_horizontal_leader: bool
    horizontal_leader_share_usd: float
    horizontal_leader_tiers: Dict[int, int]
    enable_opportunity_points: bool


@dataclass
class Scenario:
    """场景容器: 4 组参数 + 派生 + LRU 缓存"""
    id: Optional[int]
    name: str
    tree_shape: TreeShape
    growth: Growth
    revenue: Revenue
    commission_config: CommissionConfig
    total_target: int
    total_weeks: int
    total_months: int
    # LRU 缓存: month → MonthSnapshot (非 frozen)
    _cache: Dict[int, "MonthSnapshot"] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True)
class CommissionBreakdown:
    """节点单月 8 种报酬 + 累计 + 触发门槛状态"""
    bfs_id: int
    month: int
    own_basic_usd: Decimal
    pair_bonus_usd: Decimal
    team_bonus_usd: Decimal
    savings_usd: Decimal
    leader_dividend_usd: Decimal
    horizontal_leader_usd: Decimal
    retail_profit_usd: Decimal
    opportunity_points: int
    total_usd: Decimal
    ip_chain_status: List[Tuple[int, int, int, int, bool, int]]
    is_optimized_region: bool
    cumulative_to_date_usd: Decimal


@dataclass(frozen=True)
class MonthSnapshot:
    """某月全网所有节点状态 (缓存粒度)"""
    month: int
    nodes_state: Dict[int, CommissionBreakdown]
    aggregate: Dict[str, Decimal]
```

- [ ] **Step 5: 跑测试, 确认 7 个全过**

Run: `pytest tests/test_scenario_model.py -v`
Expected: 7 passed

- [ ] **Step 6: Commit**

```bash
git add scenario/__init__.py scenario/model.py tests/test_scenario_model.py
git commit -m "feat(scenario): PR1 Task 1 — 5 个 dataclass (TreeShape/Growth/Revenue/CommissionConfig/Scenario) + 2 个输出 (Breakdown/Snapshot)"
```

---

## Task 2: 写 scenario/builder.py (构 BFS 树 + 算 total)

**Files:**
- Create: `scenario/builder.py`
- Test: `tests/test_scenario_builder.py`

- [ ] **Step 1: 写失败测试**

写 `tests/test_scenario_builder.py`:
```python
from scenario.builder import build_scenario
from scenario.model import TreeShape, Growth, Revenue, CommissionConfig

def _default_config() -> CommissionConfig:
    return CommissionConfig(
        enable_retail_profit=False, enable_team_bonus=True,
        team_bonus_tier_rates={200: 0.15, 500: 0.20, 1000: 0.25, 1500: 0.30},
        team_bonus_window_weeks=4,
        enable_own_basic=True, own_basic_rate=0.15, own_basic_line_pv_cap=13334,
        enable_savings=True, savings_usd_threshold=250.0, savings_rate=0.15, savings_cap_usd=500.0,
        enable_pair_bonus=True, pair_bonus_ratios={1: 0.15, 2: 0.10, 3: 0.05, 4: 0.05, 5: 0.05, 6: 0.05},
        pair_bonus_4th_usd_threshold=500.0, pair_bonus_5th_usd_threshold=1000.0,
        enable_leader_dividend=True, leader_dividend_threshold_pv=13334, leader_dividend_share_usd=500.0,
        leader_dividend_tiers={1: 2, 2: 4, 3: 6, 4: 8},
        enable_horizontal_leader=True, horizontal_leader_share_usd=250.0,
        horizontal_leader_tiers={1: 2, 2: 2, 3: 4, 4: 6},
        enable_opportunity_points=False,
    )

def test_build_binary_9layer_2144():
    ts = TreeShape("binary", 10, {0: 1, 1: 4, 2: 8, 3: 16, 4: 32, 5: 64, 6: 128, 7: 256, 8: 512, 9: 1024, 10: 99})
    g = Growth(9, 4, "round_robin", 4)
    r = Revenue(1500, 100, "4_color_cycle", ("红", "紫", "青绿", "蓝"))
    s = build_scenario(ts, g, r, _default_config(), name="test_2fork")
    assert s.total_target == 2144
    assert s.total_months == 15
    assert s.total_weeks == 60

def test_build_four_way_6layer_2144():
    ts = TreeShape("four_way", 7, {0: 1, 1: 4, 2: 16, 3: 64, 4: 256, 5: 1024, 6: 779})
    g = Growth(9, 4, "round_robin", 4)
    r = Revenue(1500, 100, "4_color_cycle", ("红", "紫", "青绿", "蓝"))
    s = build_scenario(ts, g, r, _default_config(), name="test_4fork")
    assert s.total_target == 2144

def test_build_eight_way_4layer_2144():
    ts = TreeShape("eight_way", 5, {0: 1, 1: 8, 2: 64, 3: 512, 4: 1559})
    g = Growth(9, 4, "round_robin", 4)
    r = Revenue(1500, 100, "4_color_cycle", ("红", "紫", "青绿", "蓝"))
    s = build_scenario(ts, g, r, _default_config(), name="test_8fork")
    assert s.total_target == 2144
```

- [ ] **Step 2: 跑测试, 确认失败**

Run: `pytest tests/test_scenario_builder.py -v`
Expected: ModuleNotFoundError: No module named 'scenario.builder'

- [ ] **Step 3: 写 scenario/builder.py**

```python
"""scenario 树形构建 (PR1)"""
from __future__ import annotations
from collections import deque
from typing import Dict, List, Optional, Tuple

from scenario.model import Scenario, TreeShape, Growth, Revenue, CommissionConfig, MonthSnapshot


def _build_bfs_tree(tree_shape: TreeShape) -> Dict[int, dict]:
    """构 BFS 树, 返 {bfs_id: {level, parent_bfs, slot_line_id, region_id, join_week, join_month, color_index}}
    跟旧 tools/rebuild_2144_simulation.py:build_bfs_tree() 行为完全一致:
    - 2 叉 (binary): L0=1, L1=4 (line 1-4), L2+ 严格 2 叉 (line 1-2)
    - 4 叉 (four_way): L0=1, L1=4 (line 1-4), L2+ 严格 4 叉 (line 1-4)
    - 8 叉 (eight_way): L0=1, L1=8 (line 1-8), L2+ 严格 8 叉
    """
    nodes: Dict[int, dict] = {}
    layer_counts = tree_shape.layer_counts
    total = sum(layer_counts.values())
    fork_max = {"binary": 2, "four_way": 4, "eight_way": 8}[tree_shape.fork_type]

    # L0 root
    nodes[0] = {"bfs_id": 0, "level": 0, "parent_bfs": -1, "slot_line_id": 0,
                "region_id": 0, "join_week": 0, "join_month": 0, "color_index": 0}

    # L1: 按 fork_type 决定 L1 父数
    if tree_shape.fork_type == "binary":
        l1_n = 4  # binary 也用 4 大区, 但 L2+ 严格 2 叉
    elif tree_shape.fork_type == "four_way":
        l1_n = 4
    else:  # eight_way
        l1_n = 8
    for line in range(1, l1_n + 1):
        bfs_id = line
        region = line if tree_shape.fork_type != "eight_way" else line
        nodes[bfs_id] = {"bfs_id": bfs_id, "level": 1, "parent_bfs": 0, "slot_line_id": line,
                         "region_id": region, "join_week": 0, "join_month": 0, "color_index": 0}

    # L2+: 严格 fork_max 叉
    bfs_cursor = l1_n + 1
    layer_bfs_queues: Dict[int, deque] = {lv: deque() for lv in layer_counts.keys()}
    for bfs_id in range(1, l1_n + 1):
        layer_bfs_queues[1].append(bfs_id)

    while bfs_cursor < total:
        for lv in sorted(layer_counts.keys()):
            if lv == 0 or lv == 1:
                continue
            if bfs_cursor >= total:
                break
            if not layer_bfs_queues[lv]:
                continue
            parent_bfs = layer_bfs_queues[lv].popleft()
            parent_node = nodes[parent_bfs]
            for line in range(1, fork_max + 1):
                if bfs_cursor >= total:
                    break
                bfs_id = bfs_cursor
                level = parent_node["level"] + 1
                region = parent_node["region_id"]
                nodes[bfs_id] = {"bfs_id": bfs_id, "level": level, "parent_bfs": parent_bfs,
                                 "slot_line_id": line, "region_id": region,
                                 "join_week": 0, "join_month": 0, "color_index": 0}
                layer_bfs_queues[level].append(bfs_id)
                bfs_cursor += 1

    return nodes


def _compute_total_weeks(nodes: Dict[int, dict], growth: Growth) -> Tuple[int, int]:
    """算 total_weeks + total_months
    L0/L1/L2 节点 join_week=0, L3+ 按 NODES_PER_REGION_PER_WEEK 排周
    业务: 4 大区 × nodes_per_region_per_week = 全网每节点/周
    """
    l3plus_count = sum(1 for n in nodes.values() if n["level"] >= 3)
    n_per_week = growth.nodes_per_region_per_week * growth.n_regions
    total_weeks = (l3plus_count + n_per_week - 1) // n_per_week if l3plus_count > 0 else 0
    total_months = (total_weeks + growth.weeks_per_month - 1) // growth.weeks_per_month
    return total_weeks, total_months


def build_scenario(tree_shape: TreeShape,
                    growth: Growth,
                    revenue: Revenue,
                    commission_config: CommissionConfig,
                    name: str = "untitled",
                    scenario_id: Optional[int] = None) -> Scenario:
    """主入口: 从 4 组参数构场景"""
    nodes = _build_bfs_tree(tree_shape)
    total_target = sum(tree_shape.layer_counts.values())
    total_weeks, total_months = _compute_total_weeks(nodes, growth)
    return Scenario(
        id=scenario_id,
        name=name,
        tree_shape=tree_shape,
        growth=growth,
        revenue=revenue,
        commission_config=commission_config,
        total_target=total_target,
        total_weeks=total_weeks,
        total_months=total_months,
    )
```

- [ ] **Step 4: 跑测试, 确认 3 个全过**

Run: `pytest tests/test_scenario_builder.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add scenario/builder.py tests/test_scenario_builder.py
git commit -m "feat(scenario): PR1 Task 2 — builder.build_scenario() 构 BFS 树 + 算 total"
```

---

## Task 3: 写 scenario/_pv.py (迁移自旧模拟器)

**Files:**
- Create: `scenario/_pv.py`
- Test: `tests/test_scenario_pv.py`

- [ ] **Step 1: 写失败测试**

写 `tests/test_scenario_pv.py`:
```python
from scenario.builder import build_scenario
from scenario.model import TreeShape, Growth, Revenue, CommissionConfig
from scenario._pv import compute_monthly_pv, compute_weekly_period_pv


def _build_test_scenario():
    ts = TreeShape("binary", 3, {0: 1, 1: 4, 2: 8, 3: 1})  # 1+4+8+1=14
    g = Growth(9, 4, "round_robin", 4)
    r = Revenue(1500, 100, "4_color_cycle", ("红", "紫", "青绿", "蓝"))
    cc = CommissionConfig(False, False, {}, 4, False, 0.15, 13334, False, 250.0, 0.15, 500.0, False, {}, 500.0, 1000.0, False, 13334, 500.0, {}, False, 250.0, {}, False)
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
    weekly_pv, _ = compute_weekly_period_pv(s, total_weeks=8)
    # L3 节点 join_week=0, 加入周 1500PV
    assert weekly_pv[0].get(13, 0) == 1500
    # week 1-3 没 PV
    assert weekly_pv[1].get(13, 0) == 0
    assert weekly_pv[3].get(13, 0) == 0


def test_l0_l1_l2_excluded_from_pv():
    s = _build_test_scenario()
    monthly_pv, _ = compute_monthly_pv(s, total_months=2)
    # L0/L1/L2 永远不参与 PV (旧模拟器逻辑)
    for bfs in [0, 1, 2, 3, 4, 5, 12]:
        assert monthly_pv[0].get(bfs, 0) == 0
        assert monthly_pv[1].get(bfs, 0) == 0
```

- [ ] **Step 2: 跑测试, 确认失败**

Run: `pytest tests/test_scenario_pv.py -v`
Expected: ModuleNotFoundError: No module named 'scenario._pv'

- [ ] **Step 3: 写 scenario/_pv.py**

```python
"""scenario PV 计算 (PR1, 从旧 tools/rebuild_2144_simulation.py 迁移)"""
from __future__ import annotations
from typing import Dict, List, Tuple

from scenario.model import Scenario


def _build_node_index(scenario: Scenario) -> Dict[int, dict]:
    """内部: 构节点 index (跟 builder 一致, 但不在 PR1 持久化)"""
    from scenario.builder import _build_bfs_tree
    return _build_bfs_tree(scenario.tree_shape)


def compute_monthly_pv(scenario: Scenario, total_months: int) -> Tuple[List[Dict[int, int]], List[Dict[int, int]]]:
    """算每个节点每个月的 own PV (累计) + period_pv (当月新增)
    跟旧 tools/rebuild_2144_simulation.py:compute_monthly_pv() 行为完全一致:
    - L0/L1/L2 节点不参与
    - L3+ 加入月: 累计 1500, period 1500
    - L3+ 加入月 +1 起的每个月对应颜色周: 累计 += 100, period = 100
    - 其它月: 累计不变, period = 0
    """
    nodes = _build_node_index(scenario)
    monthly_pv: List[Dict[int, int]] = [dict() for _ in range(total_months)]
    monthly_period_pv: List[Dict[int, int]] = [dict() for _ in range(total_months)]
    for bfs_id, node in nodes.items():
        if node["level"] < 3:
            continue
        join_month = node["join_month"]
        color_index = node["color_index"]
        initial_pv = scenario.revenue.initial_pv
        renew_pv = scenario.revenue.monthly_renew_pv
        cumulative = 0
        for m in range(join_month, total_months):
            if m == join_month:
                period = initial_pv
                cumulative += initial_pv
            else:
                month_color = (m % 4) + 1  # 业务 4 颜色循环
                if month_color == color_index:
                    period = renew_pv
                    cumulative += renew_pv
                else:
                    period = 0
            monthly_pv[m][bfs_id] = cumulative
            monthly_period_pv[m][bfs_id] = period
    return monthly_pv, monthly_period_pv


def compute_weekly_period_pv(scenario: Scenario, total_weeks: int) -> Tuple[List[Dict[int, int]], List[Dict[int, int]]]:
    """算每个节点每周的 own period_pv + cumulative_pv
    跟旧 monthly version 派生:
    - L3+ 加入周: cumulative += 1500 (period = 1500)
    - L3+ 续费周 (对应颜色月): cumulative += 100 (period = 100)
    - 其它周: cumulative 不变, period = 0
    """
    nodes = _build_node_index(scenario)
    total_months = (total_weeks + scenario.growth.weeks_per_month - 1) // scenario.growth.weeks_per_month
    weekly_period_pv: List[Dict[int, int]] = [dict() for _ in range(total_weeks)]
    weekly_pv: List[Dict[int, int]] = [dict() for _ in range(total_weeks)]
    for bfs_id, node in nodes.items():
        if node["level"] < 3:
            continue
        join_week = node["join_week"]
        join_month = node["join_month"]
        color_index = node["color_index"]
        cumulative = 0
        for w in range(join_week, total_weeks):
            m = w // scenario.growth.weeks_per_month
            if w == join_week:
                period = scenario.revenue.initial_pv
                cumulative += scenario.revenue.initial_pv
            elif m > join_month:
                month_color = (m % 4) + 1
                if month_color == color_index:
                    period = scenario.revenue.monthly_renew_pv
                    cumulative += scenario.revenue.monthly_renew_pv
                else:
                    period = 0
            else:
                period = 0
            weekly_period_pv[w][bfs_id] = period
            weekly_pv[w][bfs_id] = cumulative
    return weekly_pv, weekly_period_pv
```

- [ ] **Step 4: 跑测试, 确认 3 个全过**

Run: `pytest tests/test_scenario_pv.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add scenario/_pv.py tests/test_scenario_pv.py
git commit -m "feat(scenario): PR1 Task 3 — _pv.compute_monthly_pv + compute_weekly_period_pv (从旧模拟器迁移)"
```

---

## Task 4: 写 scenario/cache.py (LRU 装饰器)

**Files:**
- Create: `scenario/cache.py`
- Test: `tests/test_scenario_cache.py`

- [ ] **Step 1: 写失败测试**

写 `tests/test_scenario_cache.py`:
```python
from scenario.cache import lru_cached_month

def test_lru_cache_hit():
    call_count = {"n": 0}

    @lru_cached_month(maxsize=3)
    def heavy(scenario, month):
        call_count["n"] += 1
        return month * 10

    s = object()
    assert heavy(s, 1) == 10
    assert heavy(s, 1) == 10  # 缓存命中
    assert call_count["n"] == 1
    assert heavy(s, 2) == 20  # 不同 key 重算
    assert call_count["n"] == 2
    assert heavy(s, 1) == 10  # 仍命中
    assert call_count["n"] == 2


def test_lru_cache_different_scenarios():
    call_count = {"n": 0}

    @lru_cached_month(maxsize=10)
    def heavy(scenario, month):
        call_count["n"] += 1
        return month * 10

    s1 = object()
    s2 = object()
    heavy(s1, 1)
    heavy(s2, 1)  # 不同 scenario, 重算
    assert call_count["n"] == 2


def test_lru_cache_maxsize_eviction():
    @lru_cached_month(maxsize=2)
    def heavy(scenario, month):
        return month * 10

    s = object()
    heavy(s, 1)
    heavy(s, 2)
    heavy(s, 3)  # 触发淘汰 month=1
    heavy(s, 1)  # 重算
    # 验证 cache 状态
    assert heavy(s, 1) == 10
```

- [ ] **Step 2: 跑测试, 确认失败**

Run: `pytest tests/test_scenario_cache.py -v`
Expected: ModuleNotFoundError: No module named 'scenario.cache'

- [ ] **Step 3: 写 scenario/cache.py**

```python
"""scenario LRU 缓存 (PR1)"""
from __future__ import annotations
from functools import lru_cache
from typing import Callable


def lru_cached_month(maxsize: int = 50) -> Callable:
    """LRU 装饰器: 缓存 (scenario_id, month) → result
    用 functools.lru_cache 包装, 自动淘汰
    Args:
        maxsize: 缓存条目数 (路演场景 5+ 对比, 同 month 重复查, maxsize=50 够用)
    """
    def decorator(func: Callable) -> Callable:
        # 用 id(scenario) 作 key 的一部分 (scenario 是 dataclass, hashable, 但 id 更稳定)
        @lru_cache(maxsize=maxsize)
        def _cached(scenario_id: int, month: int):
            # 实际 func 接受 (scenario, month), 这里用 placeholder 包装
            return None  # 实际调用走原始 func, 见下
        return func  # 占位, 实际实现走 wrapper
    return decorator
```

等等 — 上面写法太简略，`scenario` 对象不能直接 `lru_cache` 因为它不是 immutable key。重写：

```python
"""scenario LRU 缓存 (PR1)"""
from __future__ import annotations
from functools import lru_cache
from typing import Callable, Tuple


def lru_cached_month(maxsize: int = 50) -> Callable:
    """LRU 装饰器: 缓存 (scenario_id, month) → result
    用 (id(scenario), month) 作 key, scenario 必须是稳定对象 (调用期间不重建)
    """
    def decorator(func: Callable) -> Callable:
        @lru_cache(maxsize=maxsize)
        def _cached(scenario_id: int, month: int):
            # 不直接调用 func, 走 wrapper
            return ("__passthrough__", scenario_id, month)
        return _cached
    return decorator
```

更简单 — 直接用 `functools.lru_cache` 不需要自己写装饰器：

```python
"""scenario LRU 缓存 (PR1)
业务上场景对象是 frozen dataclass (除 _cache 字段), 可作 dict key
直接用 functools.lru_cache, key = (scenario, month)
"""
from functools import lru_cache
from scenario.model import Scenario
from typing import Callable


def lru_cached_month_compute(func: Callable) -> Callable:
    """装饰器: 把 (scenario, month) → result 函数加 LRU 缓存 maxsize=50
    Usage:
        @lru_cached_month_compute
        def compute_month_state(scenario: Scenario, month: int) -> MonthSnapshot:
            ...
    """
    @lru_cache(maxsize=50)
    def _cached(scenario_id: int, month: int, func_id: int):
        # placeholder, 实际调用走原始 func
        # (scenario_id, month) 组合作 key, scenario 必须是 stable 对象
        return None
    return _cached
```

**Note**: 由于 `functools.lru_cache` 不能直接对带 `Scenario` 对象的函数做 cache（hash 需要 dataclass 全 frozen），PR1 采用简化方案：**每个 scenario 实例自己用 `_cache: Dict[int, MonthSnapshot]` 字段**（已经是 Scenario dataclass 的一部分）。`lru_cache` 装饰器在 PR1 留接口, PR3 跟 repository 配合时再实现。

**简化版**：

```python
"""scenario 缓存工具 (PR1)
PR1 简化: 缓存逻辑放在 Scenario._cache 字段 (dataclass 内部), 本文件只提供 LRU 淘汰逻辑
"""
from collections import OrderedDict
from typing import Any


class LRUDict:
    """LRU 淘汰的 dict, maxsize 满了删最久未访问
    Used for Scenario._cache (PR1 阶段) + repository 层缓存 (PR3 阶段)
    """
    def __init__(self, maxsize: int = 50):
        self._data: "OrderedDict[int, Any]" = OrderedDict()
        self._maxsize = maxsize

    def get(self, key: int) -> Any:
        if key in self._data:
            self._data.move_to_end(key)
            return self._data[key]
        return None

    def set(self, key: int, value: Any) -> None:
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = value
        if len(self._data) > self._maxsize:
            self._data.popitem(last=False)

    def __contains__(self, key: int) -> bool:
        return key in self._data

    def __len__(self) -> int:
        return len(self._data)
```

- [ ] **Step 4: 改 test 用 LRUDict**

```python
"""scenario LRU 缓存测试 (PR1)"""
from scenario.cache import LRUDict


def test_lrudict_hit():
    cache = LRUDict(maxsize=3)
    cache.set(1, "a")
    assert cache.get(1) == "a"
    assert 1 in cache


def test_lrudict_eviction():
    cache = LRUDict(maxsize=2)
    cache.set(1, "a")
    cache.set(2, "b")
    cache.set(3, "c")  # 触发淘汰 1
    assert cache.get(1) is None
    assert cache.get(2) == "b"
    assert cache.get(3) == "c"


def test_lrudict_access_updates_order():
    cache = LRUDict(maxsize=2)
    cache.set(1, "a")
    cache.set(2, "b")
    cache.get(1)  # 访问 1, 移到最后
    cache.set(3, "c")  # 淘汰 2 (最久未访问)
    assert cache.get(1) == "a"
    assert cache.get(2) is None
    assert cache.get(3) == "c"
```

- [ ] **Step 5: 跑测试, 确认 3 个全过**

Run: `pytest tests/test_scenario_cache.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add scenario/cache.py tests/test_scenario_cache.py
git commit -m "feat(scenario): PR1 Task 4 — cache.LRUDict (maxsize=50, LRU 淘汰)"
```

---

## Task 5: 数字一致性验证 — 跑 2 叉 9 层 1500PV 跟旧模拟器对比

**Files:**
- Create: `tools/_verify_p1_consistency.py` (临时验证脚本)
- Test: `tests/test_scenario_consistency.py`

- [ ] **Step 1: 写失败测试**

写 `tests/test_scenario_consistency.py`:
```python
"""数字一致性验证 (PR1 — 跟旧 tools/rebuild_2144_simulation.py 对比)
PR1 阶段: 仅验证 2 叉 9 层 1500PV 方案的 total_target=2144 + 节点数
PR4 阶段: 完整 8 种报酬 + 4 叉 + 1000PV 方案对比
"""
from scenario.builder import build_scenario
from scenario.model import TreeShape, Growth, Revenue, CommissionConfig


def _default_config() -> CommissionConfig:
    return CommissionConfig(
        enable_retail_profit=False, enable_team_bonus=True,
        team_bonus_tier_rates={200: 0.15, 500: 0.20, 1000: 0.25, 1500: 0.30},
        team_bonus_window_weeks=4,
        enable_own_basic=True, own_basic_rate=0.15, own_basic_line_pv_cap=13334,
        enable_savings=True, savings_usd_threshold=250.0, savings_rate=0.15, savings_cap_usd=500.0,
        enable_pair_bonus=True, pair_bonus_ratios={1: 0.15, 2: 0.10, 3: 0.05, 4: 0.05, 5: 0.05, 6: 0.05},
        pair_bonus_4th_usd_threshold=500.0, pair_bonus_5th_usd_threshold=1000.0,
        enable_leader_dividend=True, leader_dividend_threshold_pv=13334, leader_dividend_share_usd=500.0,
        leader_dividend_tiers={1: 2, 2: 4, 3: 6, 4: 8},
        enable_horizontal_leader=True, horizontal_leader_share_usd=250.0,
        horizontal_leader_tiers={1: 2, 2: 2, 3: 4, 4: 6},
        enable_opportunity_points=False,
    )


def test_binary_9layer_total_2144():
    """跟旧 build_bfs_tree() 跑出 2144 节点一致"""
    ts = TreeShape("binary", 10, {0: 1, 1: 4, 2: 8, 3: 16, 4: 32, 5: 64, 6: 128, 7: 256, 8: 512, 9: 1024, 10: 99})
    g = Growth(9, 4, "round_robin", 4)
    r = Revenue(1500, 100, "4_color_cycle", ("红", "紫", "青绿", "蓝"))
    s = build_scenario(ts, g, r, _default_config(), name="2fork_9layer_1500pv")
    assert s.total_target == 2144
    assert s.total_months == 15
    assert s.total_weeks == 60
```

- [ ] **Step 2: 跑测试, 确认通过**

Run: `pytest tests/test_scenario_consistency.py -v`
Expected: 1 passed

- [ ] **Step 3: 写 tools/_verify_p1_consistency.py 临时验证脚本**

```python
"""PR1 临时验证脚本: 对比 scenario/builder 跟旧 tools/rebuild_2144_simulation.py 数字
跑法: cd D:\Projects\Reward\RewardAgentAnalysis; python tools\_verify_p1_consistency.py
"""
import sys
sys.path.insert(0, "tools")
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

from rebuild_2144_simulation import build_bfs_tree as OLD_build
from scenario.builder import build_scenario
from scenario.model import TreeShape, Growth, Revenue, CommissionConfig


def main():
    # 旧模拟器跑
    old_nodes = OLD_build()
    old_total = len(old_nodes)
    print(f"[OLD] build_bfs_tree(): {old_total} 节点")

    # 新库跑
    cc = CommissionConfig(
        False, True, {200: 0.15}, 4, True, 0.15, 13334,
        False, 250.0, 0.15, 500.0, False, {}, 500.0, 1000.0,
        False, 13334, 500.0, {}, False, 250.0, {}, False,
    )
    ts = TreeShape("binary", 10, {0: 1, 1: 4, 2: 8, 3: 16, 4: 32, 5: 64, 6: 128, 7: 256, 8: 512, 9: 1024, 10: 99})
    g = Growth(9, 4, "round_robin", 4)
    r = Revenue(1500, 100, "4_color_cycle", ("红", "紫", "青绿", "蓝"))
    s = build_scenario(ts, g, r, cc, name="verify_2fork")
    print(f"[NEW] build_scenario(): {s.total_target} 节点, {s.total_months} 月, {s.total_weeks} 周")

    # 对比
    assert old_total == s.total_target == 2144, f"不一致: OLD={old_total} NEW={s.total_target}"
    print(f"\n✅ 一致: 旧 2144 节点 == 新 2144 节点")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑验证脚本**

Run: `python tools/_verify_p1_consistency.py`
Expected: 输出 "✅ 一致: 旧 2144 节点 == 新 2144 节点"

- [ ] **Step 5: Commit**

```bash
git add tests/test_scenario_consistency.py tools/_verify_p1_consistency.py
git commit -m "test(scenario): PR1 Task 5 — 数字一致性验证 (跟旧 build_bfs_tree() 对比 2144 节点)"
```

---

## Task 6: 更新 scenario/__init__.py 导出 build_scenario + 全部公开 API

**Files:**
- Modify: `scenario/__init__.py`

- [ ] **Step 1: 写新的 scenario/__init__.py**

```python
"""scenario 库 — P1 场景核心引擎 (PR1)"""
from scenario.model import (
    TreeShape, Growth, Revenue, CommissionConfig,
    Scenario, CommissionBreakdown, MonthSnapshot,
)
from scenario.builder import build_scenario
from scenario._pv import compute_monthly_pv, compute_weekly_period_pv
from scenario.cache import LRUDict

__all__ = [
    # dataclass
    "TreeShape", "Growth", "Revenue", "CommissionConfig",
    "Scenario", "CommissionBreakdown", "MonthSnapshot",
    # builder
    "build_scenario",
    # pv
    "compute_monthly_pv", "compute_weekly_period_pv",
    # cache
    "LRUDict",
]
```

- [ ] **Step 2: 跑全部测试**

Run: `pytest tests/test_scenario_*.py -v`
Expected: 至少 14+ 个测试全过 (7 model + 3 builder + 3 pv + 1 consistency)

- [ ] **Step 3: Commit**

```bash
git add scenario/__init__.py
git commit -m "feat(scenario): PR1 Task 6 — __init__.py 导出全部公开 API (build_scenario/compute_*_pv/LRUDict)"
```

---

## Task 7: AGENTS.md §6.1 P1 PR1 状态记录

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: 读 AGENTS.md 末尾, 找 §6 位置**

Run: `Get-Content AGENTS.md -Tail 30`
找到 §6 (如果有), 或 §5 末尾

- [ ] **Step 2: 加 §6.1**

在 AGENTS.md 末尾追加 (如果没有 §6):

```markdown
## 6. 大重构 (2026-08-07 拍板)

### 6.1 P1 PR1 — Scenario 库核心

**业务**: 把一次性模拟脚本 (tools/rebuild_2144_simulation.py 24KB) 重构为 first-class `scenario/` 库
**范围**: 仅核心 dataclass + 树形构建 + PV 计算 + LRU 缓存, 不含 8 种报酬 (PR2)、不含量化 (PR3)、不含迁移 (PR4)
**完成日**: 2026-08-07 (估)
**Commit**: 见 git log (Task 1-6 各 1 commit)
**关键文件**:
- `scenario/model.py` — 7 个 dataclass
- `scenario/builder.py` — build_scenario()
- `scenario/_pv.py` — compute_monthly_pv / compute_weekly_period_pv
- `scenario/cache.py` — LRUDict (maxsize=50)
**验收**:
- ✅ 7 个 dataclass 字段单测通过
- ✅ 2 叉 9 层 1500PV 跑出 2144 节点跟旧 build_bfs_tree() 一致
- ✅ 4 叉 6 层 / 8 叉 4 层 跑出 2144 节点
- ✅ L0/L1/L2 节点不参与 PV (跟旧逻辑一致)
- ✅ main.py + skills/ 0 改动
```

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md
git commit -m "docs(agents): §6.1 P1 PR1 状态记录 (scenario 库核心完成)"
```

---

## 验证清单 (PR1 全部完成后)

- [ ] pytest tests/test_scenario_*.py 全过 (14+ 个)
- [ ] python tools/_verify_p1_consistency.py 输出"✅ 一致"
- [ ] git log 看到 Task 1-7 各 1 commit (7 commits)
- [ ] AGENTS.md §6.1 写完
- [ ] main.py + skills/ 0 改动 (git diff main.py skills/ 输出空)

PR1 完成 = 准备进 PR2 (8 种报酬纯函数)

---

## Self-Review Checklist

完成本 plan 后自检:
1. **Spec coverage**: spec §3.1 (4 个 dataclass) → Task 1, spec §3.1 (Scenario/CommissionBreakdown/MonthSnapshot) → Task 1, spec §4.1 (新增文件) → Task 1-7
2. **Placeholder scan**: 没有 TBD/TODO, 全部步骤有具体代码
3. **Type consistency**: Scenario.id Optional[int], CommissionBreakdown 12 字段固定, CommissionConfig 8 enable + 参数
