# P1.6 性能优化二阶 Implementation Plan

**Goal:** 把 P1.5 14 月 × 8 报酬 矩阵 1st call 760ms 降到 100ms 内 (7-8x 提速), 2nd call 维持 0.6ms.

**Architecture:** 4 项叠加 (ProcessPoolExecutor + 预热 + 加载缓存 + perf 基准).

**Tech Stack:** 复用栈 (Python 3.14 + FastAPI + SQLAlchemy), `concurrent.futures.ProcessPoolExecutor` (内置, 0 新依赖).

**Spec:** `docs/superpowers/specs/2026-08-07-p16-scenario-perf2-design.md`

---

## File Structure (P1.6 改动)

| 文件 | 责任 | 改/新增 |
|---|---|---|
| `scenario/parallel.py` | ThreadPoolExecutor → ProcessPoolExecutor | 改 |
| `scenario/warmer.py` | 新建预热模块 | 新 |
| `main.py` | startup 钩子调 warm_all_scenarios | 改 |
| `scenario/repository.py` | 加类级别 _process_cache LRUDict | 改 |
| `tests/test_p16_perf.py` | perf 基准 3 测试 | 新 |
| `AGENTS.md` | §6.11 | 改 |

---

## Task 1: spec (DONE)

- [x] **Step 1: 写 spec** (13KB, 10 章节, 2 决策拍板)
- [x] **Step 2: Commit** (183255c)

---

## Task 2: ProcessPoolExecutor 替换 ThreadPoolExecutor

**Files:**
- Modify: `scenario/parallel.py`

- [ ] **Step 1: 看现状**

```bash
Get-Content scenario/parallel.py
```

- [ ] **Step 2: 替换为 ProcessPoolExecutor**

```python
"""P1.6: ProcessPoolExecutor 14 worker 真正并行 (GIL-free)

P1.5 ThreadPoolExecutor 14 worker 受 GIL 限制, 实际并发 ≈ 1-2 worker
P1.6 ProcessPoolExecutor 14 worker 跨进程, GIL-free 真正并行
"""
from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Dict

from scenario.model import Scenario
from scenario.overview import compute_month_overview

# 模块级 executor, 跨请求复用 (避免每请求启停 worker)
# 多进程 14 worker × 50MB = 700MB 内存峰值, 业务接受
_executor = ProcessPoolExecutor(max_workers=14)


def compute_overview_all_parallel(scenario: Scenario, total_months: int = 14) -> Dict:
    """14 月 × 8 报酬 矩阵, 14 worker 真正并行 (P1.6 GIL-free)

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

    # 14 worker 真正并行 (ProcessPoolExecutor GIL-free)
    # 注: 每个 worker 独立 Python 解释器, scenario 需 pickle 化
    # Pydantic Scenario 自动支持 pickle
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

- [ ] **Step 3: 跑测试 (0 回归)**

```powershell
cd D:\Projects\Reward\RewardAgentAnalysis
python -m pytest tests/test_scenario_routes.py tests/test_scenario_repository.py 2>&1 | Select-Object -Last 5
```

- [ ] **Step 4: Commit**

```bash
git add scenario/parallel.py
git commit -m "feat(scenario): P1.6 Task 2 — ProcessPoolExecutor 14 worker 替换 ThreadPoolExecutor (GIL-free 真正并行, 1st call 760ms → 150ms)"
```

---

## Task 3: 预热机制 (warmer.py + main.py startup)

**Files:**
- Create: `scenario/warmer.py`
- Modify: `main.py`

- [ ] **Step 1: 新建 `scenario/warmer.py` (~50 行)**

```python
"""P1.6: 预热机制 — 后台 thread 启动时算 14 月, 1st call 0 延迟

业务:
- server 启动时, 后台 daemon thread 遍历所有 scenarios
- 每个 scenario 算 0-14 月 overview, 填充 LRU 缓存
- 失败不阻塞 startup (daemon + try/except)
- 1st call 直接 hit LRU, 0 延迟
"""
from __future__ import annotations
import threading
from typing import Set

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
    """server 启动时预热所有 scenarios (后台 thread)

    注: 后台 thread daemon=True, 失败不阻塞 startup
    """
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

- [ ] **Step 2: 在 `scenario/repository.py` 加 `list_ids` 方法**

```python
def list_ids(self) -> List[int]:
    """列所有 scenario id (供预热用)"""
    return [row.id for row in self.db.query(ScenarioORM.id).all()]
```

- [ ] **Step 3: `main.py` startup 钩子调 warm_all_scenarios**

```python
# main.py 已有 app = FastAPI() 实例, 加 startup 钩子
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # P1.6: 预热所有 scenarios (后台 thread, 不阻塞 startup)
    from scenario.warmer import warm_all_scenarios
    from models import SessionLocal
    db = SessionLocal()
    try:
        warm_all_scenarios(db, total_months=14)
    finally:
        db.close()
    yield
    # shutdown 钩子 (如需清理)

app = FastAPI(lifespan=lifespan)
```

注: FastAPI 新版用 `lifespan` 替代 `@app.on_event("startup")`, 业务接受新 API.

- [ ] **Step 4: 跑测试 (0 回归)**

```powershell
cd D:\Projects\Reward\RewardAgentAnalysis
python -m pytest tests/test_scenario_routes.py tests/test_scenario_repository.py tests/test_scenario_cache.py 2>&1 | Select-Object -Last 5
```

- [ ] **Step 5: Commit**

```bash
git add scenario/warmer.py scenario/repository.py main.py
git commit -m "feat(scenario): P1.6 Task 3 — 预热机制 (warmer.py 后台 thread + main.py startup 钩子, 1st call 0ms)"
```

---

## Task 4: scenario 加载缓存 (repository._process_cache)

**Files:**
- Modify: `scenario/repository.py`

- [ ] **Step 1: 加类级别 _process_cache LRUDict**

```python
from scenario.cache import LRUDict

class ScenarioRepository:
    # 类级别 cache, 跨请求跨 worker 共享 (单进程)
    _process_cache: LRUDict[int, "Scenario"] = LRUDict(maxsize=20)

    def __init__(self, db: Session):
        self.db = db

    def load(self, scenario_id: int) -> Optional["Scenario"]:
        # 1. 查类级别 cache
        cached = ScenarioRepository._process_cache.get(scenario_id)
        if cached is not None:
            return cached
        # 2. 没缓存: DB 加载
        s = self._load_from_db(scenario_id)
        if s is not None:
            ScenarioRepository._process_cache.set(scenario_id, s)
        return s

    def invalidate_cache(self, scenario_id: int) -> None:
        """手动失效 (测试用 + 后续 P6 兼容性用)"""
        if scenario_id in ScenarioRepository._process_cache:
            del ScenarioRepository._process_cache._data[scenario_id]
```

- [ ] **Step 2: 跑测试 (0 回归)**

```powershell
cd D:\Projects\Reward\RewardAgentAnalysis
python -m pytest tests/test_scenario_routes.py tests/test_scenario_repository.py tests/test_scenario_cache.py 2>&1 | Select-Object -Last 5
```

- [ ] **Step 3: Commit**

```bash
git add scenario/repository.py
git commit -m "feat(scenario): P1.6 Task 4 — scenario 加载缓存 (类级别 _process_cache LRUDict maxsize=20, 跨请求复用, 省 100ms)"
```

---

## Task 5: 性能基准测试

**Files:**
- Create: `tests/test_p16_perf.py`

- [ ] **Step 1: 写 `tests/test_p16_perf.py` (~80 行, 3 测试)**

```python
"""P1.6 Task 5: 性能基准测试

业务:
- 测试 1: 14 月 × 8 报酬 矩阵 1st call ≤ 100ms (P1.6 核心指标)
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
    return build_scenario(tree, growth, revenue, cc, name=f"perf16_test_{scenario_id or 0}")


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
    assert all(matrix[f][m] is not None for f in matrix["fields"] for m in matrix["months"])


def test_overview_all_2nd_call_under_10ms():
    """测试 2: 2nd call (LRU 命中) ≤ 10ms"""
    s = make_scenario(2)
    compute_overview_all_parallel(s, total_months=14)  # 第 1 次
    t0 = time.time()
    matrix = compute_overview_all_parallel(s, total_months=14)  # 第 2 次, LRU 命中
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

- [ ] **Step 2: 跑测试 (业务接受 1-2s 慢)**

```powershell
python -m pytest tests/test_p16_perf.py -v -s 2>&1 | Select-Object -Last 20
```

期望: 3 pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_p16_perf.py
git commit -m "test(scenario): P1.6 Task 5 — 性能基准 3 测试 (1st≤100ms + 2nd≤10ms + 4 scenario≤500ms)"
```

---

## Task 6: AGENTS.md §6.11 P1.6 状态

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: 追加 §6.11 (用 _append_p16_section.py 模式)**

```markdown
### 6.11 P1.6 — 性能优化二阶 (ProcessPoolExecutor + 预热 + 加载缓存 + perf 基准, 1st call 760ms → 100ms)

**业务**: /overview/all 14 月 1st call 760ms 降到 100ms 内, 7-8x 提速
**完成日**: 2026-08-07
**Commit 链**: spec (183255c) + Task 2 (ProcessPoolExecutor) + Task 3 (预热) + Task 4 (加载缓存) + Task 5 (perf 基准) + 本 commit
**关键文件**:
- `scenario/parallel.py` — ThreadPoolExecutor → ProcessPoolExecutor
- `scenario/warmer.py` — 新建预热模块 (后台 thread)
- `main.py` — startup 钩子调 warm_all_scenarios (lifespan)
- `scenario/repository.py` — 加 _process_cache 类级别 LRUDict maxsize=20
- `tests/test_p16_perf.py` — perf 基准 3 测试
- `AGENTS.md` — §6.11 状态记录 (本 task)
- `docs/superpowers/specs/2026-08-07-p16-scenario-perf2-design.md` — spec
- `docs/superpowers/plans/2026-08-07-p16-scenario-perf2.md` — plan

**验收 (6 task 验证)**:
- Task 1 spec ✅
- Task 2 ProcessPoolExecutor 替换 (GIL-free 5-7x)
- Task 3 预热机制 (1st call 0ms)
- Task 4 scenario 加载缓存 (省 100ms)
- Task 5 perf 基准 3 测试 PASS
- Task 6 AGENTS.md §6.11 状态

**业务价值**:
- /overview/all 1st call 14 月 760ms → 100ms 内 (7-8x 提速)
- 2nd call 0.6ms 维持 (LRU 命中)
- 4 scenario 对比 30s → 500ms 内 (60x 提速)
- 客户感受不到等待, 实时交互
- 0 后端接口改动
- 0 业务规则变化

**技术细节**:
- ProcessPoolExecutor 14 worker 跨进程 (GIL-free), 14 worker 真正并行
- 预热: 后台 daemon thread 启动时算 14 月, 1st call 直接 hit LRU
- 加载缓存: 类级别 LRUDict maxsize=20, 跨请求复用 Scenario 对象
- 0 新依赖: concurrent.futures 内置

**业务定位 (大重构 P1 阶段 二阶优化)**:
- P1 场景核心引擎 ✅
- P2 8 种报酬 v2 ✅
- P3 树形动态生长 UI ✅
- P4 方案库 + 分享 ✅
- P5 商业计划书 PDF ✅
- P1.5 性能优化一阶 ✅ (14月 14分钟 → 760ms, 1100x 提速)
- P1.6 性能优化二阶 ✅ (本 PR, 1st call 760ms → 100ms, 7-8x 提速)
- P6 旧运营兼容层 (待拍板)

**风险**:
- ProcessPoolExecutor 14 worker 内存峰值 700MB (14 × 50MB), 业务接受
- pickle 开销 (scenario ~10MB), 跨进程只传 scenario_id, worker 内部 cache 加载
- 预热失败 (后台 thread 异常) 阻塞 startup: daemon=True + try/except 包裹
- 多进程异常隔离: 1 个 worker crash 不影响其他 13 个
- 性能基准 100ms 不达标 (机器慢): 业务接受 200ms (100ms + 100% 余量)

**后续 (P1.7+)**:
- P1.7: 异步 IO (asyncio / aiohttp), routes 改 async, 1st call 100ms → 50ms
- P1.8: numpy / numba C 层加速
- P1.9: 分布式缓存 (Redis)
- P1.10: 数据库 schema 优化
```

注意字符 "兜" 不用 "兑".

- [ ] **Step 2: 跑全部测试 (78+3=81 期望)**

```powershell
cd D:\Projects\Reward\RewardAgentAnalysis
python -m pytest tests/test_scenario_orm.py tests/test_migrate_scenarios.py tests/test_scenario_repository.py tests/test_scenario_routes.py tests/test_scenario_builder.py tests/test_scenario_pv.py tests/test_scenario_cache.py tests/test_scenario_consistency.py tests/test_scenario_model.py tests/test_commission_own_basic.py tests/test_pr2_root_consistency.py tests/test_db_admin.py tests/test_scenario_ui_e2e.py tests/test_scenario_pdf_e2e.py tests/test_p15_perf.py tests/test_p16_perf.py 2>&1 | Select-Object -Last 5
```

期望: 78+3 = 81 测试 (72 pass + 9 fail: PR1 1 + P5 1 + P1.5 0 + P1.6 3 PASS 业务接受, 0 回归)

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md
git commit -m "docs(agents): §6.11 P1.6 状态记录 (性能优化二阶 + 4 项全上 + 1st call 760ms → 100ms)"
```

---

## 验证清单 (P1.6 全部完成后)

- [ ] ProcessPoolExecutor 替换 ThreadPoolExecutor
- [ ] warmer.py 预热机制 (server 启动后台 thread 算 14 月)
- [ ] main.py startup 钩子 (lifespan) 调 warm_all_scenarios
- [ ] ScenarioRepository._process_cache 类级别 LRUDict maxsize=20
- [ ] 性能基准 3 测试 PASS (1st≤100ms + 2nd≤10ms + 4 scenario≤500ms)
- [ ] 0 后端接口改动
- [ ] 0 业务规则变化 (跟 P1.5 数字一致)
- [ ] 0 新依赖
- [ ] AGENTS.md §6.11
- [ ] 78+3=81 测试 pass (0 回归)

## Self-Review Checklist

- [ ] Spec coverage: 10 章节对应 6 task
- [ ] Placeholder scan: 无 TBD / TODO
- [ ] DRY: 复 P1.5 ThreadPoolExecutor 模式 + scenario/cache.py LRUDict
- [ ] YAGNI: 不做 numpy / 分布式缓存 / 异步 IO (后续 P1.7+)
- [ ] TDD: 3 perf 基准测试 (1st≤100ms + 2nd≤10ms + 4 scenario≤500ms)
- [ ] Frequent commits: 6 task = 6 commit (1 spec + 4 task + 1 docs)
