# P3 PR2 8 种报酬 × 14 月 热图 — Design Spec

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:brainstorming to evolve this design.

**Goal:** 在 `static/scenario.html` 下方加"热图"section, 提交后画 8 种报酬 × 14 月累计热图 (112 格子). 业务分色 (8 行 8 色, 跟 PR1 卡片配色一致). Hover tooltip 0 延迟, click 详情调 GET overview?month=N (60s 一次, 业务接受).

**Architecture:** 后端加 `GET /api/scenarios/{id}/overview/all?total_months=14` 端点, 1 次算 14 月 × 8 报酬 = 112 值. 前端 scenario.html 加 `<section id="heatmap">` 在 8 卡片下方, Canvas 2D 渲染 8 行 14 列. 业务分色 (8 行 8 色) + hover tooltip + click 详情.

**Tech Stack:** 复用 PR1 栈 (Vanilla HTML + CSS + JS, Canvas 2D, 零 npm 依赖). 后端复用 `scenario.overview.compute_month_overview` 串行调用 0-14 月.

**Spec 父**: `docs/superpowers/specs/2026-08-07-p3-scenario-ui-design.md` (PR1 spec)
**Plan**: `docs/superpowers/plans/2026-08-07-p3-scenario-heatmap.md` (TBD)

---

## 1. 业务定位 (User Story)

```
作为 招商/路演客户 (PR1 之后)
我想 在同一页看 8 种报酬 14 月累计趋势 (热图, 1 行 = 1 报酬, 1 列 = 1 月)
为了 1 次看 哪个 报酬 哪月 增长 最猛, 跟客户讲故事
```

**3 类用户视角**:
1. **路演客户** — 看热图, 知道 "PairBonus 14 月累计 $251K" 故事化
2. **销售** — 调 4 组参数, 1 次看 14 月趋势
3. **运营** — 优化 commission 参数, 看历史趋势

**业务目标 (P3 PR2)**:
- 提交场景后, 1 GET 拉 14 月 × 8 报酬 = 112 值
- 热图渲染 8 行 × 14 列 = 112 格子, 业务分色
- Hover tooltip 显示 报酬名 + 月份 + 金额
- Click 格子调 GET overview?month=N, 显示该月详情 (60s 一次, 业务接受)

---

## 2. 范围 (In/Out)

### In Scope (P3 PR2, 1-2 天)
- 后端新端点 `GET /api/scenarios/{id}/overview/all?total_months=14`
- 前端 scenario.html 加 `<section id="heatmap">` 在 8 卡片下方
- Canvas 2D 渲染 8 行 × 14 列热图 (112 格子, 32×24 像素/格)
- 业务分色 (8 行 8 色, 跟 PR1 卡片配色一致)
- Hover tooltip (0 延迟, 客户端展示, 不调 GET)
- Click 格子 → 调 GET overview?month=N → 显示该月 8 报酬详情 (1 个新 modal/card)
- 0 改 main.py, 0 改 scenario_routes.py 已有端点, 0 改 PR1 commit

### Out of Scope (后续 PR)
- 多 scenario 对比 (PR3 拍板)
- 导出 PNG/CSV (PR3 拍板)
- 移动端适配
- 14 月线图 (8 条折线)
- 总月数可调 (UI 滑块)
- 节点级 hover 详情 (跟热图格子无关)

---

## 3. File Structure

| 文件 | 责任 |
|---|---|
| `scenario_routes.py` | 修改: 加 `GET /api/scenarios/{id}/overview/all` 端点 |
| `tests/test_scenario_routes.py` | 修改: 加 1 个 e2e 测试 (PR1 已有 4 个, +1 = 5 个) |
| `static/scenario.html` | 修改: 加 `<section id="heatmap">` 在 8 卡片下方 (30 行) |
| `static/scenario.js` | 修改: 加 `renderHeatmap` + `showMonthDetail` 函数 (80 行) |
| `static/scenario.css` | 修改: 加热图样式 (.heatmap-cell, .heatmap-tooltip, .month-detail) (50 行) |
| `AGENTS.md` | 加 §6.6 P3 PR2 状态记录 |

---

## 4. 页面布局 (Section 加 PR1 同页)

```
[现有 PR1 2 栏布局]

  ... 8 卡片 ...
  [提交按钮]

  ========== 新加 section ==========
  📊 8 种报酬 × 14 月累计热图
  ┌──────────────────────────────────────────────┐
  │ ownBasic  │ ▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │ (14 格子, 业务分色)
  │ pairBonus │ ░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │
  │ teamBonus │ ░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │
  │ savings   │ ░░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │
  │ leader    │ ░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │
  │ horizontal│ ░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │
  │ retail    │ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │
  │ total     │ ░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │
  └──────────────────────────────────────────────┘
  ░ 低 ▓ 中 █ 高 (颜色梯度示意)
  
  [hover 1 格子] → tooltip: "pairBonus, 14月, $251,781"
  [click 1 格子] → modal/card: "该月 8 报酬详情, loading 60s..."
```

---

## 5. 后端新端点 (后端 1 个改动)

### 5.1 `GET /api/scenarios/{id}/overview/all?total_months=14`

```python
@router.get("/{scenario_id}/overview/all")
def get_overview_all(scenario_id: int,
                     total_months: int = Query(14, ge=1, le=15),
                     db: Session = Depends(get_db)) -> Dict[str, Any]:
    """取 scenario 0-total_months 月的 8 报酬 × 月 矩阵 (heatmap 渲染用)
    
    Returns:
        {
            "total_months": 14,
            "fields": ["ownBasic", "pairBonus", ...],
            "months": [0, 1, 2, ..., 14],
            "matrix": {
                "ownBasic": ["0", "100", ..., "30001.5"],  # 15 个 string
                "pairBonus": ["0", "100", ..., "251781.27"],
                ...
            }
        }
    """
    repo = ScenarioRepository(db)
    s = repo.load(scenario_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"scenario {scenario_id} not found")
    # 复用 compute_month_overview, 0-total_months 月串行
    fields = ["ownBasic", "pairBonus", "teamBonus", "savings",
              "leader", "horizontal", "retail", "total"]
    months = list(range(0, total_months + 1))
    matrix = {f: [None] * (total_months + 1) for f in fields}
    for m in months:
        overview = compute_month_overview(s, month=m)
        for f in fields:
            matrix[f][m] = str(overview.get(f, "0"))
    return {
        "total_months": total_months,
        "fields": fields,
        "months": months,
        "matrix": matrix,
    }
```

### 5.2 性能

- 14 月 × 60s/月 (PR1 实测) = 14 分钟, 业务不理想
- 优化路径 (PR2 不修, 拍板接受):
  - 后端 1 次算 14 月 = 14 × 60s = 14 分钟
  - 跟 PR1 一样接受 (业务路演 1.5h 能等)
  - 后续 PR1.5 优化性能时一并修

---

## 6. 前端热图渲染 (Canvas 2D)

### 6.1 几何

- 8 行 × 14 列 = 112 格子
- 每格 32 × 24 像素 (W × H), 8 像素 gap
- 总尺寸: 8 × 32 + 7 × 8 = 312 W, 14 × 24 + 13 × 8 = 440 H
- 行 label (left): "ownBasic" "pairBonus" ... (12 像素 monospace)
- 列 label (top): "M0" "M1" ... "M14" (10 像素 monospace)

### 6.2 颜色 (8 行 8 色业务分色)

| 行 | 字段 | 颜色 (跟 PR1 卡片配色一致) |
|---|---|---|
| 0 | ownBasic | #5AA4AE (天水碧) |
| 1 | pairBonus | #758A99 (墨灰) |
| 2 | teamBonus | #F0C239 (缃色) |
| 3 | savings | #C0EBD7 (青白) |
| 4 | leader | #5AA4AE 浅 (业务 highlight) |
| 5 | horizontal | #758A99 浅 |
| 6 | retail | #C0EBD7 浅 |
| 7 | total | #5AA4AE 深 (highlight) |

每格颜色: 基础色 × 透明度 (alpha 0.1 - 1.0 按金额 0-max 比例)
- alpha = min(1.0, value / row_max_value)
- 0 = alpha 0.1 (浅), max = alpha 1.0 (深)

### 6.3 Hover Tooltip (0 延迟, 客户端展示)

- 监听 canvas mousemove
- 计算鼠标 → 格子 (row, col)
- 显示 tooltip (绝对定位, 暗背景)
- 内容: `"<field>, M<month>, $<value>"`
- 0 调 GET, 0 延迟

### 6.4 Click 详情 (60s 一次, 业务接受)

- 监听 canvas click
- 调 GET `/api/scenarios/{id}/overview?month=<col>` (复用 PR1 端点)
- 显示 month detail modal/card (8 报酬 + 该月数据)
- 加载时显示 "loading 60s..."
- 完成后显示 8 报酬明细
- 业务接受 (跟 PR1 一样, 60s 1 次)

---

## 7. 数据流 (PR2 新增)

```
[User 改 4 组参数 + 提交]
    ↓
[JS: POST /api/scenarios (跟 PR1 一样)]
    ↓
[JS: GET /api/scenarios/{id}/overview/all?total_months=14] ← 新端点, 1 次
    ↓
[Server: 串行 14 月 compute_month_overview, ~14 分钟]
    ↓
[JS: 渲染 8 行 14 列 Canvas 热图, 业务分色]
    ↓
[User hover → 0 延迟 tooltip]
[User click → 调 GET /overview?month=N, 60s 详情]
```

---

## 8. 测试 (PR2 新增 e2e)

### 8.1 路由测试 (`test_scenario_routes.py`)

```python
def test_get_overview_all_14_months():
    """GET /api/scenarios/{id}/overview/all?total_months=14 返 14 月 × 8 字段"""
    # ... POST /api/scenarios, 然后 GET /overview/all?total_months=14
    # 校验: matrix.ownBasic 长度 15 (0-14), 14 月 string parse 后 > 0
```

### 8.2 Playwright e2e (`test_scenario_ui_e2e.py`)

```python
def test_scenario_page_shows_heatmap_after_submit():
    """提交后, 热图 section 渲染 8 行 14 列格子"""
    # ... 调 POST, GET /overview/all, 校验 canvas 渲染 112 格子
    # (注: 实际跑只校验 canvas 元素存在, 不跑 14 分钟 computation)
```

---

## 9. 风险 & 缓解

| 风险 | 缓解 |
|---|---|
| 后端 14 月 14 分钟太慢 | 业务接受 (跟 PR1 60s 一致), 后续 PR1.5 优化 |
| Canvas 112 格子渲染卡 | 8 行 × 14 列 = 112 矩形, < 5ms 渲染, 0 风险 |
| 业务分色 8 色太多, 视觉杂乱 | 跟 PR1 卡片配色一致, 用户已习惯, 0 风险 |
| Click 详情 60s 加载用户烦躁 | loading 提示 + 业务接受 (跟 PR1 一样) |
| 0-14 月金额范围 0-max 比例可视化不准 | 显示 tooltip 0 延迟, 用户可看具体金额 |

---

## 10. 验收 (Definition of Done)

- [ ] 后端新端点 `GET /api/scenarios/{id}/overview/all` 返回 14 月 × 8 字段
- [ ] 前端 scenario.html 提交后, 热图 section 渲染 8 行 14 列
- [ ] Canvas 业务分色 (8 行 8 色, 跟 PR1 卡片配色一致)
- [ ] Hover 0 延迟 tooltip (报酬名 + 月份 + 金额)
- [ ] Click 调 GET /overview?month=N, 60s 后显示该月详情
- [ ] 路由测试 1 个 pass (test_get_overview_all_14_months)
- [ ] Playwright e2e 1 个 pass (test_scenario_page_shows_heatmap_after_submit)
- [ ] AGENTS.md §6.6 状态记录
- [ ] PR1 5 任务 0 回归
- [ ] 全部 67+2+2=71 测试 pass (PR1+PR2+PR3 + P3 PR1 e2e + P3 PR2 e2e)

---

## 11. 后续 (PR3 拍板)

### P3 PR3 (2-3 天): 多 scenario 对比 + 导出 PNG/CSV
- POST 多个 scenario, 侧栏列表
- 同图对比 (多 scenario 折线)
- 导出 PNG (Canvas → blob → download)
- 导出 CSV (overview + state)
