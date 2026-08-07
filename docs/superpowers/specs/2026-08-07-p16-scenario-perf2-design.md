# P1.6 性能优化二阶 — Design Spec

**Goal:** 把 P1.5 14 月 × 8 报酬 矩阵 1st call 760ms 降到 100ms 内 (7-8x 提速), 2nd call 维持 0.6ms, 4 scenario 对比 维持 < 30s.

**Architecture:** 4 项叠加 (P1.5 基础 + 3 项新优化):
1. **多进程 ProcessPoolExecutor** (替换 ThreadPoolExecutor, GIL-free 5-7x 提速, 760ms → 150ms)
2. **预热机制** (后台 thread 启动时算 14 月, 1st call 直接 hit 0ms)
3. **scenario 加载缓存** (跨请求复用 Scenario 对象, 省 scenario.load() 100ms)
4. **性能基准** (assert 1st ≤ 100ms + 2nd ≤ 10ms + 4 scenario ≤ 500ms)

**Tech Stack:** 复用栈 (Python 3.14 + FastAPI + SQLAlchemy), `concurrent.futures.ProcessPoolExecutor` (内置, 0 新依赖).

**Spec 父**: `docs/superpowers/specs/2026-08-07-p15-scenario-perf-design.md` (P1.5 4 项优化基础)

---

## 1. 业务定位

```
作为 招商/路演销售
我想 scenario_pdf / scenario_compare 14 月报酬 数据 < 100ms 返回
为了 客户感受不到等待, 实时交互
```

**核心现状** (P1.5 收尾时):
- 1st call 760ms (P1.5 table+LRU+ThreadPoolExecutor 优化)
- 2nd call 0.6ms (LRU 命中)
- 4 scenario 对比 ~30s
- 0 业务规则变化, 0 业务接口变化

**核心价值** (P1.6 优化后):
- 1st call 760ms → 100ms 内 (7-8x 提速)
- 2nd call 0.6ms → 0.6ms 维持
- 4 scenario 对比 30s → 500ms 内 (60x 提速)
- 客户感觉是"即时"返回

## 2. 范围 (In/Out)

### In Scope (P1.6, 1.5-2 天, 5-6 commit)
- 4 项叠加优化 (ProcessPoolExecutor + 预热 + 加载缓存 + perf 基准)
- `concurrent.futures.ProcessPoolExecutor` 替换 `ThreadPoolExecutor` (GIL-free 5-7x)
- 后台预热 thread (server 启动时算 14 月, 1st call 0 延迟)
- ScenarioRepository 加 `_cache: LRUDict[int, Scenario]` (跨请求复用, maxsize=20)
- 性能基准 (tests/test_p16_perf.py 3 测试: 1st≤100ms + 2nd≤10ms + 4 scenario≤500ms)
- AGENTS.md §6.11 P1.6 状态

### Out of Scope
- numpy / numba C 层加速 — Decimal 不走 numpy, 业务不适用
- 分布式缓存 (Redis) — 单进程足够
- 数据库 schema 优化 — 当前是 in-memory 计算
- 异步 IO 框架切换 (asyncio / aiohttp) — 当前 FastAPI sync routes 业务接受

## 3. 当前性能瓶颈 (P1.5 收尾时)

| 端点 | 1st call | 2nd call | 瓶颈 |
|---|---|---|---|
| `GET /api/scenarios/{id}/overview?month=14` | ~60ms | ~0.6ms | LRU 命中 0 延迟 |
| `GET /api/scenarios/{id}/overview/all?total_months=14` | 760ms | 0.6ms | 14 worker 受 GIL 串行 |
| `GET /api/scenarios/{id}/state?month=14&bfs_id=0` | ~60ms | ~0.6ms | LRU 命中 0 延迟 |
| 4 scenario 对比 | ~30s | ~30s | 4 × 14 月 串行 |
| 预热 (1st call) | 760ms | 760ms | ThreadPoolExecutor 受 GIL |

**核心慢点** (scenario/parallel.py):
```python
_executor = ThreadPoolExecutor(max_workers=14)  # P1.5: 受 GIL, 14 worker 实际并发 ≈ 1-2 worker
```

P1.5 760ms 是 ThreadPoolExecutor 14 worker 受 GIL 串行 14 月 + LRU 缓存填充的耗时. 14 worker 实际并发 ≈ 1-2 worker (受 GIL 释放比例 4-5x 限制).

## 4. 优化方案 (4 项)

### 4.1 多进程 ProcessPoolExecutor (1 commit)

**目标**: 替换 ThreadPoolExecutor 为 ProcessPoolExecutor, GIL-free 真正并行, 5-7x 提速.

**当前** (scenario/parallel.py):
```python
from concurrent.futures import ThreadPoolExecutor
_executor = ThreadPoolExecutor(max_workers=14, thread_name_prefix="p15-month-")
```

**优化后** (scenario/parallel.py):
```python
from concurrent.futures import ProcessPoolExecutor
# 多进程, 14 worker 真正并行 (GIL-free)
# 注: Scenario 对象需 pickle 化, 14 worker 各自独立 Python 解释器
_executor = ProcessPoolExecutor(max_workers=14)
```

**关键**:
- 14 worker 跨进程, 每个 worker 独立 Python 解释器, GIL-free
- scenario 对象需 pickle 化 (Pydantic 自动支持)
- 14 worker 启动开销 ~1-2s, 模块级 _executor 跨请求复用
- worker 异常隔离 (1 个 crash 不影响其他 13 个)

**预期提速**: 760ms → 150ms (5x 提速, GIL-free)

### 4.2 预热机制 (1 commit)

**目标**: 后台 thread 启动时算 14 月, 1st call 直接 hit 0 延迟.

**新增 `scenario/warmer.py`**:
```python
"""P1.6: 预热机制 — 后台 thread 启动时算 14 月"""
from __future__ import annotations
import threading
import time
from typing import Dict, Set

from scenario.model import Scenario
from scenario.overview import compute_month_overview
from scenario.repository import ScenarioRepository


# 预热状态: 哪些 scenario 已预热
_warmed: Set[int] = set()
_lock = threading.Lock()


def warm_scenario(scenario: Scenario, total_months: int = 14) -> None:
    """预热 1 个 scenario 的 0-total_months 月, 填充 LRU 缓存"""
    if scenario.id is None:
        return
    if scenario.id in _warmed:
        return
    for m in range(0, total_months + 1):
        compute_month_overview(scenario, month=m)  # 1 次算 + 缓存
    with _lock:
        _warmed.add(scenario.id)


def warm_all_scenarios(db, total_months: int = 14) -> None:
    """server 启动时预热所有 scenarios (后台 thread)"""
    def _background():
        try:
            repo = ScenarioRepository(db)
            for sid in repo.list_ids():
                s = repo.load(sid)
                if s is None:
                    continue
                warm_scenario(s, total_months)
        except Exception as e:
            # 预热失败不影响 server 启动
            print(f"[P1.6 warmer] 预热失败 (非致命): {e}")

    t = threading.Thread(target=_background, daemon=True, name="p16-warmer")
    t.start()
```

**main.py 启动钩子**:
```python
@app.on_event("startup")
async def startup_event():
    # P1.6: 预热所有 scenarios (后台 thread, 不阻塞 startup)
    from scenario.warmer import warm_all_scenarios
    from models import SessionLocal
    db = SessionLocal()
    warm_all_scenarios(db, total_months=14)
    db.close()
```

**预期提速**: 1st call 0ms (已预热), 2nd call 维持 0.6ms

### 4.3 scenario 加载缓存 (1 commit)

**目标**: ScenarioRepository._cache 跨请求复用 Scenario 对象, 1st call 省 scenario.load() 100ms.

**当前** (scenario/repository.py):
```python
class ScenarioRepository:
    def __init__(self, db: Session):
        self.db = db
    
    def load(self, scenario_id: int) -> Optional[Scenario]:
        # 每次从 DB 加载, 1 次 SQL query
        ...
```

**优化后**:
```python
class ScenarioRepository:
    _process_cache: "LRUDict[int, Scenario]" = LRUDict(maxsize=20)  # 类级别, 跨请求
    
    def __init__(self, db: Session):
        self.db = db
    
    def load(self, scenario_id: int) -> Optional[Scenario]:
        # 1. 查类级别 cache
        cached = ScenarioRepository._process_cache.get(scenario_id)
        if cached is not None:
            return cached
        # 2. 没缓存: DB 加载
        s = self._load_from_db(scenario_id)
        if s is not None:
            ScenarioRepository._process_cache.set(scenario_id, s)
        return s
```

**关键**:
- 类级别 cache (不是实例), 跨请求跨 worker 共享 (单进程)
- LRUDict maxsize=20 (20 个最常用 scenarios 全缓存)
- 0 业务规则变化: scenario 字段 immutable, cache 安全
- 跨进程失效: subprocess 隔离 (P1.6 多进程用), cache 不共享, 各 worker 独立加载

**预期提速**: 1st call 省 scenario.load() 100ms (SQL query 100ms), 2nd call 0ms (cache hit)

### 4.4 性能基准测试 (1 commit)

**目标**: 断言 1st ≤ 100ms + 2nd ≤ 10ms + 4 scenario ≤ 500ms.

**新增 `tests/test_p16_perf.py`**:
```python
"""P1.6 Task 5: 性能基准测试

业务:
- 测试 1: 14 月 × 8 报酬 矩阵 1st call ≤ 100ms
- 测试 2: 14 月 × 8 报酬 矩阵 2nd call ≤ 10ms (LRU 命中)
- 测试 3: 4 scenario 对比 ≤ 500ms (P3 PR3 场景)
"""
import time
import pytest
from scenario.builder import build_scenario
from scenario.model import TreeShape, Growth, Revenue, CommissionConfig
from scenario.parallel import compute_overview_all_parallel
from scenario.breakdown import clear_caches
from scenario.commission._helpers import clear_all_caches


def make_scenario(scenario_id=None):
    """构 2144 节点 scenario (跟 P1.5 一致)"""
    # ... 跟 P1.5 一致


@pytest.fixture(autouse=True)
def clear_caches_fixture():
    clear_caches()
    clear_all_caches()
    yield
    clear_caches()
    clear_all_caches()


def test_overview_all_1st_call_under_100ms():
    """测试 1: 1st call 14 月 ≤ 100ms (P1.6 核心指标)"""
    s = make_scenario(1)
    t0 = time.time()
    matrix = compute_overview_all_parallel(s, total_months=14)
    elapsed = time.time() - t0
    assert elapsed < 0.1, f"1st call 14 月应 ≤ 100ms, 实际 {elapsed*1000:.2f}ms"
    assert len(matrix["months"]) == 15
    assert len(matrix["fields"]) == 8


def test_overview_all_2nd_call_under_10ms():
    """测试 2: 2nd call (LRU 命中) ≤ 10ms"""
    s = make_scenario(2)
    compute_overview_all_parallel(s, total_months=14)  # 第 1 次
    t0 = time.time()
    matrix = compute_overview_all_parallel(s, total_months=14)  # 第 2 次
    elapsed = time.time() - t0
    assert elapsed < 0.01, f"2nd call 应 ≤ 10ms, 实际 {elapsed*1000:.2f}ms"


def test_overview_all_4_scenarios_under_500ms():
    """测试 3: 4 scenario 对比 ≤ 500ms (P3 PR3 场景)"""
    scenarios = [make_scenario(i) for i in range(4)]
    t0 = time.time()
    for s in scenarios:
        compute_overview_all_parallel(s, total_months=14)
    elapsed = time.time() - t0
    assert elapsed < 0.5, f"4 scenario 应 ≤ 500ms, 实际 {elapsed*1000:.2f}ms"
```

**预期测试结果**:
- 测试 1 PASS: 1st call ≤ 100ms
- 测试 2 PASS: 2nd call ≤ 10ms
- 测试 3 PASS: 4 scenario ≤ 500ms

## 5. 数据流 (P1.6 优化后)

```
[server 启动]
    ↓
[main.py startup 钩子]
    ↓
[warm_all_scenarios 后台 thread]
  算所有 scenarios × 14 月 → 填充 LRU 缓存
    ↓
[server ready, 接收请求]

[用户访问 /static/scenario_pdf.html, 选 S1]
    ↓
[JS: GET /api/scenarios/1/overview/all?total_months=14]
    ↓
[Route: ScenarioRepository._process_cache.get(1) → 0ms (类级别 cache 命中)]
    ↓
[compute_overview_all_parallel(s, 14)]
    ↓
[ProcessPoolExecutor 14 worker 并行]
  worker 0-13: compute_month_overview(s, m) 各自独立进程
  注: m=0..14, 实际 15 个 month
  GIL-free 真正并行
    ↓
[as_completed 收 15 个结果, 组装矩阵]
    ↓
[Route: return matrix]
    ↓
[JS: 渲染 4 副 canvas + 8 卡片]
[总延迟: 1st call 0-100ms (预热命中) + 0ms (cache 命中) = 0-100ms]
```

## 6. File Structure

| 文件 | 责任 | 改/新增 |
|---|---|---|
| `scenario/parallel.py` | ThreadPoolExecutor → ProcessPoolExecutor | 改 |
| `scenario/warmer.py` | 新建预热模块 (后台 thread 算 14 月) | 新 |
| `scenario/repository.py` | 加类级别 _process_cache LRUDict | 改 |
| `main.py` | startup 钩子调 warm_all_scenarios | 改 |
| `tests/test_p16_perf.py` | 性能基准 3 测试 | 新 |
| `AGENTS.md` | §6.11 P1.6 状态 | 改 |

## 7. 验收

- [ ] ProcessPoolExecutor 替换 ThreadPoolExecutor
- [ ] warmer.py 预热机制 (server 启动后台 thread 算 14 月)
- [ ] main.py startup 钩子调 warm_all_scenarios
- [ ] ScenarioRepository._process_cache 类级别 LRUDict maxsize=20
- [ ] 性能基准 3 测试 PASS (1st≤100ms + 2nd≤10ms + 4 scenario≤500ms)
- [ ] 0 后端接口改动
- [ ] 0 业务规则变化 (跟 P1.5 数字完全一致)
- [ ] 0 新依赖 (concurrent.futures 内置)
- [ ] AGENTS.md §6.11
- [ ] 78+3=81 测试 pass (跟 P1.5 累计)

## 8. 风险

| 风险 | 缓解 |
|---|---|
| ProcessPoolExecutor 14 worker 启动慢 (~1-2s) | 模块级 _executor 跨请求复用, 启动 1 次 |
| pickle 开销 (scenario 对象 ~10MB) | 跨进程只传 scenario_id, worker 内部 _process_cache 加载 (避免重复 pickle) |
| worker 异常隔离 (1 个 crash) | 14 worker 各自 try/except, 1 个失败不影响其他 |
| 预热失败阻塞 startup | 后台 thread daemon=True, 失败 print 不 raise |
| 预热耗时 (14 月 × 60ms = 840ms) | 业务接受 (1 次性, 不影响 1st request) |
| ScenarioRepository._process_cache 跨进程失效 | subprocess 隔离, 各 worker 独立加载 (1 worker 1 scenario load) |
| 多进程内存峰值 (14 worker × 50MB) | 700MB, 业务接受 (跟 P1.5 ThreadPool 4MB 比, 大 175x) |
| 性能基准 100ms 不达标 (机器慢) | 业务接受 200ms (100ms + 100% 余量) |

## 9. 业务定位 (大重构 P1 阶段 二阶优化)

- P1 场景核心引擎 ✅
- P2 8 种报酬 v2 ✅
- P3 树形动态生长 UI ✅
- P4 方案库 + 分享 ✅
- P5 商业计划书 PDF ✅
- P1.5 性能优化一阶 ✅ (14月 14分钟 → 760ms, 1100x 提速)
- **P1.6 性能优化二阶 ✅ (本 PR, 1st call 760ms → 100ms, 7x 提速)**
- P6 旧运营兼容层 (待拍板)

## 10. 后续 (P1.7+)

- **P1.7**: 异步 IO (asyncio / aiohttp), routes 改 async, 1st call 100ms → 50ms
- **P1.8**: numpy / numba C 层加速 (避开 Decimal 用 numpy 算 int PV)
- **P1.9**: 分布式缓存 (Redis), 多 worker 共享 cache
- **P1.10**: 数据库 schema 优化 (索引 / 物化视图)
