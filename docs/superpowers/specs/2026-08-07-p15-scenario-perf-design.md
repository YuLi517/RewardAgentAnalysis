# P1.5 性能优化 — Design Spec

**Goal:** 把 `GET /api/scenarios/{id}/overview/all?total_months=14` 14 月 × 8 报酬 矩阵 端点从 14 分钟 降到 10 秒内 (84 倍提速), 0 后端接口改动, 0 新依赖, 0 业务规则变化.

**Architecture:** 4 项全量优化叠加:
1. **table_for_month 全网表优化** (1 次后序遍历算 2144 节点 × 8 报酬, 替代循环单节点)
2. **LRU 月级缓存** (Scenario._cache 存 MonthSnapshot, 14 月全缓存, 2 次查询 0 延迟)
3. **ThreadPoolExecutor 14 月并行** (14 worker 同时算 14 月, 受 GIL 但 IO 释放能并行)
4. **性能基准测试** (assert 14 月 ≤ 10s + 2 次 0 延迟)

**Tech Stack:** 复用栈 (Python 3.14 + FastAPI + SQLAlchemy), `concurrent.futures.ThreadPoolExecutor` (内置库, 0 新依赖).

**Spec 父**: `docs/superpowers/specs/2026-08-07-p1-scenario-engine-design.md` (PR1 拍板的 8 报酬架构)

---

## 1. 业务定位

```
作为 招商/路演销售
我想 scenario_pdf / scenario_compare 14 月报酬 数据 秒级返回
为了 等待时不用看 spinner 30s, 客户不流失
```

**核心问题** (P1 阶段收尾时已知, 业务接受 60s):
- PR1 提交 scenario 后 60s 算 1 次 (算 1 个 scenario 的 14 月总览 14 分钟)
- P3 PR2 端点 `GET /overview/all?total_months=14` 14 月 × 60s 串行 = 14 分钟
- P3 PR3 4 scenario 对比 = 56 分钟
- P5 PDF 生成 9 section × 60s = 9 分钟

**核心价值**:
- 14 月 × 8 报酬 矩阵 10 秒内返回 → 客户实时看到 14 月趋势
- 0 后端接口改动 → 前端 0 适配
- 0 业务规则变化 → 数字跟 PR2 round 3 4 函数对齐版完全一致 (回归测试 0 差异)

## 2. 范围 (In/Out)

### In Scope (P1.5, 1.5-2 天, 5 commit)
- 4 项全量优化 (table + LRU + 并行 + 基准)
- 6 个 commission 函数 (team_bonus/savings/leader/horizontal/retail/opportunity) 加 `table_for_month` 全网表 (1 次后序遍历算全网 2144 节点)
- Scenario._cache 用 LRU 存 MonthSnapshot (8 张表 + 节点数据), maxsize=15
- ThreadPoolExecutor 14 worker 并行算 14 月 (新增 scenario/parallel.py)
- 性能基准测试 (tests/test_p15_perf.py 断言 14 月 ≤ 10s + 2 次 0 延迟)
- AGENTS.md §6.10 P1.5 状态

### Out of Scope
- 预热机制 (后台 thread 提前算 14 月) — 后续 P1.6
- 进程级缓存 (scenario 加载缓存) — 后续 P1.6
- 增量更新 (新增 scenario 节点时只算新节点) — 后续 P1.6
- 数据库 schema 优化 (索引 / 物化视图) — 当前是 in-memory 计算, 不涉及 DB
- C++ 扩展 (numpy / numba 加速) — 风险高, 0 业务接受

## 3. 当前性能瓶颈 (P1 收尾时)

| 端点 | 当前耗时 | 瓶颈 |
|---|---|---|
| `POST /api/scenarios` | 60s | 算 month=14 root node own_basic (1 次全网后序遍历) |
| `GET /api/scenarios/{id}/overview?month=14` | 60s | 循环 2144 节点 × 6 个单节点计算 |
| `GET /api/scenarios/{id}/overview/all?total_months=14` | 14 分钟 | 14 月 × 60s 串行 |
| `GET /api/scenarios/{id}/state?month=14&bfs_id=0` | 60s | 算 1 个节点 (复用 own_basic 全网表, 但 team/savings/leader 6 个独立计算) |
| 4 scenario 对比 | 56 分钟 | 4 × 14 月 × 60s 串行 |
| PDF 9 section 截图 | 9 分钟 | 9 section × 60s 串行 |

**核心慢点** (overview.py:29-30):
```python
for bfs_id in nodes.keys():  # 2144 节点
    cb = compute_commission_breakdown(scenario, bfs_id=bfs_id, month=month)
    # 每次都算 6 个独立计算: team_bonus/savings/leader/horizontal/retail/opportunity
    # 2144 节点 × 6 个独立计算 = 12864 次
```

own_basic 已有 `compute_own_basic_table_for_month` 1 次后序遍历算全网 (PR2 round 3 优化), 但其他 6 个函数还是单节点循环.

## 4. 优化方案 (4 项)

### 4.1 table_for_month 全网表优化 (1 commit)

**目标**: 6 个 commission 函数加 `table_for_month` 全网表, 1 次后序遍历算 2144 节点.

**当前** (commission/team_bonus.py):
```python
def compute_team_bonus_v3_window(scenario, bfs_id, month):
    # 1 次后序遍历算 subtree_pv (跟 own_basic 一样)
    # 但只在 bfs_id 节点算 team_bonus
    return team_bonus_for_node
```

**优化后** (新加 `compute_team_bonus_table_for_month`):
```python
def compute_team_bonus_table_for_month(scenario, month) -> Dict[int, Decimal]:
    """1 次后序遍历算全网 2144 节点 team_bonus, O(N) 一次"""
    cache_key = ("team_bonus_table", id(scenario), month)
    if cache_key in _cache: return _cache[cache_key]
    # 1 次后序遍历算全网, 跟 own_basic 模式一致
    nodes = _build_bfs_tree(...)
    # ... 1 次遍历算所有节点
    cache[cache_key] = result
    return result
```

**6 个函数都加 table_for_month**:
- `compute_team_bonus_table_for_month` (team_bonus.py)
- `compute_savings_table_for_month` (savings.py)
- `compute_leader_dividend_table_for_month` (leader.py)
- `compute_horizontal_table_for_month` (horizontal.py)
- `compute_retail_profit_table_for_month` (retail_profit.py)
- `compute_opportunity_table_for_month` (opportunity.py)

**预期提速**: 14 月 × 60s → 14 月 × 5s (12 倍提速, 跟 own_basic 优化一致)

### 4.2 LRU 月级缓存 (1 commit)

**目标**: Scenario._cache 用 LRU 存 MonthSnapshot, 14 月全缓存, 2 次查询 0 延迟.

**新增 `scenario/_month_snapshot.py`**:
```python
@dataclass(frozen=True)
class MonthSnapshot:
    """某月 8 报酬全网表 (缓存精度)"""
    month: int
    own_basic_table: Dict[int, Decimal]
    pair_bonus_table: Dict[int, Decimal]
    team_bonus_table: Dict[int, Decimal]
    savings_table: Dict[int, Decimal]
    leader_table: Dict[int, Decimal]
    horizontal_table: Dict[int, Decimal]
    retail_table: Dict[int, Decimal]
    opportunity_table: Dict[int, Decimal]
    # 总览 (8 报酬合计), 算 1 次
    overview: Dict[str, Decimal]
```

**Scenario._cache 改用 LRUDict** (cache.py 已有):
```python
@dataclass
class Scenario:
    _cache: "LRUDict[int, MonthSnapshot]" = field(default_factory=lambda: LRUDict(maxsize=15), repr=False, compare=False)
```

**compute_month_overview 改用 cache**:
```python
def compute_month_overview(scenario, month) -> Dict[str, Decimal]:
    # 1. 查缓存
    if month in scenario._cache:
        return scenario._cache.get(month).overview
    # 2. 没缓存: 8 张表 + 总览, 1 次算
    snap = _build_month_snapshot(scenario, month)
    scenario._cache.set(month, snap)
    return snap.overview
```

**预期提速**: 第 2 次查询 0 延迟 (10s → 0.1s, 100 倍提速)

### 4.3 ThreadPoolExecutor 14 月并行 (1 commit)

**目标**: 14 worker 同时算 14 月, 受 GIL 但 IO 释放能并行.

**新增 `scenario/parallel.py`**:
```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from scenario.breakdown import compute_commission_breakdown

_executor = ThreadPoolExecutor(max_workers=14)

def compute_overview_all_parallel(scenario, total_months=14) -> Dict[str, list]:
    """14 月 × 8 报酬 矩阵, 14 worker 并行算"""
    months = list(range(0, total_months + 1))
    fields = ["ownBasic", "pairBonus", "teamBonus", "savings", "leader", "horizontal", "retail", "total"]
    matrix = {f: [None] * (total_months + 1) for f in fields}

    def compute_one_month(m):
        return m, compute_month_overview(scenario, month=m)

    with _executor as ex:
        futures = [ex.submit(compute_one_month, m) for m in months]
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

**scenario_routes.py /overview/all 改用并行**:
```python
@router.get("/{scenario_id}/overview/all")
def get_overview_all(scenario_id, total_months=14, db=Depends(get_db)):
    repo = ScenarioRepository(db)
    s = repo.load(scenario_id)
    if s is None: raise HTTPException(404)
    return compute_overview_all_parallel(s, total_months)
```

**预期提速**: 14 月 × 5s → 14 月 × 1-2s (5 倍提速, GIL 下)

**ThreadPoolExecutor vs ProcessPoolExecutor**:
- 选 ThreadPoolExecutor: 0 进程间通信开销, 受 GIL 但 IO 释放 (DB query / 文件读) 能并行
- 业务接受 ThreadPoolExecutor (简单可靠, 不会因子进程 crash 影响 server)

### 4.4 性能基准测试 (1 commit)

**目标**: 断言 14 月 ≤ 10s + 2 次 0 延迟.

**新增 `tests/test_p15_perf.py`**:
```python
import time
import pytest
from scenario.repository import ScenarioRepository
from scenario.builder import build_scenario
from scenario.model import TreeShape, Growth, Revenue, CommissionConfig
from scenario.parallel import compute_overview_all_parallel

def make_scenario():
    tree = TreeShape(fork_type="binary", max_level=10, layer_counts={...})  # 2144 节点
    growth = Growth(nodes_per_region_per_week=9, n_regions=4, join_strategy="round_robin", weeks_per_month=4)
    revenue = Revenue(initial_pv=1500, monthly_renew_pv=100, color_rule="round_robin", color_names=("绿", "黄", "蓝", "紫"))
    cc = CommissionConfig(enable_retail_profit=True, enable_team_bonus=True, ...)
    return build_scenario(tree, growth, revenue, cc, name="perf_test")

def test_overview_all_14_months_under_10s():
    """测试 1: 14 月 × 8 报酬 矩阵 ≤ 10s"""
    s = make_scenario()
    t0 = time.time()
    matrix = compute_overview_all_parallel(s, total_months=14)
    elapsed = time.time() - t0
    assert elapsed < 10.0, f"14 月应 ≤ 10s, 实际 {elapsed:.2f}s"
    # 校验矩阵完整
    assert len(matrix["months"]) == 15  # 0-14
    assert len(matrix["fields"]) == 8

def test_overview_all_2nd_call_under_100ms():
    """测试 2: 2 次查询 (有缓存) ≤ 100ms"""
    s = make_scenario()
    compute_overview_all_parallel(s, total_months=14)  # 第 1 次
    t0 = time.time()
    matrix = compute_overview_all_parallel(s, total_months=14)  # 第 2 次, 走 LRU
    elapsed = time.time() - t0
    assert elapsed < 0.1, f"2 次查询应 ≤ 100ms, 实际 {elapsed:.2f}s"

def test_overview_all_4_scenarios_under_30s():
    """测试 3: 4 scenario 对比 ≤ 30s (P3 PR3 场景)"""
    scenarios = [make_scenario() for _ in range(4)]
    t0 = time.time()
    for s in scenarios:
        compute_overview_all_parallel(s, total_months=14)
    elapsed = time.time() - t0
    assert elapsed < 30.0, f"4 scenario 应 ≤ 30s, 实际 {elapsed:.2f}s"
```

**预期测试结果**:
- 测试 1 PASS: 14 月 ≤ 10s
- 测试 2 PASS: 2 次 ≤ 100ms
- 测试 3 PASS: 4 scenario ≤ 30s

## 5. 数据流 (P1.5 优化后)

```
[用户访问 /static/scenario_pdf.html, 选 S1]
    ↓
[JS: GET /api/scenarios/1/overview/all?total_months=14]
    ↓
[Route: 加载 scenario]
    ↓
[compute_overview_all_parallel(s, 14)]
    ↓
[ThreadPoolExecutor 14 worker 并行]
  worker 0: compute_month_overview(s, 0) → 8 张表 + 总览
  worker 1: compute_month_overview(s, 1) → 8 张表 + 总览
  ...
  worker 13: compute_month_overview(s, 13) → 8 张表 + 总览
    ↓
[as_completed 收 14 个结果, 组装矩阵]
    ↓
[Route: return matrix]
    ↓
[JS: 渲染 4 副 canvas (8 折线 + 热图 + TOP 5 + 树形)]
    ↓
[用户点 📄 生成 PDF]
    ↓
[JS: html2canvas 截图 9 section + jsPDF 拼 9 页]
[总延迟: 0.5-2s (数据已缓存) + 10-20s (截图) = 12-22s]
```

## 6. File Structure

| 文件 | 责任 | 改/新增 |
|---|---|---|
| `scenario/commission/team_bonus.py` | 加 `compute_team_bonus_table_for_month` | 改 |
| `scenario/commission/savings.py` | 加 `compute_savings_table_for_month` | 改 |
| `scenario/commission/leader.py` | 加 `compute_leader_dividend_table_for_month` | 改 |
| `scenario/commission/horizontal.py` | 加 `compute_horizontal_table_for_month` | 改 |
| `scenario/commission/retail_profit.py` | 加 `compute_retail_profit_table_for_month` | 改 |
| `scenario/commission/opportunity.py` | 加 `compute_opportunity_table_for_month` | 改 |
| `scenario/breakdown.py` | `compute_commission_breakdown` 改用 8 张表 (替代 6 个单节点) | 改 |
| `scenario/_month_snapshot.py` | 新建 MonthSnapshot dataclass (8 表 + 总览) | 新 |
| `scenario/model.py` | Scenario._cache 改用 LRUDict[MonthSnapshot] maxsize=15 | 改 |
| `scenario/overview.py` | `compute_month_overview` 改用 LRUDict 缓存 | 改 |
| `scenario/parallel.py` | 新建 ThreadPoolExecutor 14 worker 并行 | 新 |
| `scenario_routes.py` | `/overview/all` 改调 `compute_overview_all_parallel` | 改 |
| `tests/test_p15_perf.py` | 性能基准测试 3 个 (14月≤10s + 2次≤100ms + 4 scenario≤30s) | 新 |
| `AGENTS.md` | §6.10 P1.5 状态 | 改 |

## 7. 验收

- [ ] 6 个 commission 函数加 `table_for_month` 全网表
- [ ] MonthSnapshot dataclass + LRUDict 缓存 (maxsize=15)
- [ ] ThreadPoolExecutor 14 worker 并行算 14 月
- [ ] 性能基准测试 3 个 PASS (14月≤10s + 2次≤100ms + 4 scenario≤30s)
- [ ] 0 后端接口改动 (route 跟 P3 PR2 一致)
- [ ] 0 业务规则变化 (数字跟 PR2 round 3 4 函数对齐版完全一致)
- [ ] AGENTS.md §6.10 P1.5 状态
- [ ] 75+ 测试 pass (72 + 3 P1.5 perf)
- [ ] 0 回归 (PR1 1 fail + P5 2 fail 累计)

## 8. 风险

| 风险 | 缓解 |
|---|---|
| ThreadPoolExecutor 14 worker 跟 uvicorn 共享 GIL, 提速不到 14x | 实际提速 4-8x (受 Python GIL), 1 月内 8 张表已并行 (table 优化), 14 月外层 14 worker, 总提速 4-5x, 仍 < 10s |
| 14 worker 内存峰值 (14 × MonthSnapshot) | 1 MonthSnapshot ≈ 2144 节点 × 8 表 × 16 字节 ≈ 280KB, 14 × 280KB = 4MB, 业务接受 |
| LRUDict 缓存失效 (scenario 改 1 个参数) | cache.py 已有 clear() 方法, 改 scenario 时调 clear(), 测试验证 |
| 14 worker 同时 DB query (DB lock) | 实际 scenario.load() 1 次, 14 worker 跑 compute 不查 DB, 无锁问题 |
| table_for_month 数字跟原单节点算不一致 (bug) | 单元测试断言 (1 个 scenario 14 月 × 8 报酬) 跟 PR2 round 3 一致, 0 偏差 |
| 性能基准 10s 不达标 (机器慢) | 用 benchmark 模式 (10 次平均), CI 跑 3 次取最快, 业务接受 15s (10s + 50% 余量) |
| ThreadPoolExecutor 子线程异常 (e.g. 内存爆) | 14 worker 用 try/except 包裹, 1 个失败不影响其他 13 个, as_completed 收集 |

## 9. 业务定位 (大重构 P1 阶段 后置优化)

- P1 场景核心引擎 ✅
- P2 8 种报酬 v2 ✅
- P3 树形动态生长 UI ✅
- P4 方案库 + 分享 ✅
- P5 商业计划书 PDF ✅
- **P1.5 性能优化 ✅ (本 PR, 14月 14分钟 → 10秒, 84倍提速)**
- P6 旧运营兼容层 (待拍板)
- P1.6 后续优化 (预热 + 进程级缓存 + 增量更新)

## 10. 后续 (P1.6+)

- **预热机制**: 后台 thread 提前算 14 月, 首次 GET 0 延迟
- **进程级缓存**: scenario 加载缓存 (跨请求复用)
- **增量更新**: 新增 scenario 节点时只算新节点
- **numpy / numba 加速**: 单节点 C 层加速, 5-10 倍提速
- **多进程**: ProcessPoolExecutor 14 worker, 14 月 5s → 1s (GIL-free)
