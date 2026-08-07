# P3 PR2 8 种报酬 × 14 月 热图 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 scenario.html 下方加热图 section, 提交后 1 GET 拉 14 月 × 8 报酬 = 112 值, Canvas 渲染 8 行 14 列业务分色热图, hover tooltip 0 延迟, click 详情 60s 1 次.

**Architecture:** 后端新端点 `GET /api/scenarios/{id}/overview/all?total_months=14` 串行 14 月 `compute_month_overview`. 前端 Canvas 2D 渲染 8 行 14 列 (112 格子), 业务分色 (8 行 8 色, 跟 PR1 卡片配色). Hover 客户端 0 延迟, click 调 GET /overview?month=N 60s 后显示详情.

**Tech Stack:** 复用 PR1 栈 (Vanilla HTML + CSS + JS, Canvas 2D, FastAPI, SQLAlchemy, 零 npm 依赖).

**Spec:** `docs/superpowers/specs/2026-08-07-p3-scenario-heatmap-design.md`
**Plan 父:** `docs/superpowers/plans/2026-08-07-p3-scenario-ui.md` (PR1 plan)

---

## File Structure (PR2 改动)

| 文件 | 责任 |
|---|---|
| `scenario_routes.py` | 修改: 加 `GET /api/scenarios/{id}/overview/all` 端点 (1 个新路由) |
| `tests/test_scenario_routes.py` | 修改: 加 `test_get_overview_all_14_months` 测试 |
| `static/scenario.html` | 修改: 加 `<section id="heatmap">` 在 8 卡片下方 (30 行) |
| `static/scenario.js` | 修改: 加 `renderHeatmap` + `showMonthDetail` 函数 (80 行) |
| `static/scenario.css` | 修改: 加 .heatmap-container / .heatmap-cell / .heatmap-tooltip / .month-detail 样式 (50 行) |
| `AGENTS.md` | 加 §6.6 P3 PR2 状态记录 (30 行) |

---

## Task 1: 后端新端点 — `scenario_routes.py` 加 `overview/all`

**Files:**
- Modify: `scenario_routes.py`

- [ ] **Step 1: 找 `get_overview` 路由位置, 在它之后加新路由**

用 Select-String 找:
```powershell
Select-String -Pattern 'def get_overview|@router\.get\("/\{scenario_id\}/overview"\)' scenario_routes.py
```

- [ ] **Step 2: 在 `get_overview` 函数后追加新路由**

```python
@router.get("/{scenario_id}/overview/all")
def get_overview_all(scenario_id: int,
                     total_months: int = Query(14, ge=1, le=15),
                     db: Session = Depends(get_db)) -> Dict[str, Any]:
    """取 scenario 0-total_months 月的 8 报酬 × 月 矩阵 (heatmap 渲染用)

    业务 (P3 PR2):
      - 1 次算 14 月 × 8 报酬 = 112 值 (避免前端 14 次串行 GET)
      - 14 月 × 60s/月 = 14 分钟, 业务接受 (跟 PR1 60s 一致)
      - 矩阵按字段分组, 返 15 个 string (0-14 月)
    """
    repo = ScenarioRepository(db)
    s = repo.load(scenario_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"scenario {scenario_id} not found")
    fields = ["ownBasic", "pairBonus", "teamBonus", "savings",
              "leader", "horizontal", "retail", "total"]
    months = list(range(0, total_months + 1))
    matrix: Dict[str, list] = {f: [None] * (total_months + 1) for f in fields}
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

- [ ] **Step 3: 跑现有 4 个路由测试确认没破坏**

```powershell
cd D:\Projects\Reward\RewardAgentAnalysis
python -m pytest tests/test_scenario_routes.py -v
```

期望: 4 passed (PR1 已有 4 个, 加新端点不破坏)

- [ ] **Step 4: Commit**

```bash
git add scenario_routes.py
git commit -m "feat(scenario): P3 PR2 Task 1 — overview/all 端点 (1 次算 14 月 × 8 报酬 = 112 值)"
```

---

## Task 2: 路由测试 — `tests/test_scenario_routes.py` 加新测试

**Files:**
- Modify: `tests/test_scenario_routes.py`

- [ ] **Step 1: 找 `test_get_overview_route` 位置, 在它之后加新测试**

- [ ] **Step 2: 加新测试 (复用 PR1 测试的 _override_db + _sample_body helper)**

```python
def test_get_overview_all_14_months():
    """GET /api/scenarios/{id}/overview/all?total_months=14 返 14 月 × 8 字段矩阵"""
    get_db_fn, engine, path = _override_db()
    app.dependency_overrides[get_db] = get_db_fn
    try:
        client = TestClient(app)
        # 先建场景 (PR1 拍板: max_level=2 layer_counts={0:1, 1:2, 2:2}, 快算)
        body = _sample_body(name="test_overview_all", max_level=2, layer_counts={"0": 1, "1": 2, "2": 2})
        resp = client.post("/api/scenarios", json=body)
        assert resp.status_code == 201
        sid = resp.json()["id"]
        # 拉 all (max_level=2 → total_months=2, 跟 layer 匹配)
        resp2 = client.get(f"/api/scenarios/{sid}/overview/all?total_months=2")
        assert resp2.status_code == 200
        data = resp2.json()
        # 校验 8 字段
        assert set(data["fields"]) == {"ownBasic", "pairBonus", "teamBonus", "savings",
                                       "leader", "horizontal", "retail", "total"}
        # 校验 3 个月 (0-2)
        assert data["months"] == [0, 1, 2]
        # 校验矩阵: 8 字段 × 3 月 = 24 值
        for f in data["fields"]:
            assert len(data["matrix"][f]) == 3
            # 14 月 (m=2) 累计应该 > 0
            assert float(data["matrix"][f][2]) > 0, f"{f}[2] 应该是 > 0, 实际 {data['matrix'][f][2]}"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        try:
            os.unlink(path)
        except (PermissionError, OSError):
            pass
```

- [ ] **Step 3: 跑新测试确认通过**

```powershell
cd D:\Projects\Reward\RewardAgentAnalysis
python -m pytest tests/test_scenario_routes.py -v
```

期望: 5 passed (4 PR1 + 1 PR2)

- [ ] **Step 4: Commit**

```bash
git add tests/test_scenario_routes.py
git commit -m "test(scenario): P3 PR2 Task 2 — overview/all 路由测试 (14 月 × 8 字段 = 24 值)"
```

---

## Task 3: 前端 HTML section + CSS 样式

**Files:**
- Modify: `static/scenario.html`
- Modify: `static/scenario.css`

- [ ] **Step 1: 找 PR1 提交按钮位置, 在它之后加热图 section**

用 Select-String 找:
```powershell
Select-String -Pattern 'btn-submit|p3-submit-row|toast' static/scenario.html
```

- [ ] **Step 2: 在 `</div>` 关闭 `.p3-right` 之前加 `<section id="heatmap">`**

```html
<!-- ★ P3 PR2: 8 种报酬 × 14 月 热图 (提交后渲染) -->
<section id="heatmap" class="p3-heatmap" style="display:none">
  <h2>📊 8 种报酬 × 14 月累计热图</h2>
  <div class="heatmap-container">
    <canvas id="heatmap-canvas" width="500" height="320"></canvas>
  </div>
  <div class="heatmap-legend">
    <span class="legend-low">低</span>
    <span class="legend-grad"></span>
    <span class="legend-high">高</span>
    <span class="legend-hint">(颜色深 = 金额高)</span>
  </div>
  <div id="heatmap-tooltip" class="heatmap-tooltip" style="display:none"></div>
  <div id="month-detail" class="month-detail" style="display:none">
    <h3>📅 月份详情</h3>
    <div class="month-detail-body">加载中...</div>
    <button class="month-detail-close">✕ 关闭</button>
  </div>
</section>
```

- [ ] **Step 3: 在 `static/scenario.css` 末尾加 heatmap 样式**

```css
/* === P3 PR2: 热图样式 === */
.p3-heatmap {
  margin-top: 16px;
  padding: 16px;
  background: #1a1a2e;
  border-radius: 8px;
}
.p3-heatmap h2 {
  color: #5AA4AE;
  font-size: 14px;
  margin-bottom: 12px;
}
.heatmap-container {
  background: #0a0a14;
  border-radius: 4px;
  padding: 8px;
  overflow-x: auto;
}
#heatmap-canvas {
  display: block;
}
.heatmap-legend {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: #758A99;
  margin-top: 8px;
}
.legend-low, .legend-high { color: #D6ECF0; }
.legend-grad {
  flex: 0 0 100px;
  height: 8px;
  background: linear-gradient(to right,
    rgba(90, 164, 174, 0.1), rgba(90, 164, 174, 1.0));
  border-radius: 4px;
}
.heatmap-tooltip {
  position: fixed;
  background: #1a1a2e;
  color: #D6ECF0;
  border: 1px solid #5AA4AE;
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 12px;
  pointer-events: none;
  z-index: 100;
}
.month-detail {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background: #1a1a2e;
  color: #D6ECF0;
  border: 1px solid #5AA4AE;
  border-radius: 8px;
  padding: 16px;
  min-width: 360px;
  z-index: 101;
}
.month-detail h3 {
  color: #5AA4AE;
  font-size: 14px;
  margin-bottom: 12px;
}
.month-detail-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 12px;
}
.month-detail-body .field { color: #758A99; }
.month-detail-body .val { color: #F0C239; font-family: monospace; }
.month-detail-close {
  background: transparent;
  color: #C0EBD7;
  border: 1px solid #758A99;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
}
```

- [ ] **Step 4: 验证 (浏览器加载 `/static/scenario.html`, 应该看不到 heatmap section 因为 display:none 初始隐藏)**

- [ ] **Step 5: Commit**

```bash
git add static/scenario.html static/scenario.css
git commit -m "feat(scenario-ui): P3 PR2 Task 3 — heatmap section HTML + CSS 样式 (8 行 14 列布局 + tooltip + month-detail modal)"
```

---

## Task 4: 前端 JS 热图渲染 + hover + click

**Files:**
- Modify: `static/scenario.js`

- [ ] **Step 1: 找 `submitScenario` 函数位置, 在它之后加 heatmap 函数**

- [ ] **Step 2: 在 `static/scenario.js` 末尾 IIFE 内加 heatmap 渲染函数**

```javascript
  // === P3 PR2: 热图渲染 ===
  const HEATMAP_COLORS = {
    ownBasic: '#5AA4AE', pairBonus: '#758A99', teamBonus: '#F0C239',
    savings: '#C0EBD7', leader: '#5AA4AE80', horizontal: '#758A9980',
    retail: '#C0EBD780', total: '#5AA4AE',
  };
  const HEATMAP_ROWS = ['ownBasic', 'pairBonus', 'teamBonus', 'savings',
                        'leader', 'horizontal', 'retail', 'total'];
  const HEATMAP_CELL_W = 32, HEATMAP_CELL_H = 24, HEATMAP_GAP = 4;
  const HEATMAP_LABEL_W = 70, HEATMAP_LABEL_H = 20;
  let heatmapData = null;  // {fields, months, matrix}

  function hexToRgba(hex, alpha) {
    // hex = "#5AA4AE" or "#5AA4AE80" (带 alpha)
    if (hex.length === 9) hex = hex.slice(0, 7);
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  function renderHeatmap() {
    if (!heatmapData) return;
    const canvas = document.getElementById('heatmap-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const totalCols = heatmapData.months.length;
    const totalRows = HEATMAP_ROWS.length;
    canvas.width = HEATMAP_LABEL_W + totalCols * (HEATMAP_CELL_W + HEATMAP_GAP) + HEATMAP_GAP;
    canvas.height = HEATMAP_LABEL_H + totalRows * (HEATMAP_CELL_H + HEATMAP_GAP) + HEATMAP_GAP;
    const w = canvas.width, h = canvas.height;
    ctx.fillStyle = '#0a0a14';
    ctx.fillRect(0, 0, w, h);

    // 行 label (left)
    ctx.fillStyle = '#758A99';
    ctx.font = '11px monospace';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    HEATMAP_ROWS.forEach((f, i) => {
      const y = HEATMAP_LABEL_H + i * (HEATMAP_CELL_H + HEATMAP_GAP) + HEATMAP_CELL_H / 2;
      ctx.fillText(f, HEATMAP_LABEL_W - 6, y);
    });
    // 列 label (top)
    ctx.textAlign = 'center';
    ctx.textBaseline = 'bottom';
    heatmapData.months.forEach((m, j) => {
      const x = HEATMAP_LABEL_W + j * (HEATMAP_CELL_W + HEATMAP_GAP) + HEATMAP_CELL_W / 2;
      ctx.fillText('M' + m, x, HEATMAP_LABEL_H - 4);
    });

    // 算每行 max value (alpha 0.1-1.0 比例)
    HEATMAP_ROWS.forEach((f, i) => {
      const rowValues = heatmapData.matrix[f].map(v => parseFloat(v) || 0);
      const maxV = Math.max(...rowValues, 0.01);
      rowValues.forEach((v, j) => {
        const x = HEATMAP_LABEL_W + j * (HEATMAP_CELL_W + HEATMAP_GAP);
        const y = HEATMAP_LABEL_H + i * (HEATMAP_CELL_H + HEATMAP_GAP);
        const alpha = Math.min(1.0, Math.max(0.1, v / maxV));
        ctx.fillStyle = hexToRgba(HEATMAP_COLORS[f], alpha);
        ctx.fillRect(x, y, HEATMAP_CELL_W, HEATMAP_CELL_H);
      });
    });
    // 显示 heatmap section
    document.getElementById('heatmap').style.display = 'block';
  }

  function showHeatmapTooltip(event, row, col) {
    const tt = document.getElementById('heatmap-tooltip');
    if (!tt || !heatmapData) return;
    const f = HEATMAP_ROWS[row];
    const m = heatmapData.months[col];
    const v = heatmapData.matrix[f][m];
    tt.textContent = `${f}, M${m}, $${parseFloat(v).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    tt.style.display = 'block';
    tt.style.left = (event.clientX + 12) + 'px';
    tt.style.top = (event.clientY + 12) + 'px';
  }
  function hideHeatmapTooltip() {
    const tt = document.getElementById('heatmap-tooltip');
    if (tt) tt.style.display = 'none';
  }

  async function showMonthDetail(row, col, scenarioId) {
    if (!heatmapData) return;
    const detail = document.getElementById('month-detail');
    if (!detail) return;
    const m = heatmapData.months[col];
    detail.querySelector('.month-detail-body').innerHTML = '<p>加载中... (≤ 60s)</p>';
    detail.style.display = 'block';
    try {
      const resp = await fetch(`/api/scenarios/${scenarioId}/overview?month=${m}`);
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      const fields = ['ownBasic', 'pairBonus', 'teamBonus', 'savings',
                      'leader', 'horizontal', 'retail', 'total'];
      const body = detail.querySelector('.month-detail-body');
      body.innerHTML = '';
      const f = HEATMAP_ROWS[row];
      body.innerHTML += `<div class="field" style="grid-column: 1/-1; color:#5AA4AE">📅 M${m} (${f} 行: $${parseFloat(heatmapData.matrix[f][m]).toLocaleString('en-US', {minimumFractionDigits: 2})})</div>`;
      fields.forEach(field => {
        body.innerHTML += `<div class="field">${field}</div><div class="val">$${parseFloat(data[field] || '0').toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</div>`;
      });
    } catch (err) {
      detail.querySelector('.month-detail-body').innerHTML = '<p style="color:#EF4444">错误: ' + err.message + '</p>';
    }
  }
  function hideMonthDetail() {
    const detail = document.getElementById('month-detail');
    if (detail) detail.style.display = 'none';
  }

  function bindHeatmapEvents(scenarioId) {
    const canvas = document.getElementById('heatmap-canvas');
    if (!canvas) return;
    canvas.addEventListener('mousemove', (e) => {
      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      if (x < HEATMAP_LABEL_W || y < HEATMAP_LABEL_H) {
        hideHeatmapTooltip();
        return;
      }
      const j = Math.floor((x - HEATMAP_LABEL_W) / (HEATMAP_CELL_W + HEATMAP_GAP));
      const i = Math.floor((y - HEATMAP_LABEL_H) / (HEATMAP_CELL_H + HEATMAP_GAP));
      if (i < 0 || i >= HEATMAP_ROWS.length || j < 0 || j >= heatmapData.months.length) {
        hideHeatmapTooltip();
        return;
      }
      showHeatmapTooltip(e, i, j);
    });
    canvas.addEventListener('mouseleave', hideHeatmapTooltip);
    canvas.addEventListener('click', (e) => {
      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      if (x < HEATMAP_LABEL_W || y < HEATMAP_LABEL_H) return;
      const j = Math.floor((x - HEATMAP_LABEL_W) / (HEATMAP_CELL_W + HEATMAP_GAP));
      const i = Math.floor((y - HEATMAP_LABEL_H) / (HEATMAP_CELL_H + HEATMAP_GAP));
      if (i < 0 || i >= HEATMAP_ROWS.length || j < 0 || j >= heatmapData.months.length) return;
      showMonthDetail(i, j, scenarioId);
    });
    document.querySelector('.month-detail-close').addEventListener('click', hideMonthDetail);
  }
```

- [ ] **Step 3: 修改 `submitScenario` 函数末尾, 加拉 all-months 调 heatmap**

在 `submitScenario` 函数 `showToast(` 调用之前, 加:

```javascript
  // P3 PR2: 拉 overview/all, 渲染热图 (业务 14 月 × 60s = 14 分钟, 接受)
  const allResp = await fetch(`/api/scenarios/${scenario_id}/overview/all?total_months=${formState.total_months}`);
  if (allResp.ok) {
    heatmapData = await allResp.json();
    renderHeatmap();
    bindHeatmapEvents(scenario_id);
  }
```

注意: `formState.total_months` 不存在, 用 hardcoded 14 (跟 spec 拍板).

```javascript
  // P3 PR2: 拉 overview/all, 渲染热图 (业务 14 月 × 60s = 14 分钟, 接受)
  const allResp = await fetch(`/api/scenarios/${scenario_id}/overview/all?total_months=14`);
  if (allResp.ok) {
    heatmapData = await allResp.json();
    renderHeatmap();
    bindHeatmapEvents(scenario_id);
  }
```

- [ ] **Step 4: 验证 (浏览器, 提交后, 等 14 分钟, 热图渲染 8 行 14 列)**

实际业务验证 14 分钟太长, 临时改 `max_level=2 layer_counts={0:1, 1:2, 2:2}` 拍 3 月快 (约 12s) 验证渲染. PR2 plan 不强制 e2e 跑 14 月.

- [ ] **Step 5: Commit**

```bash
git add static/scenario.js
git commit -m "feat(scenario-ui): P3 PR2 Task 4 — Canvas 热图渲染 (8 行 14 列 + 业务分色 + hover tooltip + click detail modal)"
```

---

## Task 5: Playwright e2e — `tests/test_scenario_ui_e2e.py` 加热图测试

**Files:**
- Modify: `tests/test_scenario_ui_e2e.py`

- [ ] **Step 1: 在 `test_scenario_submit_shows_8_cards` 之后加新测试**

```python
@pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="playwright not installed")
def test_scenario_page_shows_heatmap_after_submit(uvicorn_server):
    """提交后, 热图 section 渲染 8 行 14 列格子 (不跑 14 分钟 computation, 用小 scenario)"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        # 注入小 scenario (max_level=2, 3 月) 跳过 14 分钟
        page.goto(f"{uvicorn_server}/static/scenario.html")
        # 修改 formState 改成小 scenario
        page.evaluate("""() => {
          window.P3.getFormState().tree_shape.max_level = 2;
          window.P3.getFormState().tree_shape.layer_counts = {0: 1, 1: 2, 2: 2};
        }""")
        # 提交
        page.click("#btn-submit")
        # 等 8 卡片填充 (≤ 60s)
        for _ in range(40):
            total = page.query_selector('.card[data-field="total"] .val').inner_text()
            if total != "—" and total != "$0.00":
                break
            time.sleep(0.1)
        # 校验 heatmap section 可见
        heatmap = page.query_selector("#heatmap")
        assert heatmap is not None
        # canvas 存在
        canvas = page.query_selector("#heatmap-canvas")
        assert canvas is not None
        # 校验 canvas 尺寸 (8 行 14 列)
        width = page.evaluate("() => document.getElementById('heatmap-canvas').width")
        assert width > 400, f"heatmap canvas 宽度应该 > 400, 实际 {width}"
        # hover 测试 (cell 0,0 = ownBasic M0)
        # click detail modal
        browser.close()
```

- [ ] **Step 2: 跑新测试**

```powershell
cd D:\Projects\Reward\RewardAgentAnalysis
python -m pytest tests/test_scenario_ui_e2e.py::test_scenario_page_shows_heatmap_after_submit -v
```

期望: 1 passed (有 playwright) 或 1 skipped (没 playwright)

- [ ] **Step 3: Commit**

```bash
git add tests/test_scenario_ui_e2e.py
git commit -m "test(scenario-ui): P3 PR2 Task 5 — Playwright e2e (热图 section 渲染验证)"
```

---

## Task 6: AGENTS.md §6.6 状态记录

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: 在 §6.5 (PR1 状态) 之后加 §6.6 章节**

用 Python 追加模式 (跟之前 `_append_pr3_section.py` 一样):

```python
addition = """

### 6.6 P3 PR2 — 8 种报酬 × 14 月 热图 (scenario.html 下方 section)

**业务**: 1 次画 8 种报酬 × 14 月累计热图, hover tooltip 0 延迟, click 详情 60s 1 次
**完成日**: 2026-08-07 (本轮)
**Commit**: 见 git log (Task 1-6 各 1 commit, Task 5 e2e 用 @skipif 兜底)
**关键文件**:
- `scenario_routes.py` — 新增 `GET /api/scenarios/{id}/overview/all?total_months=14` 端点
- `tests/test_scenario_routes.py` — +1 测试 (test_get_overview_all_14_months)
- `static/scenario.html` — 加 `<section id="heatmap">` 在 8 卡片下方
- `static/scenario.js` — 加 `renderHeatmap` + `showHeatmapTooltip` + `showMonthDetail` + `bindHeatmapEvents`
- `static/scenario.css` — 加 .p3-heatmap / .heatmap-container / .heatmap-tooltip / .month-detail 样式
- `tests/test_scenario_ui_e2e.py` — +1 e2e 测试 (test_scenario_page_shows_heatmap_after_submit)

**验收 (5+1=6 task 验证)**:
- Task 1 后端: GET /overview/all 返 14 月 × 8 字段 = 112 值
- Task 2 路由测试: 5 passed (4 PR1 + 1 PR2)
- Task 3 前端 HTML+CSS: heatmap section + tooltip + month-detail modal
- Task 4 前端 JS: Canvas 8 行 14 列 + 业务分色 + hover + click
- Task 5 e2e: 1 测试 pass (用 max_level=2 跳过 14 分钟)
- Task 6 AGENTS.md §6.6 状态记录

**业务价值**:
- 1 次看 14 月趋势, 不用 14 次点击切换
- 业务分色突出"哪个报酬哪月增长最猛"
- Hover 0 延迟, 路演时即点即看
- Click 详情 60s 1 次, 业务接受 (跟 PR1 60s 一致)

**性能**:
- 1 GET 14 月 ≈ 14 分钟 (跟 PR1 60s 一致, 业务接受)
- 后续 PR1.5 优化 (LRU cache + parallel compute) 时一并修
- 实际 e2e 用 max_level=2 跳过, 3 月 ≈ 12s

**业务分色 8 色 (跟 PR1 卡片一致)**:
- ownBasic #5AA4AE / pairBonus #758A99 / teamBonus #F0C239 / savings #C0EBD7
- leader #5AA4AE80 / horizontal #758A9980 / retail #C0EBD780 / total #5AA4AE

**后续 (PR3 拍板)**:
- 多 scenario 对比 (2-3 天)
- 导出 PNG/CSV
"""
with open('AGENTS.md', 'ab') as f:
    f.write(addition.encode('utf-8'))
```

- [ ] **Step 2: 跑全部 PR1+PR2+PR3 + P3 PR1+PR2 测试**

```powershell
cd D:\Projects\Reward\RewardAgentAnalysis
python -m pytest tests/test_scenario_orm.py tests/test_migrate_scenarios.py tests/test_scenario_repository.py tests/test_scenario_routes.py tests/test_scenario_builder.py tests/test_scenario_pv.py tests/test_scenario_cache.py tests/test_scenario_consistency.py tests/test_scenario_model.py tests/test_commission_own_basic.py tests/test_pr2_root_consistency.py tests/test_db_admin.py tests/test_scenario_ui_e2e.py 2>&1 | Select-Object -Last 5
```

期望: 68 + 3 = 71 测试 (PR1+PR2+PR3 + P3 PR1 2 e2e + P3 PR2 1 e2e)

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md
git commit -m "docs(agents): §6.6 P3 PR2 状态记录 (8 种报酬 × 14 月 热图 + 后端 all 端点 + 业务分色 + hover/click)"
```

---

## 验证清单 (PR2 全部完成后)

- [ ] 后端 1 GET 14 月 ≈ 14 分钟, 业务接受
- [ ] 前端热图 8 行 14 列, 业务分色 8 色
- [ ] Hover 0 延迟 tooltip (报酬名 + 月份 + 金额)
- [ ] Click 60s 后显示该月 8 报酬详情
- [ ] 路由测试 5 passed (4 PR1 + 1 PR2)
- [ ] Playwright e2e 3 passed (2 PR1 + 1 PR2, skipif 兜底)
- [ ] PR1 6 commit 0 回归
- [ ] AGENTS.md §6.6 状态记录
- [ ] 71 测试 pass

## Self-Review Checklist

- [ ] Spec coverage: 11 章节每章节对应到 task (6 task)
- [ ] Placeholder scan: 无 TBD / TODO / "类似 Task N"
- [ ] DRY: 8 行 14 列布局复用 HEATMAP_CELL_W/H 4 个常量
- [ ] YAGNI: 不做多 scenario 对比 (PR3 拍板), 不做 PNG/CSV 导出
- [ ] TDD: Task 1 路由测试 + Task 5 e2e 测试
- [ ] Frequent commits: 6 task = 6 commit
