# P1 场景核心引擎 — 设计文档

> 日期: 2026-08-07
> 状态: 设计敲定, 待 review
> 作者: Mavis (跟用户 8 轮 brainstorming 产出)

---

## 1. 目标

把现有 `tools/rebuild_2144_simulation.py`（一次性 24KB 模拟脚本）重构为 first-class `scenario/` 库 + 持久化 + 3 个 HTTP 路由。客户在路演现场能通过 8+ 参数 + 4 个预设方案（进取/稳健/保守/镜像）+ 2 叉/4 叉 切换，**实时看到 8 种报酬方式 + 横向/纵向分红在 3 年的累计曲线**。

P1 是「分析推理系统」大重构（用户 2026-08-07 拍板）的**第一个子项目**，为 P2-P6 提供业务核心。

**P1 范围边界**:
- ✅ 包含: scenario 数据模型 + 业务算法 (8 种报酬) + scenarios 表 + 3 个 HTTP API
- ❌ 不包含: 树形 UI (P3)、预设方案库 (P4)、商业计划书导出 (P5)、旧运营兼容 (P6)
- 客户在路演现场调的是 4 组参数 (tree_shape + growth + revenue + commission_config) 共 30+ 字段, 不是 8 个参数
- 8+ 客户调参数的"方案库"是 P4 范围, P1 只提供"任意参数都能跑"的能力

### 1.1 业务验收标准

PR4 跑通时：
- ✅ 跟旧版 `tools/rebuild_2144_simulation.py` 跑出**完全相同**的 Root 收入 **$1,024,983**（15 月 2 叉 9 层 1500PV 方案）
- ✅ 8 种报酬方式各自金额完全一致：
  - ownBasic $30,001.50
  - pairBonus $251,831.53
  - teamBonus $480,150.00
  - savings $4,500.22
  - 纵向领袖分红 $236,000
  - 横向领袖分红 $22,500
  - retail_profit $0 (非 commission)
  - opportunity_points 0 (第 8 种未实现)
- ✅ L1-L4 各层各月 IP 触发状态一致
- ✅ 4 叉方案 Root 收入 $660,179 一致
- ✅ 1000PV 方案 Root 收入 $555,626 一致
- ✅ 800PV / 各种 NODES_PER_REGION_PER_WEEK 跑出数字一致

### 1.2 工程验收标准

- ✅ 4 个 PR 全部通过测试 (pytest 35+ 个)
- ✅ 旧 `skills/` + `main.py` 在 PR1-PR3 期间**零改动**（PR4 才切换 + 删除）
- ✅ 新 `scenario/` 模块单测覆盖率 ≥ 80%
- ✅ LRU 缓存命中率 ≥ 60%（路演现场 5+ 个对比场景下，重复查相同 month）

### 1.3 退出标准

P1 完成 = 业务/工程/文档 15 项全过（详见 §5）。

---

## 2. 架构

### 2.1 模块图

```
┌─────────────────────────────────────────────────────────────┐
│              static/index.html (P3 树形 UI)                  │
│              fetch('/api/scenarios/...')                     │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTP
┌────────────────────▼────────────────────────────────────────┐
│              scenario_routes.py (PR3 加)                     │
│  - POST   /api/scenarios                  (建场景)           │
│  - GET    /api/scenarios/{id}/state?m&bfs  (取节点状态)     │
│  - GET    /api/scenarios/{id}/overview?m   (取当月总览)     │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────▼────────────┐
        │  scenario/ 库 (PR1)     │
        │  ├─ model.py (dataclass)│
        │  ├─ builder.py (构树)   │
        │  ├─ commission/         │
        │  │  ├─ own_basic.py     │
        │  │  ├─ pair_bonus.py    │
        │  │  ├─ team_bonus.py    │
        │  │  ├─ savings.py       │
        │  │  ├─ leader.py        │
        │  │  └─ horizontal.py    │
        │  ├─ cache.py (LRU)      │
        │  └─ repository.py (DB)  │
        └────────────┬────────────┘
                     │ 吃 Scenario / 返回 CommissionBreakdown
        ┌────────────▼────────────┐
        │  skills/ 7 文件改写 (PR2)│
        │  从「对 members 跑」     │
        │  →「对 Scenario 跑」    │
        └────────────┬────────────┘
                     │
        ┌────────────▼────────────┐
        │  SQLite scenarios 表     │
        │  (PR3 加, 拍平 40 列)    │
        └─────────────────────────┘
```

### 2.2 数据流（一次"取节点状态"调用）

```
HTTP GET /api/scenarios/42/state?month=5&bfs_id=10
  ↓
scenario_routes.get_state(scenario_id=42, month=5, bfs_id=10)
  ↓
ScenarioRepository.load(scenario_id=42)         # 从 DB 读 4 组参数
  ↓
Scenario.build(params)                           # 构树 (缓存命中则跳)
  ↓ (缓存 miss)
compute_commission_breakdown(scenario, m=5)      # 调 8 个 commission 函数
  ↓
{ownBasic, pairBonus, teamBonus, savings,
 leader, horizontal, retail, points, total,
 ip_chain, is_optimized, cumulative} for bfs_id=10
  ↓
HTTP 200 JSON
```

### 2.3 关键设计决策

1. **scenario_routes.py 是新文件**，不修改 main.py（PR1-PR3 期间 main.py + skills/ 0 改动）
2. **scenario/commission/* 是新模块**，从 skills/ 抽出纯函数，skills/ 旧函数 PR2 期间保留，PR4 删除
3. **scenarios 表是新增表**，不替换任何现有表（members / pv_ledger / commission_periods / order_items 全部保留）
4. **PR4 删 `tools/rebuild_2144_simulation.py`** 是唯一删除动作
5. **业务算法边界**：现有 `skills/pair_commission.py._settle_node` 接收 ORM 对象，新设计改为接收 `Scenario + bfs_id + month` 三个参数，返回 `Decimal` 金额

---

## 3. Scenario 数据模型

### 3.1 4 个 dataclass + Scenario 容器 + 2 个输出

```python
# scenario/model.py

@dataclass(frozen=True)
class TreeShape:
    """树形: 叉数 + 层级 + 节点数"""
    fork_type: str             # "binary" | "four_way" | "eight_way"
    max_level: int             # 树最大深度 (L0-L9 = 9, L0-L14 = 14)
    layer_counts: Dict[int, int]  # {0: 1, 1: 4, 2: 8, ..., 9: 1024}

@dataclass(frozen=True)
class Growth:
    """增长: 速度 + 加入顺序"""
    nodes_per_region_per_week: int  # 9 (4 大区 × 9 = 36/周)
    n_regions: int                  # 4
    join_strategy: str              # "round_robin" | "bfs" | "random"
    weeks_per_month: int            # 4

@dataclass(frozen=True)
class Revenue:
    """收入: PV + 颜色规则"""
    initial_pv: int                 # 1500 (新成员首月)
    monthly_renew_pv: int           # 100 (续费月)
    color_rule: str                 # "4_color_cycle" (红/紫/青绿/蓝)
    color_names: Tuple[str, ...]    # ("红", "紫", "青绿", "蓝")

@dataclass(frozen=True)
class CommissionConfig:
    """8 种报酬方式 + 参数 (含 PR #71 #72 #74 全部业务规则)"""
    enable_retail_profit: bool       # 1 零售利润 (非 commission)
    enable_team_bonus: bool          # 2 培育奖金
    team_bonus_tier_rates: Dict[int, float]  # {200: 0.15, 500: 0.20, 1000: 0.25, 1500: 0.30}
    team_bonus_window_weeks: int     # 4 (前 4 周订单窗口, 2026-08-07 选项 B)
    enable_own_basic: bool           # 3 基本佣金
    own_basic_rate: float            # 0.15
    own_basic_line_pv_cap: int       # 13334 (PR #72)
    enable_savings: bool             # 4 储蓄奖金 (PR #73)
    savings_usd_threshold: float     # 250
    savings_rate: float              # 0.15
    savings_cap_usd: float           # 500
    enable_pair_bonus: bool          # 7 对等奖金 (PR #74)
    pair_bonus_ratios: Dict[int, float]  # {1: 0.15, 2: 0.10, 3: 0.05, ...}
    pair_bonus_4th_usd_threshold: float  # 500
    pair_bonus_5th_usd_threshold: float  # 1000
    enable_leader_dividend: bool     # 5 纵向领袖分红 (2026-08-07)
    leader_dividend_threshold_pv: int   # 13334 (周)
    leader_dividend_share_usd: float    # 500
    leader_dividend_tiers: Dict[int, int]  # {1: 2, 2: 4, 3: 6, 4: 8}
    enable_horizontal_leader: bool   # 6 横向领袖分红 (2026-08-07)
    horizontal_leader_share_usd: float   # 250
    horizontal_leader_tiers: Dict[int, int]  # {1: 2, 2: 2, 3: 4, 4: 6}
    enable_opportunity_points: bool  # 8 机遇积分 (未实现, 留接口)


@dataclass(frozen=True)
class Scenario:
    """场景容器: 4 组参数 + 派生计算结果"""
    id: Optional[int]                # DB id (None = 内存临时场景)
    name: str                        # "2叉9层_1500PV_进取方案"
    tree_shape: TreeShape
    growth: Growth
    revenue: Revenue
    commission_config: CommissionConfig
    total_target: int                # 2144 (全网点位目标)
    total_weeks: int                 # 60 (派生: 2叉9层布局完成)
    total_months: int                # 15
    # 运行时缓存 (非 frozen 字段)
    _cache: Dict[int, MonthSnapshot]  # month → MonthSnapshot (LRU maxsize=50)


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
    retail_profit_usd: Decimal       # 1 零售利润 (非 commission)
    opportunity_points: int          # 8 机遇积分
    total_usd: Decimal
    # 触发门槛状态
    ip_chain_status: List[Tuple[int, int, int, int, bool, int]]  # (region, ip_level, l1, l2, ok, shares)
    is_optimized_region: bool        # 横向: 该节点子树 >= 53K
    cumulative_to_date_usd: Decimal  # 月累计到该月


@dataclass(frozen=True)
class MonthSnapshot:
    """某月全网所有节点状态 (缓存粒度)"""
    month: int
    nodes_state: Dict[int, CommissionBreakdown]  # bfs_id → breakdown
    aggregate: Dict[str, Decimal]     # 全网合计 {"ownBasic": ..., "pairBonus": ...}
```

### 3.2 SQLite scenarios 表（PR3 加, 拍平 40 列）

```sql
CREATE TABLE scenarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    -- tree_shape
    tree_fork_type TEXT NOT NULL,           -- "binary" | "four_way" | "eight_way"
    tree_max_level INTEGER NOT NULL,         -- 9 / 14
    tree_layer_counts_json TEXT NOT NULL,    -- {"0":1,"1":4,...}
    -- growth
    growth_nodes_per_region_per_week INTEGER NOT NULL,  -- 9
    growth_n_regions INTEGER NOT NULL,       -- 4
    growth_join_strategy TEXT NOT NULL,      -- "round_robin"
    growth_weeks_per_month INTEGER NOT NULL, -- 4
    -- revenue
    revenue_initial_pv INTEGER NOT NULL,     -- 1500
    revenue_monthly_renew_pv INTEGER NOT NULL,  -- 100
    revenue_color_rule TEXT NOT NULL,        -- "4_color_cycle"
    revenue_color_names_json TEXT NOT NULL,  -- ["红","紫","青绿","蓝"]
    -- commission_config (8 种报酬 enable + 参数)
    cc_enable_retail_profit BOOLEAN NOT NULL,
    cc_enable_team_bonus BOOLEAN NOT NULL,
    cc_team_bonus_tier_rates_json TEXT NOT NULL,  -- {"200":0.15,...}
    cc_team_bonus_window_weeks INTEGER NOT NULL,
    cc_enable_own_basic BOOLEAN NOT NULL,
    cc_own_basic_rate REAL NOT NULL,
    cc_own_basic_line_pv_cap INTEGER NOT NULL,
    cc_enable_savings BOOLEAN NOT NULL,
    cc_savings_usd_threshold REAL NOT NULL,
    cc_savings_rate REAL NOT NULL,
    cc_savings_cap_usd REAL NOT NULL,
    cc_enable_pair_bonus BOOLEAN NOT NULL,
    cc_pair_bonus_ratios_json TEXT NOT NULL,
    cc_pair_bonus_4th_usd_threshold REAL NOT NULL,
    cc_pair_bonus_5th_usd_threshold REAL NOT NULL,
    cc_enable_leader_dividend BOOLEAN NOT NULL,
    cc_leader_dividend_threshold_pv INTEGER NOT NULL,
    cc_leader_dividend_share_usd REAL NOT NULL,
    cc_leader_dividend_tiers_json TEXT NOT NULL,
    cc_enable_horizontal_leader BOOLEAN NOT NULL,
    cc_horizontal_leader_share_usd REAL NOT NULL,
    cc_horizontal_leader_tiers_json TEXT NOT NULL,
    cc_enable_opportunity_points BOOLEAN NOT NULL,
    -- 派生
    total_target INTEGER NOT NULL,            -- 2144
    total_weeks INTEGER NOT NULL,             -- 60
    total_months INTEGER NOT NULL             -- 15
);
```

### 3.3 Layer_counts JSON 示例

- 2叉9层: `{"0":1,"1":4,"2":8,"3":16,"4":32,"5":64,"6":128,"7":256,"8":512,"9":1024,"10":99}` (2144)
- 4叉6层: `{"0":1,"1":4,"2":16,"3":64,"4":256,"5":1024,"6":779}` (2144)
- 8叉4层: `{"0":1,"1":8,"2":64,"3":512,"4":1559}` (2144)

---

## 4. 4 个 PR 拆分

### 4.1 PR1: scenario 库核心 + 树形构建（估 5-7 天）

**新增文件**:
- `scenario/__init__.py` (导出 Scenario)
- `scenario/model.py` (5 个 dataclass: TreeShape, Growth, Revenue, CommissionConfig, Scenario, CommissionBreakdown, MonthSnapshot)
- `scenario/builder.py` (build_scenario() — 从参数构 BFS 树 + 总周/月数)
- `scenario/cache.py` (LRU cache: lru_cache 装饰器 + TTL)
- `scenario/_pv.py` (compute_monthly_pv() / compute_weekly_period_pv() — 从 rebuild_2144_simulation.py 迁移)
- `tests/test_scenario_model.py` (dataclass 单测)
- `tests/test_scenario_builder.py` (2叉9层 2144 / 4叉6层 2144 / 8叉4层 2144)

**PR1 验收**:
- ✅ `Scenario.build(tree_shape, growth, revenue, commission_config).total_nodes == 2144` 对 3 种 fork_type 都成立
- ✅ `scenario.get_pv(scenario, bfs_id=10, month=5)` 返回正确累计 PV
- ✅ 旧 `tools/rebuild_2144_simulation.py` 行为**不变** (0 改动)

### 4.2 PR2: 8 种报酬纯函数 + skills/ 改写（估 7-10 天）

**新增文件**:
- `scenario/commission/__init__.py`
- `scenario/commission/own_basic.py` (compute_own_basic_for_node, compute_own_basic_for_month)
- `scenario/commission/pair_bonus.py` (compute_ancestor_share, 含 PR #74 4-5 USD 门槛)
- `scenario/commission/team_bonus.py` (compute_team_bonus_for_node, 含 PR #71 4 档 + 4 周窗口)
- `scenario/commission/savings.py` (PR #73)
- `scenario/commission/leader.py` (PR #72 v2 纵向领袖分红, IP 链)
- `scenario/commission/horizontal.py` (横向领袖分红)
- `scenario/commission/retail_profit.py` (PR #70 下单管理, 非 commission)
- `scenario/commission/opportunity.py` (第 8 种, 留接口 raise NotImplementedError)
- `scenario/breakdown.py` (compute_commission_breakdown(scenario, bfs_id, month) → CommissionBreakdown)
- `scenario/overview.py` (compute_month_overview(scenario, month) → Dict[总计])
- `tests/test_commission_*.py` (8 个测试文件, 每个 5+ 用例)

**改写 `skills/`（但不删除, PR4 删）**:
- `skills/pair_commission.py` — `_settle_node` 提取为 `scenario/commission/own_basic.py.compute_own_basic_for_node`; skills/ 改为调用 scenario 函数
- `skills/skill_5_lib.py`, `skills/period.py` — 同上提取

**PR2 验收**:
- ✅ `compute_commission_breakdown(s_2fork, bfs_id=0, month=14).total_usd` = $1,024,983 / 15 ≈ $68,332
- ✅ 旧 `main.py` 调 `settle_period` 仍能跑（业务数据不变）
- ✅ pytest 全通过 (旧 + 新)

### 4.3 PR3: scenarios 表 + 3 个 HTTP 路由（估 3-5 天）

**新增文件**:
- `scenario/repository.py` (ScenarioRepository: save / load / list / delete)
- `scenario_routes.py` (3 个路由):
  - `POST /api/scenarios` body={4 组参数 + name} → 201 {id}
  - `GET /api/scenarios/{id}/state?month=5&bfs_id=10` → CommissionBreakdown JSON
  - `GET /api/scenarios/{id}/overview?month=5` → 全网当月合计
- `tools/migrate_add_scenarios_table.py` (idempotent, 创建 scenarios 表)
- `tests/test_scenario_routes.py` (httpx 异步测试)

**PR3 验收**:
- ✅ `POST /api/scenarios` 创建一个 2叉9层1500PV场景，DB 写 1 行
- ✅ `GET /api/scenarios/1/state?month=14&bfs_id=0` 返 8 种报酬 + 累计
- ✅ 同一 scenario 重复查同 month, 第二次走 LRU 缓存 (log "cache hit")
- ✅ 旧 `main.py` 路由 + `skills/` 行为不变 (0 改动)

### 4.4 PR4: 迁移 + 数字一致性验证 + 删除旧脚本（估 2-3 天）

**改写**:
- `tools/rebuild_2144_simulation.py` → 改用 `scenario/` 重写, 跑 15 月输出报表 (验证数字一致)
- `main.py` — 切换到 `scenario/` 作为业务核心, `skills/` 旧函数标记 deprecated
- `AGENTS.md` — §6 新增 P1 章节

**删除**:
- `tools/rebuild_2144_simulation.py` (业务逻辑全部迁走, 文件删)
- `skills/pair_commission.py`, `skills/skill_5_lib.py`, `skills/period.py` (改写后删除旧实现)

**PR4 验收**:
- ✅ **数字一致性**: `python -c "from scenario import build_default; s = build_default('2fork_9layer_1500pv'); [print(m, s.get_state(m, 0).total_usd) for m in range(15)]"` 跑出 跟旧 `tools/_final_output_v3.txt` 完全一致
- ✅ Root 15 月累计 = $1,024,983
- ✅ 4 叉方案 Root 15 月累计 = $660,179
- ✅ 1000PV 方案 Root = $555,626
- ✅ 旧 `tests/test_pair_commission.py`, `test_settle_e2e.py` 全部通过 (现在走新库)
- ✅ pytest 全 35+ 个测试通过

### 4.5 PR 顺序依赖图

```
PR1 (核心库)
  ↓
PR2 (业务算法)
  ↓
PR3 (持久化 + 路由)
  ↓
PR4 (迁移 + 验证 + 删旧)
```

**P1 总时间估算**: 17-25 天 ≈ **4-6 周**

**Plan 拆分建议** (writing-plans 阶段会拆 4 个子 plan):
- `plan-p1-pr1.md` — scenario 库核心 (5-7 天)
- `plan-p1-pr2.md` — 8 种报酬纯函数 (7-10 天)
- `plan-p1-pr3.md` — scenarios 表 + 3 个 HTTP 路由 (3-5 天)
- `plan-p1-pr4.md` — 迁移 + 数字一致性验证 + 删除旧脚本 (2-3 天)

**关键不变量**（4 PR 全程保持）:
- `main.py` 1-75 PR 业务路由在 PR1-PR3 期间 0 改动
- `members` / `pv_ledger` / `commission_periods` / `order_items` 表 0 改动
- `tests/test_*.py` 0 改动 (PR4 才改 import)

---

## 5. 风险 + 退出标准

### 5.1 主要风险

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| **数字漂移** (新库跟旧库跑出不一致) | 中 | 高 — 业务错误 | PR4 强制对比 `_final_output_v3.txt` 每行每列, 任何 0.01 差异都回滚 |
| **PR2 抽纯函数破坏 skills/** | 中 | 高 — 1-75 PR 业务全断 | PR2 期间 skills/ 旧函数**保留**, 新旧并存, PR3 跑完业务路由仍走旧函数, PR4 才删 |
| **scenarios 表设计过死** (40 列拍平后改不动) | 中 | 中 | 关键参数 (8 种 enable + tier rates) 留 JSON 列, 字段调整时只改 JSON 不动表 |
| **LRU 缓存导致内存爆炸** | 低 | 中 | 限制 maxsize=50, 用 functools.lru_cache 自动淘汰 |
| **P2/P3 子项目接口变化需要回头改 P1** | 中 | 中 | P1 CommissionBreakdown 字段固定 12 个, P2 不会动 |
| **scenario/ 库跟 rebuild_2144_simulation.py 业务漂移** | 中 | 中 | P1 期间用 `tools/rebuild_2144_simulation.py` 跑业务**冻结**, 所有参数修改通过 `scenario/` |
| **pytest 跑前/跑后 DB 状态不一致** | 中 | 中 | PR4 加 scenario 测试用内存 SQLite `:memory:` 不污染 live DB |
| **node_modules / static 旧代码引用** (P3 还没做, static/ 旧 index.html 还在) | 低 | 低 | PR1-PR3 期间 static/ 一行不动, P3 才重写 |

### 5.2 风险触发回滚条件

- PR2 后任何 `test_*.py` 失败 → 立即修, 不带病进 PR3
- PR4 数字一致性验证失败 → 不合并, 回 PR3 排查
- 任何 PR 超过预估时间 50% → 暂停, 重新评估

### 5.3 退出标准

P1 完成 = 业务/工程/文档 15 项全过：

**业务（6 项）**:
1. ✅ `scenario/` 库跑出 Root 15 月累计 $1,024,983 (跟旧模拟器 0 差异)
2. ✅ 4 叉方案 Root $660,179 一致
3. ✅ 1000PV 方案 Root $555,626 一致
4. ✅ 8 种报酬方式 (含未实现第 8 种留 NotImplementedError) 全部能调
5. ✅ 3 个 HTTP 路由可调用, 返 JSON
6. ✅ LRU 缓存命中率 ≥ 60% (路演场景)

**工程（6 项）**:
7. ✅ 4 个 PR 全部 merge
8. ✅ 35+ 个 pytest 全过 (旧 + 新)
9. ✅ 新 `scenario/` 单测覆盖率 ≥ 80%
10. ✅ 旧 `tools/rebuild_2144_simulation.py` 删除, 旧 `skills/` 业务函数删除
11. ✅ `main.py` 业务路由**0 行为变化** (用户访问旧 URL 行为一致)
12. ✅ `AGENTS.md` §6 新增 P1 章节, §5.1-5.36 旧 PR 业务规则引用不动

**文档（3 项）**:
13. ✅ `docs/superpowers/specs/2026-08-07-p1-scenario-engine-design.md` 文档完成 + commit (本文档)
14. ✅ `AGENTS.md` §6.1-6.5 (P1 子项目状态, 进度, 验证清单) 写完
15. ✅ 设计文档 self-review 4 项 (placeholder/内部一致性/scope/歧义) 全过

### 5.4 P1 完成后, P2-P6 自动解锁

- **P2** (8 种报酬 v2) — 直接基于 `scenario/commission/` 扩展
- **P3** (树形动态生长 UI) — 调 `scenario_routes` 3 个 API
- **P4** (方案库 + 对比) — 加 `presets` 表 + 多 scenario 对比路由
- **P5** (商业计划书导出) — 加 PDF 路由
- **P6** (旧运营兼容层) — 加 `snapshots` 表, 从 members 表建 scenario

每个 P2-P6 都**独立 brainstorm** (按 P1 模板走)。

---

## 附录 A: 跟旧模拟器的代码迁移路径

旧 `tools/rebuild_2144_simulation.py` (24KB) 拆解为：
- **常量** (40+ 个) → `scenario/model.py` CommissionConfig 等 dataclass 字段
- **build_bfs_tree()** → `scenario/builder.py.build_scenario()`
- **compute_monthly_pv()** → `scenario/_pv.py.compute_monthly_pv()`
- **compute_own_basic_at_month()** → `scenario/commission/own_basic.py.compute_own_basic_for_month()`
- **compute_ancestor_share()** → `scenario/commission/pair_bonus.py.compute_ancestor_share()`
- **compute_team_bonus_v3_window()** → `scenario/commission/team_bonus.py.compute_team_bonus()`
- **compute_savings()** → `scenario/commission/savings.py.compute_savings()`
- **compute_leader_dividend()** → `scenario/commission/leader.py.compute_leader_dividend()`
- **compute_horizontal_leader_dividend()** → `scenario/commission/horizontal.py.compute_horizontal_leader_dividend()`
- **main()** 输出报表 → `tools/scenario_report.py` (新工具, PR4 写)

## 附录 B: 跟 skills/ 的边界

| 旧 skills/ 函数 | 新 scenario/ 函数 | PR2 改写方式 |
|---|---|---|
| `pair_commission._settle_node` | `commission/own_basic.compute_own_basic_for_node` | 抽签名 (scenario, bfs_id, month) → Decimal |
| `pair_commission._apply_pairing_bonus` | `commission/pair_bonus.compute_ancestor_share` | 抽签名 + 接受 4-5 USD 门槛 (PR #74) |
| `skill_5_lib.effective_max_active_lines` | `scenario/builder` 内部 | 树构建时算 |
| `period.compute_period_bounds` | `scenario/_pv` 内部 | 月度 PV 计算时算 |
| `pair_commission._settle_period` | 整体逻辑移到 `scenario/breakdown.compute_commission_breakdown` | 改成批量算 monthly |

PR2 期间 skills/ 旧函数 + scenario/ 新函数**并存**, PR4 才删 skills/。
