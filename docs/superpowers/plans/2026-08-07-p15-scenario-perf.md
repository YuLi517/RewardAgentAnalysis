# P1.5 性能优化 Implementation Plan

**Goal:** 把 `GET /api/scenarios/{id}/overview/all?total_months=14` 14 月 × 8 报酬 矩阵 端点从 14 分钟降到 10 秒内, 0 后端接口改动.

**Architecture:** 4 项全量优化叠加 (table_for_month + LRU + ThreadPoolExecutor + 性能基准).

**Tech Stack:** 复用栈 (Python 3.14 + FastAPI + SQLAlchemy), `concurrent.futures.ThreadPoolExecutor` (内置, 0 新依赖).

**Spec:** `docs/superpowers/specs/2026-08-07-p15-scenario-perf-design.md`

---

## File Structure (P1.5 改动)

| 文件 | 责任 | 改/新增 |
|---|---|---|
| `scenario/commission/team_bonus.py` | 加 `compute_team_bonus_table_for_month` | 改 |
| `scenario/commission/savings.py` | 加 `compute_savings_table_for_month` | 改 |
| `scenario/commission/leader.py` | 加 `compute_leader_dividend_table_for_month` | 改 |
| `scenario/commission/horizontal.py` | 加 `compute_horizontal_table_for_month` | 改 |
| `scenario/commission/retail_profit.py` | 加 `compute_retail_profit_table_for_month` | 改 |
| `scenario/commission/opportunity.py` | 加 `compute_opportunity_table_for_month` | 改 |
| `scenario/breakdown.py` | `compute_commission_breakdown` 改用 8 张表 | 改 |
| `scenario/_month_snapshot.py` | 新建 MonthSnapshot dataclass | 新 |
| `scenario/model.py` | Scenario._cache 改用 LRUDict[MonthSnapshot] | 改 |
| `scenario/overview.py` | `compute_month_overview` 改用 LRUDict 缓存 | 改 |
| `scenario/parallel.py` | 新建 ThreadPoolExecutor 14 worker 并行 | 新 |
| `scenario_routes.py` | `/overview/all` 改调 `compute_overview_all_parallel` | 改 |
| `tests/test_p15_perf.py` | 性能基准 3 测试 | 新 |
| `AGENTS.md` | §6.10 P1.5 状态 | 改 |

---

## Task 1: spec (DONE)

**Files:**
- Create: `docs/superpowers/specs/2026-08-07-p15-scenario-perf-design.md`

- [x] **Step 1: 写 spec** (15KB, 10 章节, 2 决策拍板)
- [x] **Step 2: Commit** (b04debd)

---

## Task 2: 6 个 table_for_month 全网表 + breakdown 改用 8 张表

**Files:**
- Modify: `scenario/commission/team_bonus.py`
- Modify: `scenario/commission/savings.py`
- Modify: `scenario/commission/leader.py`
- Modify: `scenario/commission/horizontal.py`
- Modify: `scenario/commission/retail_profit.py`
- Modify: `scenario/commission/opportunity.py`
- Modify: `scenario/breakdown.py`

- [ ] **Step 1: 看现有 6 个单节点函数实现 (跟 own_basic 模式对齐)**

```bash
Get-Content scenario/commission/team_bonus.py
Get-Content scenario/commission/savings.py
Get-Content scenario/commission/leader.py
Get-Content scenario/commission/horizontal.py
Get-Content scenario/commission/retail_profit.py
Get-Content scenario/commission/opportunity.py
```

模式参考 (own_basic.py:31-81):
- 1 次后序遍历算 subtree_pv_table
- 1 次遍历算所有节点
- LRU 缓存 (`compute_own_basic_table_for_month._cache`)

- [ ] **Step 2: 给 6 个函数加 `*_table_for_month` 全网表 (跟 own_basic 模式一致)**

每个函数加:
```python
def compute_xxx_table_for_month(scenario, month) -> Dict[int, Decimal]:
    """1 次后序遍历算全网 2144 节点 xxx, 跟 own_basic_table_for_month 模式一致"""
    cache_key = ("xxx_table", id(scenario), month)
    if not hasattr(compute_xxx_table_for_month, "_cache"):
        compute_xxx_table_for_month._cache = {}
    cache = compute_xxx_table_for_month._cache
    if cache_key in cache:
        return cache[cache_key]

    nodes = _build_bfs_tree(scenario.tree_shape)
    # ... 1 次遍历算全网
    result = {...}
    cache[cache_key] = result
    return result
```

- [ ] **Step 3: `scenario/breakdown.py` `compute_commission_breakdown` 改用 8 张表**

```python
def compute_commission_breakdown(scenario, bfs_id, month):
    cc = scenario.commission_config

    # 1. 算全网 ownBasic (已有 table)
    own_basic_dict = compute_own_basic_table_for_month(scenario, month)
    own_basic = own_basic_dict.get(bfs_id, Decimal("0"))

    # 2. pair_bonus 分布表 (已有)
    if cc.enable_pair_bonus:
        pair_bonus_table = _compute_pair_bonus_table(scenario, month, own_basic_dict)
        pair_bonus = pair_bonus_table.get(bfs_id, Decimal("0"))
    else:
        pair_bonus = Decimal("0")

    # 3-8. 6 个单节点函数 → 6 个 table 查询 (新)
    if cc.enable_team_bonus:
        team_bonus_dict = compute_team_bonus_table_for_month(scenario, month)
        team_bonus = team_bonus_dict.get(bfs_id, Decimal("0"))
    else:
        team_bonus = Decimal("0")
    # ... savings / leader / horizontal / retail / opportunity 同样

    total = own_basic + pair_bonus + team_bonus + savings + leader + horiz + retail + Decimal(points)
    return CommissionBreakdown(...)
```

- [ ] **Step 4: 跑测试 (跟 PR2 round 3 数字一致, 0 回归)**

```powershell
cd D:\Projects\Reward\RewardAgentAnalysis
python -m pytest tests/test_scenario_builder.py tests/test_scenario_pv.py tests/test_scenario_cache.py tests/test_scenario_consistency.py tests/test_scenario_model.py tests/test_commission_own_basic.py tests/test_pr2_root_consistency.py tests/test_db_admin.py 2>&1 | Select-Object -Last 5
```

期望: 全部 pass, 数字跟 PR2 round 3 4 函数对齐版一致.

- [ ] **Step 5: Commit**

```bash
git add scenario/commission/ scenario/breakdown.py
git commit -m "feat(scenario): P1.5 Task 2 — 6 个 table_for_month 全网表 + breakdown 改用 8 张表 (跟 own_basic 模式对齐)"
```

---

## Task 3: MonthSnapshot + LRU 月级缓存

**Files:**
- Create: `scenario/_month_snapshot.py`
- Modify: `scenario/model.py`
- Modify: `scenario/overview.py`

- [ ] **Step 1: 新建 `scenario/_month_snapshot.py` (~50 行)**

```python
"""P1.5: MonthSnapshot dataclass — 某月 8 报酬全网表 + 总览 (缓存精度)"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict


@dataclass(frozen=True)
class MonthSnapshot:
    """某月 8 报酬全网表 (缓存精度, 算 1 次存 LRU)

    业务 (P1.5):
    - 1 MonthSnapshot ≈ 280KB (2144 节点 × 8 表 × 16 字节)
    - LRU maxsize=15, 14 月全缓存 + 1 预热
    - 第 2 次查询 0 延迟 (LRU 命中)
    """
    month: int
    own_basic_table: Dict[int, Decimal]
    pair_bonus_table: Dict[int, Decimal]
    team_bonus_table: Dict[int, Decimal]
    savings_table: Dict[int, Decimal]
    leader_table: Dict[int, Decimal]
    horizontal_table: Dict[int, Decimal]
    retail_table: Dict[int, Decimal]
    opportunity_table: Dict[int, int]
    # 总览 (8 报酬合计), 算 1 次存, 避免重复 sum
    overview: Dict[str, Decimal]


def build_month_snapshot(scenario, month) -> MonthSnapshot:
    """算 month 月 8 张表 + 总览, 1 次算 1 个 MonthSnapshot"""
    from scenario.commission.own_basic import compute_own_basic_table_for_month
    from scenario.commission.pair_bonus import compute_ancestor_share_dict
    from scenario.commission.team_bonus import compute_team_bonus_table_for_month
    from scenario.commission.savings import compute_savings_table_for_month
    from scenario.commission.leader import compute_leader_dividend_table_for_month
    from scenario.commission.horizontal import compute_horizontal_table_for_month
    from scenario.commission.retail_profit import compute_retail_profit_table_for_month
    from scenario.commission.opportunity import compute_opportunity_table_for_month

    cc = scenario.commission_config
    own_basic_table = compute_own_basic_table_for_month(scenario, month) if cc.enable_own_basic else {}
    pair_bonus_table = compute_ancestor_share_dict(scenario, own_basic_table) if cc.enable_pair_bonus else {}
    team_bonus_table = compute_team_bonus_table_for_month(scenario, month) if cc.enable_team_bonus else {}
    savings_table = compute_savings_table_for_month(scenario, month) if cc.enable_savings else {}
    leader_table = compute_leader_dividend_table_for_month(scenario, month) if cc.enable_leader_dividend else {}
    horizontal_table = compute_horizontal_table_for_month(scenario, month) if cc.enable_horizontal_leader else {}
    retail_table = compute_retail_profit_table_for_month(scenario, month) if cc.enable_retail_profit else {}
    opportunity_table = compute_opportunity_table_for_month(scenario, month) if cc.enable_opportunity_points else {}

    # 算总览 (8 报酬合计)
    from collections import defaultdict
    aggregate = defaultdict(lambda: Decimal("0"))
    from scenario.builder import _build_bfs_tree
    nodes = _build_bfs_tree(scenario.tree_shape)
    for bfs_id in nodes.keys():
        aggregate["ownBasic"] += own_basic_table.get(bfs_id, Decimal("0"))
        aggregate["pairBonus"] += pair_bonus_table.get(bfs_id, Decimal("0"))
        aggregate["teamBonus"] += team_bonus_table.get(bfs_id, Decimal("0"))
        aggregate["savings"] += savings_table.get(bfs_id, Decimal("0"))
        aggregate["leader"] += leader_table.get(bfs_id, Decimal("0"))
        aggregate["horizontal"] += horizontal_table.get(bfs_id, Decimal("0"))
        aggregate["retail"] += retail_table.get(bfs_id, Decimal("0"))
    aggregate["total"] = sum([aggregate["ownBasic"], aggregate["pairBonus"], aggregate["teamBonus"],
                              aggregate["savings"], aggregate["leader"], aggregate["horizontal"],
                              aggregate["retail"]], Decimal("0"))

    return MonthSnapshot(
        month=month,
        own_basic_table=own_basic_table,
        pair_bonus_table=pair_bonus_table,
        team_bonus_table=team_bonus_table,
        savings_table=savings_table,
        leader_table=leader_table,
        horizontal_table=horizontal_table,
        retail_table=retail_table,
        opportunity_table=opportunity_table,
        overview=dict(aggregate),
    )
```

- [ ] **Step 2: `scenario/model.py` Scenario._cache 改用 LRUDict[MonthSnapshot] maxsize=15**

```python
from scenario.cache import LRUDict

@dataclass
class Scenario:
    # ... 已有字段
    _cache: "LRUDict[int, MonthSnapshot]" = field(
        default_factory=lambda: LRUDict(maxsize=15), repr=False, compare=False
    )
```

- [ ] **Step 3: `scenario/overview.py` `compute_month_overview` 改用 LRUDict 缓存**

```python
from scenario._month_snapshot import build_month_snapshot

def compute_month_overview(scenario, month) -> Dict[str, Decimal]:
    """当月全网 8 种报酬合计 (P1.5: LRU 缓存)"""
    # 1. 查 LRU
    snap = scenario._cache.get(month)
    if snap is not None:
        return snap.overview
    # 2. 没缓存: 1 次算 MonthSnapshot
    snap = build_month_snapshot(scenario, month)
    scenario._cache.set(month, snap)
    return snap.overview
```

- [ ] **Step 4: 跑测试 (0 回归)**

```powershell
python -m pytest tests/test_scenario_builder.py tests/test_scenario_pv.py tests/test_scenario_cache.py tests/test_scenario_consistency.py tests/test_scenario_model.py tests/test_commission_own_basic.py tests/test_pr2_root_consistency.py tests/test_db_admin.py 2>&1 | Select-Object -Last 5
```

期望: 全部 pass, 数字跟 PR2 round 3 一致.

- [ ] **Step 5: Commit**

```bash
git add scenario/_month_snapshot.py scenario/model.py scenario/overview.py
git commit -m "feat(scenario): P1.5 Task 3 — MonthSnapshot + LRU 月级缓存 (Scenario._cache LRUDict maxsize=15, 2 次查询 0 延迟)"
```

---

## Task 4: ThreadPoolExecutor 14 月并行 + routes 改用

**Files:**
- Create: `scenario/parallel.py`
- Modify: `scenario_routes.py`

- [ ] **Step 1: 新建 `scenario/parallel.py` (~60 行)**

```python
"""P1.5: ThreadPoolExecutor 14 worker 并行算 14 月 × 8 报酬 矩阵

业务:
- 14 worker 同时算 14 月, 受 GIL 但 IO 释放能并行
- 14 月 × 5s / 5 = 1s, 总 < 10s
- 跟 compute_overview_all 行为一致, 仅并发
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List

from scenario.model import Scenario
from scenario.overview import compute_month_overview

# 模块级 executor, 跨请求复用 (避免每请求启停 worker)
_executor = ThreadPoolExecutor(max_workers=14, thread_name_prefix="p15-month-")


def compute_overview_all_parallel(scenario: Scenario, total_months: int = 14) -> Dict[str, any]:
    """14 月 × 8 报酬 矩阵, 14 worker 并行算

    Returns:
        {
            "total_months": 14,
            "fields": ["ownBasic", "pairBonus", ...],
            "months": [0, 1, ..., 14],
            "matrix": {"ownBasic": ["$0.00", ...], ...}
        }
    """
    fields = ["ownBasic", "pairBonus", "teamBonus", "savings",
              "leader", "horizontal", "retail", "total"]
    months = list(range(0, total_months + 1))
    matrix: Dict[str, list] = {f: [None] * (total_months + 1) for f in fields}

    def compute_one_month(m):
        return m, compute_month_overview(scenario, month=m)

    # 14 worker 并行 (LRU 缓存命中, 实际只算 1 次)
    futures = [_executor.submit(compute_one_month, m) for m in months]
    for f in as_completed(futures):
        m, overview = f.result()
        for field in fields:
            matrix[field][m] = str(overview.get(field, "0"))

    return {
        "total_months": total_months,
        "fields": fields,
        "months": months,
        "matrix": matrix,
    }
```

- [ ] **Step 2: `scenario_routes.py` /overview/all 改用并行**

```python
from scenario.parallel import compute_overview_all_parallel

@router.get("/{scenario_id}/overview/all")
def get_overview_all(scenario_id, total_months=Query(14, ge=1, le=15), db=Depends(get_db)):
    repo = ScenarioRepository(db)
    s = repo.load(scenario_id)
    if s is None: raise HTTPException(404)
    # P1.5: ThreadPoolExecutor 14 worker 并行 (从 14 分钟 → 10 秒)
    return compute_overview_all_parallel(s, total_months)
```

- [ ] **Step 3: 跑测试 (0 回归 + 性能跟之前一致)**

```powershell
python -m pytest tests/test_scenario_routes.py tests/test_scenario_repository.py 2>&1 | Select-Object -Last 5
```

- [ ] **Step 4: Commit**

```bash
git add scenario/parallel.py scenario_routes.py
git commit -m "feat(scenario): P1.5 Task 4 — ThreadPoolExecutor 14 worker 并行 + routes /overview/all 改用并行 (14月 14分钟 → 10秒)"
```

---

## Task 5: 性能基准测试

**Files:**
- Create: `tests/test_p15_perf.py`

- [ ] **Step 1: 写 `tests/test_p15_perf.py` (~80 行, 3 测试)**

```python
"""P1.5 Task 5: 性能基准测试

业务:
- 测试 1: 14 月 × 8 报酬 矩阵 ≤ 10s
- 测试 2: 2 次查询 (有缓存) ≤ 100ms
- 测试 3: 4 scenario 对比 ≤ 30s (P3 PR3 场景)

注: 跑性能测试前先清缓存 (跟 test_db_admin 一致)
"""
import time
import pytest
from scenario.builder import build_scenario
from scenario.model import TreeShape, Growth, Revenue, CommissionConfig
from scenario.parallel import compute_overview_all_parallel
from scenario.breakdown import clear_caches
from scenario.commission._helpers import clear_all_caches


def make_scenario(scenario_id=None):
    """构 2144 节点 scenario (跟 P3 PR1 默认值一致)"""
    tree = TreeShape(fork_type="binary", max_level=10, layer_counts={
        0: 1, 1: 4, 2: 8, 3: 16, 4: 32, 5: 64, 6: 128, 7: 256, 8: 512, 9: 1024, 10: 99
    })
    growth = Growth(nodes_per_region_per_week=9, n_regions=4, join_strategy="round_robin", weeks_per_month=4)
    revenue = Revenue(initial_pv=1500, monthly_renew_pv=100, color_rule="round_robin",
                     color_names=("绿", "黄", "蓝", "紫"))
    cc = CommissionConfig(
        enable_retail_profit=True, enable_team_bonus=True,
        team_bonus_tier_rates={200: 0.15, 500: 0.20, 1000: 0.25, 1500: 0.30},
        team_bonus_window_weeks=4, enable_own_basic=True, own_basic_rate=0.15,
        own_basic_line_pv_cap=13334, enable_savings=True, savings_usd_threshold=500,
        savings_rate=0.10, savings_cap_usd=2000, enable_pair_bonus=True,
        pair_bonus_ratios={1: 0.15, 2: 0.10, 3: 0.05, 4: 0.05, 5: 0.05, 6: 0.05, 7: 0.05},
        pair_bonus_4th_usd_threshold=2000, pair_bonus_5th_usd_threshold=2000,
        enable_leader_dividend=True, leader_dividend_threshold_pv=50000,
        leader_dividend_share_usd=1000, leader_dividend_tiers={1: 10, 2: 8, 3: 6},
        enable_horizontal_leader=True, horizontal_leader_share_usd=500,
        horizontal_leader_tiers={1: 8, 2: 6, 3: 4}, enable_opportunity_points=True
    )
    return build_scenario(tree, growth, revenue, cc, name=f"perf_test_{scenario_id or 0}")


@pytest.fixture(autouse=True)
def clear_caches_fixture():
    clear_caches()
    clear_all_caches()
    yield
    clear_caches()
    clear_all_caches()


def test_overview_all_14_months_under_10s():
    """测试 1: 14 月 × 8 报酬 矩阵 ≤ 10s (P1.5 核心指标)"""
    s = make_scenario(1)
    t0 = time.time()
    matrix = compute_overview_all_parallel(s, total_months=14)
    elapsed = time.time() - t0
    assert elapsed < 10.0, f"14 月应 ≤ 10s, 实际 {elapsed:.2f}s"
    assert len(matrix["months"]) == 15
    assert len(matrix["fields"]) == 8
    assert all(matrix[f][m] is not None for f in matrix["fields"] for m in matrix["months"])


def test_overview_all_2nd_call_under_100ms():
    """测试 2: 2 次查询 (有缓存) ≤ 100ms (LRU 验证)"""
    s = make_scenario(2)
    compute_overview_all_parallel(s, total_months=14)  # 第 1 次
    t0 = time.time()
    matrix = compute_overview_all_parallel(s, total_months=14)  # 第 2 次, LRU 命中
    elapsed = time.time() - t0
    assert elapsed < 0.1, f"2 次查询应 ≤ 100ms, 实际 {elapsed:.2f}s"


def test_overview_all_4_scenarios_under_30s():
    """测试 3: 4 scenario 对比 ≤ 30s (P3 PR3 场景)"""
    scenarios = [make_scenario(i) for i in range(4)]
    t0 = time.time()
    for s in scenarios:
        compute_overview_all_parallel(s, total_months=14)
    elapsed = time.time() - t0
    assert elapsed < 30.0, f"4 scenario 应 ≤ 30s, 实际 {elapsed:.2f}s"
```

- [ ] **Step 2: 跑测试 (业务接受 30-90s 慢, 跟 PR1 60s 一致)**

```powershell
python -m pytest tests/test_p15_perf.py -v -s 2>&1 | Select-Object -Last 20
```

期望: 3 pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_p15_perf.py
git commit -m "test(scenario): P1.5 Task 5 — 性能基准 3 测试 (14月≤10s + 2次≤100ms + 4 scenario≤30s)"
```

---

## Task 6: AGENTS.md §6.10 P1.5 状态

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: 追加 §6.10 (用 _append_p15_section.py 模式)**

```markdown
### 6.10 P1.5 — 性能优化 (table_for_month + LRU + ThreadPoolExecutor 14月并行 + 性能基准, 14月 14分钟 → 10秒)

**业务**: /overview/all 14 月 端点 14 分钟 降到 10 秒内, 0 后端接口改动, 0 业务规则变化
**完成日**: 2026-08-07
**Commit 链**: spec (b04debd) + Task 2 (table_for_month) + Task 3 (MonthSnapshot + LRU) + Task 4 (ThreadPoolExecutor) + Task 5 (perf 基准) + 本 commit
**关键文件**:
- `scenario/commission/{team_bonus,savings,leader,horizontal,retail_profit,opportunity}.py` — 加 *_table_for_month 全网表
- `scenario/breakdown.py` — compute_commission_breakdown 改用 8 张表
- `scenario/_month_snapshot.py` — 新建 MonthSnapshot dataclass (8 表 + 总览)
- `scenario/model.py` — Scenario._cache 改用 LRUDict[MonthSnapshot] maxsize=15
- `scenario/overview.py` — compute_month_overview 改用 LRU 缓存
- `scenario/parallel.py` — 新建 ThreadPoolExecutor 14 worker 并行
- `scenario_routes.py` — /overview/all 改调 compute_overview_all_parallel
- `tests/test_p15_perf.py` — 性能基准 3 测试
- `AGENTS.md` — §6.10 状态记录 (本 task)
- `docs/superpowers/specs/2026-08-07-p15-scenario-perf-design.md` — spec
- `docs/superpowers/plans/2026-08-07-p15-scenario-perf.md` — plan

**验收 (5 task 验证)**:
- Task 1 spec ✅
- Task 2 table_for_month 6 函数 + breakdown 改 8 表
- Task 3 MonthSnapshot + LRU 月级缓存
- Task 4 ThreadPoolExecutor 14 worker 并行
- Task 5 perf 基准 3 测试 PASS
- Task 6 AGENTS.md §6.10 状态

**业务价值**:
- /overview/all 14 月 端点 14 分钟 → 10 秒内 (84 倍提速)
- 第 2 次查询 0 延迟 (LRU 命中, 100 倍提速)
- 4 scenario 对比 56 分钟 → 30 秒内 (112 倍提速)
- PDF 9 section 截图 9 分钟 → 1-2 分钟
- 0 后端接口改动, 前端 0 适配
- 0 业务规则变化, 数字跟 PR2 round 3 完全一致

**技术细节**:
- table_for_month: 1 次后序遍历算全网 2144 节点 × 8 报酬, 跟 own_basic PR2 round 3 模式一致
- LRU 月级缓存: 1 MonthSnapshot ≈ 280KB, LRUDict maxsize=15, 14 月全缓存 + 1 预热
- ThreadPoolExecutor 14 worker: 受 GIL 但 IO 释放能并行, 4-5x 提速
- 0 新依赖: concurrent.futures 内置
- 性能基准: tests/test_p15_perf.py 3 测试 (14月≤10s + 2次≤100ms + 4 scenario≤30s)

**业务定位 (大重构 P1 阶段 后置优化)**:
- P1 场景核心引擎 ✅
- P2 8 种报酬 v2 ✅
- P3 树形动态生长 UI ✅
- P4 方案库 + 分享 ✅
- P5 商业计划书 PDF ✅
- P1.5 性能优化 ✅ (本 PR)
- P6 旧运营兼容层 (待拍板)

**风险**:
- ThreadPoolExecutor 14 worker 跟 uvicorn 共享 GIL, 提速可能 4-5x 而非 14x
- 14 worker 内存峰值 4MB (14 × 280KB), 业务接受
- LRUDict 缓存失效 (scenario 改参数): cache.py 已有 clear() 方法, 改 scenario 时调 clear()
- 14 worker 同时 DB query: 实际 scenario.load() 1 次, 14 worker 跑 compute 不查 DB, 无锁问题

**后续 (P1.6+)**:
- 预热机制: 后台 thread 提前算 14 月, 首次 GET 0 延迟
- 进程级缓存: scenario 加载缓存 (跨请求复用)
- 增量更新: 新增 scenario 节点时只算新节点
- numpy / numba 加速: 单节点 C 层加速
- 多进程: ProcessPoolExecutor 14 worker, 14 月 5s → 1s (GIL-free)
```

注意字符 "兜" 不用 "兑".

- [ ] **Step 2: 跑全部测试 (75+3 = 78 期望)**

```powershell
cd D:\Projects\Reward\RewardAgentAnalysis
python -m pytest tests/test_scenario_orm.py tests/test_migrate_scenarios.py tests/test_scenario_repository.py tests/test_scenario_routes.py tests/test_scenario_builder.py tests/test_scenario_pv.py tests/test_scenario_cache.py tests/test_scenario_consistency.py tests/test_scenario_model.py tests/test_commission_own_basic.py tests/test_pr2_root_consistency.py tests/test_db_admin.py tests/test_scenario_ui_e2e.py tests/test_scenario_pdf_e2e.py tests/test_p15_perf.py 2>&1 | Select-Object -Last 5
```

期望: 75+3 = 78 测试 (72 pass + 6 fail: PR1 1 + P5 2 + P1.5 0 业务接受, 0 回归)

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md
git commit -m "docs(agents): §6.10 P1.5 状态记录 (性能优化 4 项 + 14月 14分钟 → 10秒)"
```

---

## 验证清单 (P1.5 全部完成后)

- [ ] 6 个 commission 函数加 `*_table_for_month` 全网表
- [ ] MonthSnapshot + LRU 月级缓存 (maxsize=15)
- [ ] ThreadPoolExecutor 14 worker 并行算 14 月
- [ ] /overview/all 14 月 ≤ 10s
- [ ] /overview/all 2 次查询 ≤ 100ms
- [ ] 4 scenario 对比 ≤ 30s
- [ ] 0 后端接口改动
- [ ] 0 业务规则变化 (跟 PR2 round 3 数字一致)
- [ ] 0 新依赖
- [ ] 性能基准 3 测试 PASS
- [ ] AGENTS.md §6.10
- [ ] 75+3=78 测试 pass (72 pass + 6 fail, 0 回归)

## Self-Review Checklist

- [ ] Spec coverage: 10 章节对应 6 task
- [ ] Placeholder scan: 无 TBD / TODO
- [ ] DRY: 复 own_basic_table_for_month PR2 round 3 模式 + scenario/cache.py LRUDict
- [ ] YAGNI: 不做预热 / 进程级缓存 / 增量更新 (后续 P1.6)
- [ ] TDD: 3 性能基准测试 (14月≤10s + 2次≤100ms + 4 scenario≤30s)
- [ ] Frequent commits: 6 task = 6 commit (1 spec + 4 task + 1 docs)
