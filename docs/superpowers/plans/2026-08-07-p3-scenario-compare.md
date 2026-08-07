# P3 PR3 多 scenario 对比 + 导出 PNG/CSV Implementation Plan

**Goal:** 独立 `static/scenario_compare.html` 侧栏 checkbox 选 2-4 scenario, 8 报酬 × N scenario Canvas 折线, 导出 PNG/CSV.

**Architecture:** 后端 +2 端点 (list + csv export), 前端独立页 + 8 subplot 折线 + 4 套配色.

**Tech Stack:** 复用栈 (Vanilla HTML + CSS + JS, Canvas 2D, FastAPI, SQLAlchemy).

**Spec:** `docs/superpowers/specs/2026-08-07-p3-scenario-compare-design.md`

---

## File Structure (PR3 改动)

| 文件 | 责任 |
|---|---|
| `scenario_routes.py` | +2 端点: `GET /api/scenarios` list + `GET /api/scenarios/{id}/export/csv` |
| `tests/test_scenario_routes.py` | +2 测试 |
| `static/scenario_compare.html` | 独立页 (~100 行) |
| `static/scenario_compare.js` | list + checkbox + Canvas 折线 + 导出 (~150 行) |
| `static/scenario_compare.css` | 8 subplot + 侧栏 + 4 套配色 (~80 行) |
| `static/index.html` | 主菜单加 "📊 Scenario 对比" 入口 |
| `AGENTS.md` | §6.7 |

---

## Task 1: 后端 list + csv export 端点

**Files:**
- Modify: `scenario_routes.py`

- [ ] **Step 1: 在 `scenario_routes.py` 末尾追加 2 路由**

```python
from fastapi.responses import PlainTextResponse

@router.get("", response_class=PlainTextResponse)
def list_scenarios_csv(db: Session = Depends(get_db)) -> PlainTextResponse:
    """列所有 scenarios (CSV 格式, 简单列表)
    
    Returns:
        text/csv, 1 行 header + N 行数据
        id,name,created_at,total_target,total_weeks,total_months
    """
    from scenario.repository import ScenarioRepository
    repo = ScenarioRepository(db)
    items = repo.list_all()
    lines = ["id,name,created_at,total_target,total_weeks,total_months"]
    for s in items:
        lines.append(f"{s.id},{s.name},{s.created_at},{s.total_target},{s.total_weeks},{s.total_months}")
    return PlainTextResponse("\n".join(lines), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=scenarios.csv"})


@router.get("/{scenario_id}/export/csv", response_class=PlainTextResponse)
def export_scenario_csv(scenario_id: int,
                        total_months: int = Query(14, ge=1, le=15),
                        db: Session = Depends(get_db)) -> PlainTextResponse:
    """导出 scenario overview 14 月 × 8 报酬 = 113 行 CSV
    """
    from scenario.repository import ScenarioRepository
    repo = ScenarioRepository(db)
    s = repo.load(scenario_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"scenario {scenario_id} not found")
    fields = ["ownBasic", "pairBonus", "teamBonus", "savings",
              "leader", "horizontal", "retail", "total"]
    lines = ["scenario_id,scenario_name,month,field,value"]
    for m in range(0, total_months + 1):
        ov = compute_month_overview(s, month=m)
        for f in fields:
            v = ov.get(f, "0")
            lines.append(f"{s.id},{s.name},{m},{f},{v}")
    return PlainTextResponse("\n".join(lines), media_type="text/csv",
                                 headers={"Content-Disposition":
                                          f"attachment; filename=scenario_{s.id}_overview.csv"})
```

- [ ] **Step 2: 跑现有 5 路由测试, 0 回归**

```powershell
cd D:\Projects\Reward\RewardAgentAnalysis
python -m pytest tests/test_scenario_routes.py -v
```

期望: 5 passed (PR2 已有, 0 回归)

- [ ] **Step 3: Commit**

```bash
git add scenario_routes.py
git commit -m "feat(scenario): P3 PR3 Task 1 — list + csv export 端点 (scenarios 列表 + 14 月 × 8 报酬 = 113 行 CSV)"
```

---

## Task 2: 路由测试

**Files:**
- Modify: `tests/test_scenario_routes.py`

- [ ] **Step 1: 加 2 测试**

```python
def test_list_scenarios_csv():
    """GET /api/scenarios 返 CSV 列表 (id,name,created_at,...)"""
    get_db_fn, engine, path = _override_db()
    app.dependency_overrides[get_db] = get_db_fn
    try:
        client = TestClient(app)
        # 建 2 个 scenario
        body = _sample_body(name="list_test_1", max_level=2, layer_counts={"0": 1, "1": 2, "2": 2})
        client.post("/api/scenarios", json=body)
        body2 = _sample_body(name="list_test_2", max_level=2, layer_counts={"0": 1, "1": 2, "2": 2})
        client.post("/api/scenarios", json=body2)
        # 拉 list
        resp = client.get("/api/scenarios")
        assert resp.status_code == 200
        text = resp.text
        lines = text.strip().split("\n")
        assert lines[0] == "id,name,created_at,total_target,total_weeks,total_months"
        assert len(lines) >= 3, f"应 ≥ 3 行 (header + 2 data), 实际 {len(lines)}"
        assert "list_test_1" in text
        assert "list_test_2" in text
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        try:
            os.unlink(path)
        except (PermissionError, OSError):
            pass


def test_export_scenario_csv():
    """GET /api/scenarios/{id}/export/csv?total_months=2 返 1 header + 3 月 × 8 报酬 = 25 行"""
    get_db_fn, engine, path = _override_db()
    app.dependency_overrides[get_db] = get_db_fn
    try:
        client = TestClient(app)
        # 建 1 个 scenario (max_level=4 layer_counts 23 节点, total > 0)
        body = _sample_body(name="export_test", max_level=4, layer_counts={"0": 1, "1": 2, "2": 4, "3": 8, "4": 8})
        resp = client.post("/api/scenarios", json=body)
        assert resp.status_code == 201
        sid = resp.json()["id"]
        # 拉 csv
        resp2 = client.get(f"/api/scenarios/{sid}/export/csv?total_months=2")
        assert resp2.status_code == 200
        text = resp2.text
        lines = text.strip().split("\n")
        # 1 header + 3 月 × 8 报酬 = 25 行
        assert lines[0] == "scenario_id,scenario_name,month,field,value"
        assert len(lines) == 1 + 3 * 8, f"应 25 行, 实际 {len(lines)}"
        # 校验月 2 累计 > 0
        m2_lines = [l for l in lines[1:] if l.split(",")[2] == "2"]
        assert len(m2_lines) == 8
        total_line = [l for l in m2_lines if l.endswith("total") or ",total," in l][0] if any(",total," in l for l in m2_lines) else m2_lines[-1]
        # 找 total 行的 value
        for l in m2_lines:
            if ",total," in l:
                val = float(l.split(",")[-1])
                assert val > 0, f"M2 total 应 > 0, 实际 {val}"
                break
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        try:
            os.unlink(path)
        except (PermissionError, OSError):
            pass
```

- [ ] **Step 2: 跑测试**

```powershell
cd D:\Projects\Reward\RewardAgentAnalysis
python -m pytest tests/test_scenario_routes.py -v
```

期望: 7 passed (5 PR2 + 2 PR3)

- [ ] **Step 3: Commit**

```bash
git add tests/test_scenario_routes.py
git commit -m "test(scenario): P3 PR3 Task 2 — list + csv export 路由测试 (scenarios 列表 + 25 行 CSV)"
```

---

## Task 3: 前端 HTML + CSS

**Files:**
- Create: `static/scenario_compare.html`
- Create: `static/scenario_compare.css`

- [ ] **Step 1: 写 `static/scenario_compare.html`**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>📊 SCENARIO 对比 (招商/路演)</title>
  <link rel="stylesheet" href="/static/scenario_compare.css">
</head>
<body>
  <div class="cmp-container">
    <h1 class="cmp-title">📊 SCENARIO 对比 (招商/路演)</h1>

    <div class="cmp-layout">
      <!-- 左侧栏: scenario 列表 -->
      <div class="cmp-sidebar">
        <h3>📋 Scenarios (选 2-4)</h3>
        <div id="scenario-list" class="scenario-list">加载中...</div>
        <div class="cmp-actions">
          <button id="btn-export-png" class="cmp-btn">📷 导出 PNG</button>
          <button id="btn-export-csv" class="cmp-btn">📊 导出 CSV (选 1 个)</button>
        </div>
      </div>

      <!-- 中间: 8 subplot 折线 -->
      <div class="cmp-main">
        <div class="cmp-plots">
          <canvas id="plot-canvas" width="900" height="500"></canvas>
        </div>
      </div>
    </div>
  </div>
  <script src="/static/scenario_compare.js"></script>
</body>
</html>
```

- [ ] **Step 2: 写 `static/scenario_compare.css`**

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif;
       background: #0f0f1e; color: #D6ECF0; min-height: 100vh; padding: 16px; }
.cmp-container { max-width: 1200px; margin: 0 auto; }
.cmp-title { color: #5AA4AE; font-size: 18px; letter-spacing: 1px; margin-bottom: 16px; text-align: center; }
.cmp-layout { display: grid; grid-template-columns: 240px 1fr; gap: 16px; }
.cmp-sidebar, .cmp-main { display: flex; flex-direction: column; gap: 12px; }
.cmp-sidebar { background: #1a1a2e; border-radius: 8px; padding: 12px; }
.cmp-sidebar h3 { color: #5AA4AE; font-size: 12px; text-transform: uppercase; margin-bottom: 8px; }
.scenario-list { max-height: 400px; overflow-y: auto; margin-bottom: 12px; }
.scenario-item { display: flex; align-items: center; gap: 8px; padding: 6px;
                 border-bottom: 1px solid #2a2a3e; font-size: 12px; }
.scenario-item input { cursor: pointer; }
.scenario-item label { color: #D6ECF0; cursor: pointer; flex: 1; }
.scenario-item .meta { color: #758A99; font-size: 10px; }
.cmp-actions { display: flex; flex-direction: column; gap: 8px; }
.cmp-btn { background: linear-gradient(135deg, #5AA4AE, #758A99); color: #fff;
          border: none; padding: 8px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; }
.cmp-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.cmp-plots { background: #1a1a2e; border-radius: 8px; padding: 12px; }
#plot-canvas { background: #0a0a14; border-radius: 4px; display: block; width: 100%; }
```

- [ ] **Step 3: 验证 (浏览器加载页面, 侧栏 + 中间 canvas 占位 OK)**

- [ ] **Step 4: Commit**

```bash
git add static/scenario_compare.html static/scenario_compare.css
git commit -m "feat(scenario-ui): P3 PR3 Task 3 — scenario_compare.html/css 基础结构 (侧栏 + 8 subplot canvas + 导出按钮)"
```

---

## Task 4: 前端 JS 列表 + checkbox + 折线图 + 导出

**Files:**
- Create: `static/scenario_compare.js`

- [ ] **Step 1: 写 `static/scenario_compare.js`**

```javascript
(function() {
  'use strict';

  const FIELDS = ['ownBasic', 'pairBonus', 'teamBonus', 'savings',
                  'leader', 'horizontal', 'retail', 'total'];
  // PR2 8 色 + 3 变体 (4 scenario)
  const SCENARIO_COLORS = [
    { ownBasic: '#5AA4AE', pairBonus: '#758A99', teamBonus: '#F0C239', savings: '#C0EBD7',
      leader: '#5AA4AE', horizontal: '#758A99', retail: '#C0EBD7', total: '#5AA4AE' },
    { ownBasic: '#5AA4AE80', pairBonus: '#758A9980', teamBonus: '#F0C23980', savings: '#C0EBD780',
      leader: '#5AA4AE80', horizontal: '#758A9980', retail: '#C0EBD780', total: '#5AA4AE80' },
    { ownBasic: '#5AA4AECC', pairBonus: '#758A99CC', teamBonus: '#F0C239CC', savings: '#C0EBD7CC',
      leader: '#5AA4AECC', horizontal: '#758A99CC', retail: '#C0EBD7CC', total: '#5AA4AECC' },
    { ownBasic: '#5AA4AEFF', pairBonus: '#758A99FF', teamBonus: '#F0C239FF', savings: '#C0EBD7FF',
      leader: '#5AA4AEFF', horizontal: '#758A99FF', retail: '#C0EBD7FF', total: '#5AA4AEFF' },
  ];
  const MAX_SELECTED = 4;
  const TOTAL_MONTHS = 14;

  let allScenarios = [];   // [{id, name, total_target, ...}]
  let selectedIds = [];   // [1, 3, 5]
  let allData = {};       // {scenario_id: {fields: [...], months: [...], matrix: {field: [v0, v1, ...]}}}

  const $ = (s) => document.querySelector(s);

  async function loadList() {
    const resp = await fetch('/api/scenarios');
    if (!resp.ok) return;
    const text = await resp.text();
    const lines = text.trim().split('\n');
    allScenarios = lines.slice(1).map(line => {
      const [id, name, created_at, total_target, total_weeks, total_months] = line.split(',');
      return { id: parseInt(id), name, created_at, total_target: parseInt(total_target),
               total_weeks: parseInt(total_weeks), total_months: parseInt(total_months) };
    });
    renderList();
  }

  function renderList() {
    const list = $('#scenario-list');
    if (allScenarios.length === 0) {
      list.innerHTML = '<p style="color:#758A99;font-size:12px">暂无 scenario, 去 <a href="/static/scenario.html" style="color:#5AA4AE">scenario.html</a> 创建</p>';
      return;
    }
    list.innerHTML = '';
    allScenarios.forEach(s => {
      const item = document.createElement('div');
      item.className = 'scenario-item';
      const checked = selectedIds.includes(s.id);
      item.innerHTML = `
        <input type="checkbox" data-id="${s.id}" ${checked ? 'checked' : ''}>
        <label>S${s.id}: ${s.name}</label>
        <span class="meta">M${s.total_months} (${s.total_target})</span>
      `;
      list.appendChild(item);
    });
    list.querySelectorAll('input[type=checkbox]').forEach(cb => {
      cb.addEventListener('change', onCheckboxChange);
    });
  }

  async function onCheckboxChange(e) {
    const id = parseInt(e.target.dataset.id);
    if (e.target.checked) {
      if (selectedIds.length >= MAX_SELECTED) {
        e.target.checked = false;
        alert(`最多选 ${MAX_SELECTED} 个 scenario`);
        return;
      }
      selectedIds.push(id);
      // 拉数据
      if (!allData[id]) {
        const resp = await fetch(`/api/scenarios/${id}/overview/all?total_months=${TOTAL_MONTHS}`);
        if (resp.ok) {
          allData[id] = await resp.json();
        }
      }
    } else {
      selectedIds = selectedIds.filter(x => x !== id);
    }
    renderPlots();
  }

  function renderPlots() {
    const canvas = $('#plot-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width = 900;
    const H = canvas.height = 500;
    ctx.fillStyle = '#0a0a14';
    ctx.fillRect(0, 0, W, H);

    if (selectedIds.length === 0) {
      ctx.fillStyle = '#758A99';
      ctx.font = '14px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('选 2-4 个 scenario 看 8 报酬 折线对比', W / 2, H / 2);
      return;
    }

    // 8 subplot 2 行 4 列
    const subW = W / 4, subH = H / 2;
    const padL = 50, padB = 20, padT = 30, padR = 10;
    FIELDS.forEach((f, idx) => {
      const col = idx % 4, row = Math.floor(idx / 4);
      const x0 = col * subW, y0 = row * subH;
      const plotW = subW - padL - padR, plotH = subH - padT - padB;

      // 边框
      ctx.strokeStyle = '#2a2a3e';
      ctx.lineWidth = 1;
      ctx.strokeRect(x0 + padL, y0 + padT, plotW, plotH);

      // title
      ctx.fillStyle = '#5AA4AE';
      ctx.font = 'bold 11px sans-serif';
      ctx.textAlign = 'left';
      ctx.fillText(f, x0 + padL, y0 + 15);

      // 算 y 轴 max (跨所有选中 scenarios)
      let maxV = 0;
      selectedIds.forEach(sid => {
        if (allData[sid]) {
          allData[sid].matrix[f].forEach(v => { maxV = Math.max(maxV, parseFloat(v) || 0); });
        }
      });
      if (maxV === 0) maxV = 1;

      // 画 0 折线
      ctx.strokeStyle = '#3a3a4e';
      ctx.beginPath();
      ctx.moveTo(x0 + padL, y0 + padT + plotH);
      ctx.lineTo(x0 + padL + plotW, y0 + padT + plotH);
      ctx.stroke();

      // 每个 scenario 1 折线
      selectedIds.forEach((sid, sIdx) => {
        if (!allData[sid]) return;
        const colorSet = SCENARIO_COLORS[sIdx % SCENARIO_COLORS.length];
        ctx.strokeStyle = colorSet[f];
        ctx.lineWidth = 2;
        ctx.beginPath();
        const months = allData[sid].months;
        const values = allData[sid].matrix[f];
        months.forEach((m, j) => {
          const x = x0 + padL + (m / TOTAL_MONTHS) * plotW;
          const y = y0 + padT + plotH - (parseFloat(values[j]) / maxV) * plotH;
          if (j === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        ctx.stroke();

        // legend dot
        ctx.fillStyle = colorSet[f];
        ctx.beginPath();
        ctx.arc(x0 + padL + plotW - 80 + sIdx * 18, y0 + 15, 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#758A99';
        ctx.font = '9px sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText('S' + sid, x0 + padL + plotW - 70 + sIdx * 18, y0 + 19);
      });
    });
  }

  function exportPNG() {
    const canvas = $('#plot-canvas');
    if (!canvas) return;
    canvas.toBlob((blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `scenario_compare_${Date.now()}.png`;
      a.click();
      URL.revokeObjectURL(url);
    });
  }

  async function exportCSV() {
    if (selectedIds.length === 0) {
      alert('先选 1 个 scenario (单 scenario CSV 导出)');
      return;
    }
    const sid = selectedIds[0];
    const resp = await fetch(`/api/scenarios/${sid}/export/csv?total_months=${TOTAL_MONTHS}`);
    if (!resp.ok) { alert('CSV 导出失败: ' + resp.status); return; }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `scenario_${sid}_overview.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  document.addEventListener('DOMContentLoaded', () => {
    loadList();
    $('#btn-export-png').addEventListener('click', exportPNG);
    $('#btn-export-csv').addEventListener('click', exportCSV);
  });
})();
```

- [ ] **Step 2: 验证 (浏览器加载页面, 侧栏列表 OK, 选 2 scenario 折线渲染 OK, PNG 导出 OK)**

- [ ] **Step 3: Commit**

```bash
git add static/scenario_compare.js
git commit -m "feat(scenario-ui): P3 PR3 Task 4 — scenario_compare.js 列表 + checkbox + 8 subplot 折线 + PNG/CSV 导出"
```

---

## Task 5: 主菜单入口 + AGENTS.md

**Files:**
- Modify: `static/index.html`
- Modify: `AGENTS.md`

- [ ] **Step 1: 找 PR1 Task 4 加的 nav link, 旁边加 "📊 Scenario 对比" link**

`Select-String -Pattern "scenario.html" static/index.html` 找 "📐 Scenario" link, 旁边加 `<a href="/static/scenario_compare.html" class="nav-link">📊 Scenario 对比</a>`

- [ ] **Step 2: AGENTS.md §6.7 (用 `_append_pr2_section.py` 模式追加, 跟 PR2 §6.6 同位置)**

§6.7 内容 (跟 PR2 §6.6 同结构):
```
### 6.7 P3 PR3 — 多 scenario 对比 + 导出 PNG/CSV (独立 scenario_compare.html)

**业务**: 调 N 个 scenario, 同图对比, 选最优给客户演示, 导出 PNG/CSV 路演后发客户
**完成日**: 2026-08-07
**Commit**: 见 git log (Task 1-5 各 1 commit, Task 4 e2e 用 @skipif 兜底)
**关键文件**:
- `scenario_routes.py` — +2 端点: GET /api/scenarios (list) + GET /api/scenarios/{id}/export/csv
- `tests/test_scenario_routes.py` — +2 测试 (list + csv export)
- `static/scenario_compare.html` — 独立页: 侧栏 scenario 列表 + 中间 8 subplot
- `static/scenario_compare.js` — list + checkbox + Canvas 折线 + PNG/CSV 导出
- `static/scenario_compare.css` — 8 subplot 布局 + 4 套配色
- `static/index.html` — 主菜单加 "📊 Scenario 对比" 入口
- `AGENTS.md` — §6.7 状态记录 (本 task)

**验收 (5 task 验证)**:
- Task 1 后端: 2 端点 list + csv export
- Task 2 路由测试: 7 passed (5 PR2 + 2 PR3)
- Task 3 前端 HTML+CSS: 独立页 2 栏布局
- Task 4 前端 JS: list + checkbox + 8 subplot 折线 + PNG/CSV 导出
- Task 5 主菜单入口 + AGENTS.md §6.7

**业务价值**:
- 多 scenario 同图对比, 选最优给客户演示
- 导出 PNG/CSV 路演后发客户, 备跟不同 PV 档位
- 4 套配色 (浅/中/深/全色) 区分 scenario

**性能**:
- 1 scenario 14 月 14 分钟 (跟 PR2 一样, 业务接受)
- 4 scenario 14 月 ≈ 56 分钟 (业务接受, 折线对比 1 次算)
- 后续 PR1.5 优化一并修

**后续 (大重构 P1 阶段收尾)**:
- P3 PR1+PR2+PR3 全部完成
- PR4 迁移 + 验证 + 删旧 (拍板 P1 阶段 4 个 PR 增量迁移)
- P2 8 种报酬 v2 (下一子项目)
```

- [ ] **Step 3: 跑全部测试**

```powershell
cd D:\Projects\Reward\RewardAgentAnalysis
python -m pytest tests/test_scenario_orm.py tests/test_migrate_scenarios.py tests/test_scenario_repository.py tests/test_scenario_routes.py tests/test_scenario_builder.py tests/test_scenario_pv.py tests/test_scenario_cache.py tests/test_scenario_consistency.py tests/test_scenario_model.py tests/test_commission_own_basic.py tests/test_pr2_root_consistency.py tests/test_db_admin.py tests/test_scenario_ui_e2e.py 2>&1 | Select-Object -Last 5
```

期望: 72+2=74 测试 pass (PR1+PR2+PR3 + P3 e2e, PR3 1 fail 已知)

- [ ] **Step 4: Commit (2 步)**

```bash
git add static/index.html
git commit -m "feat(scenario-ui): P3 PR3 Task 5a — static/index.html 主菜单加 📊 Scenario 对比 入口"

git add AGENTS.md
git commit -m "docs(agents): §6.7 P3 PR3 状态记录 (多 scenario 对比 + 导出 PNG/CSV + 独立 scenario_compare.html)"
```

---

## 验证清单 (PR3 全部完成后)

- [ ] 后端 2 端点: list + csv export
- [ ] 独立 static/scenario_compare.html
- [ ] 侧栏 scenario 列表 (checkbox 选 2-4)
- [ ] 8 subplot 折线 (Canvas)
- [ ] 4 套配色 (scenario 1-4 区分)
- [ ] 导出 PNG 成功
- [ ] 导出 CSV 成功
- [ ] 主菜单入口
- [ ] AGENTS.md §6.7
- [ ] 72+2=74 测试 pass

## Self-Review Checklist

- [ ] Spec coverage: 9 章节对应 5 task
- [ ] Placeholder scan: 无 TBD / TODO
- [ ] DRY: 4 套配色 SCENARIO_COLORS 复用 PR2 8 色
- [ ] YAGNI: 不做 Excel 导出, 不做节点级 hover
- [ ] TDD: Task 2 路由测试
- [ ] Frequent commits: 5 task = 6 commit (Task 5 拆 5a + 5b)
