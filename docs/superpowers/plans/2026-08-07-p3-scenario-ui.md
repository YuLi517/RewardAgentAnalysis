# P3 PR1 树形动态生长 UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 招商/路演客户调 4 组参数, 实时看 8 种报酬在 15 月累计 + Canvas 树形图. 调 `scenario_routes.py` 3 个已有路由, 0 后端改动.

**Architecture:** 独立 `static/scenario.html` 跟主运营 `static/index.html` 平级 (通过 `app.mount("/static")` 访问). 2 栏布局: 左 4 个 border-beam 表单 + 右 Canvas 树形 + 8 报酬卡片. 提交后刷新 (1 POST + 2 GET, ≤2s).

**Tech Stack:** Vanilla HTML + CSS + JS, Canvas 2D, Playwright (e2e test), 零 npm 依赖.

**Spec:** `docs/superpowers/specs/2026-08-07-p3-scenario-ui-design.md`

---

## File Structure

| 文件 | 责任 |
|---|---|
| `static/scenario.html` | 2 栏布局: 左 4 表单 + 右 Canvas 树形 + 8 卡片 |
| `static/scenario.js` | Canvas 树形渲染 + POST/GET 路由调用 + 卡片更新 |
| `static/scenario.css` | 科技感样式 (border-beam 纯 CSS, 暗背景, 多色 token) |
| `static/index.html` | 修改: 顶部 nav 加 `<a href="/static/scenario.html">📐 Scenario</a>` |
| `tests/test_scenario_ui_e2e.py` | Playwright e2e: 加载页 + 填表 + 提交 + 校验 |
| `AGENTS.md` | 加 §6.5 P3 PR1 状态记录 |

---

## Task 1: 静态骨架 — `static/scenario.html` + `static/scenario.css` (基础布局)

**Files:**
- Create: `static/scenario.html`
- Create: `static/scenario.css`

- [ ] **Step 1: 写 `static/scenario.html` 基础结构 (2 栏布局 + 4 表单占位 + Canvas 占位 + 8 卡片占位)**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>📐 SCENARIO 招商/路演实时计算器</title>
  <link rel="stylesheet" href="/static/scenario.css">
</head>
<body>
  <div class="p3-container">
    <h1 class="p3-title">📐 SCENARIO 招商/路演实时计算器</h1>

    <div class="p3-layout">
      <!-- LEFT: 4 个 border-beam 表单 -->
      <div class="p3-left">
        <div class="beam-wrap" data-section="tree">
          <div class="beam-content">
            <h3>🌳 TreeShape (树形)</h3>
            <div class="form-row"><span>fork_type</span><span class="val">binary</span></div>
            <div class="form-row"><span>max_level</span><span class="val">10</span></div>
            <div class="form-row"><span>total_target</span><span class="val">2144</span></div>
          </div>
        </div>
        <div class="beam-wrap" data-section="growth">
          <div class="beam-content">
            <h3>📈 Growth (增长)</h3>
            <div class="form-row"><span>per_region/week</span><span class="val">9</span></div>
            <div class="form-row"><span>n_regions</span><span class="val">4</span></div>
            <div class="form-row"><span>weeks/month</span><span class="val">4</span></div>
          </div>
        </div>
        <div class="beam-wrap" data-section="revenue">
          <div class="beam-content">
            <h3>💰 Revenue (收入)</h3>
            <div class="form-row"><span>initial_pv</span><span class="val">1500</span></div>
            <div class="form-row"><span>monthly_renew</span><span class="val">100</span></div>
          </div>
        </div>
        <div class="beam-wrap" data-section="commission">
          <div class="beam-content">
            <h3>🎁 Commission (报酬)</h3>
            <div class="form-row"><span>own_basic_rate</span><span class="val">15%</span></div>
            <div class="form-row"><span>pair_bonus 1代</span><span class="val">15%</span></div>
            <div class="form-row"><span>team_bonus 4档</span><span class="val">15-30%</span></div>
          </div>
        </div>
      </div>

      <!-- RIGHT: Canvas 树形 + 8 卡片 -->
      <div class="p3-right">
        <h2>🌲 树形图 (Canvas 2D)</h2>
        <div class="canvas-wrap">
          <canvas id="tree-canvas" width="600" height="280"></canvas>
          <p class="canvas-hint">省略 L4+, 共 2144 节点</p>
        </div>

        <h2>💎 8 种报酬 — 月 14 累计</h2>
        <div class="p3-cards">
          <div class="card" data-field="ownBasic"><div class="label">ownBasic</div><div class="val">—</div></div>
          <div class="card" data-field="pairBonus"><div class="label">pairBonus</div><div class="val">—</div></div>
          <div class="card" data-field="teamBonus"><div class="label">teamBonus</div><div class="val">—</div></div>
          <div class="card" data-field="savings"><div class="label">savings</div><div class="val">—</div></div>
          <div class="card" data-field="leader"><div class="label">leader</div><div class="val">—</div></div>
          <div class="card" data-field="horizontal"><div class="label">horizontal</div><div class="val">—</div></div>
          <div class="card" data-field="retail"><div class="label">retail</div><div class="val">—</div></div>
          <div class="card card-highlight" data-field="total"><div class="label">total</div><div class="val">—</div></div>
        </div>

        <div class="p3-submit-row">
          <button id="btn-preview" class="p3-preview-btn">👁 树形预览</button>
          <button id="btn-submit" class="p3-submit-btn">🎲 提交场景 + 算报酬</button>
        </div>

        <div id="toast" class="p3-toast" style="display:none"></div>
      </div>
    </div>
  </div>

  <script src="/static/scenario.js"></script>
</body>
</html>
```

- [ ] **Step 2: 写 `static/scenario.css` 基础布局 (2 栏 + 暗背景 + border-beam 动效)**

```css
/* === P3 scenario.css === */

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif;
  background: #0f0f1e;
  color: #D6ECF0;
  min-height: 100vh;
  padding: 16px;
}

.p3-container {
  max-width: 1000px;
  margin: 0 auto;
}

.p3-title {
  color: #5AA4AE;
  font-size: 18px;
  letter-spacing: 1px;
  margin-bottom: 16px;
  text-align: center;
}

.p3-layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 16px;
}

.p3-left, .p3-right {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* === border-beam 纯 CSS (跟 npm border-beam 包效果一致) === */
.beam-wrap {
  position: relative;
  padding: 1px;
  border-radius: 12px;
  background: #1a1a2e;
  overflow: visible;
}
.beam-wrap::before, .beam-wrap::after {
  content: '';
  position: absolute;
  inset: -1px;
  border-radius: 12px;
  pointer-events: none;
}
.beam-wrap::before {
  background: conic-gradient(
    from 0deg,
    transparent 0deg,
    #5AA4AE 60deg,
    #758A99 120deg,
    transparent 180deg,
    transparent 360deg
  );
  animation: beam-rotate 3s linear infinite;
  z-index: 1;
}
.beam-wrap::after {
  background: rgba(90, 164, 174, 0.15);
  filter: blur(8px);
  z-index: 0;
}
@keyframes beam-rotate { to { transform: rotate(360deg); } }

.beam-content {
  position: relative;
  background: #1a1a2e;
  border-radius: 11px;
  padding: 12px 16px;
  z-index: 2;
}
.beam-content h3 {
  color: #5AA4AE;
  font-size: 12px;
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.form-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  padding: 4px 0;
  color: #758A99;
}
.form-row .val {
  color: #F0C239;
  font-family: "Consolas", monospace;
}

/* === Canvas === */
.canvas-wrap {
  background: #1a1a2e;
  border-radius: 8px;
  padding: 8px;
}
#tree-canvas {
  background: #0a0a14;
  border-radius: 4px;
  display: block;
  width: 100%;
}
.canvas-hint {
  font-size: 11px;
  color: #758A99;
  margin-top: 4px;
  text-align: center;
}

/* === 8 报酬卡片 === */
.p3-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}
.card {
  background: #1a1a2e;
  border-radius: 8px;
  padding: 8px 12px;
}
.card .label {
  font-size: 11px;
  color: #758A99;
  text-transform: uppercase;
}
.card .val {
  font-size: 16px;
  color: #F0C239;
  font-family: "Consolas", monospace;
  margin-top: 4px;
}
.card-highlight { background: #2a3a3e; border: 1px solid #C0EBD7; }
.card-highlight .val { color: #C0EBD7; }

/* === 按钮 === */
.p3-submit-row {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
.p3-submit-btn, .p3-preview-btn {
  padding: 10px 16px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  border: none;
}
.p3-submit-btn {
  background: linear-gradient(135deg, #5AA4AE, #758A99);
  color: #fff;
  flex: 1;
}
.p3-submit-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.p3-preview-btn {
  background: transparent;
  color: #C0EBD7;
  border: 1px solid #758A99;
}

/* === Toast === */
.p3-toast {
  position: fixed;
  top: 16px;
  right: 16px;
  padding: 12px 16px;
  border-radius: 6px;
  font-size: 13px;
  z-index: 100;
}
.p3-toast.error { background: #EF4444; color: #fff; }
.p3-toast.success { background: #5AA4AE; color: #fff; }
```

- [ ] **Step 3: 写 `static/scenario.js` 最小占位 (空函数, 不报错)**

```javascript
// static/scenario.js
// P3 PR1: 招商/路演实时计算器 (2026-08-07)

(function() {
  'use strict';

  const formState = {
    name: 'live_scenario',
    tree_shape: { fork_type: 'binary', max_level: 10,
                  layer_counts: {0: 1, 1: 4, 2: 8, 3: 16, 4: 32, 5: 64, 6: 128, 7: 256, 8: 512, 9: 1024, 10: 99} },
    growth: { nodes_per_region_per_week: 9, n_regions: 4, join_strategy: 'round_robin', weeks_per_month: 4 },
    revenue: { initial_pv: 1500, monthly_renew_pv: 100, color_rule: '4_color_cycle', color_names: ['红', '紫', '青绿', '蓝'] },
    commission_config: {
      enable_retail_profit: false, enable_team_bonus: true,
      team_bonus_tier_rates: {200: 0.15, 500: 0.20, 1000: 0.25, 1500: 0.30},
      team_bonus_window_weeks: 4,
      enable_own_basic: true, own_basic_rate: 0.15, own_basic_line_pv_cap: 13334,
      enable_savings: true, savings_usd_threshold: 250.0, savings_rate: 0.15, savings_cap_usd: 500.0,
      enable_pair_bonus: true,
      pair_bonus_ratios: {1: 0.15, 2: 0.10, 3: 0.05, 4: 0.05, 5: 0.05, 6: 0.05},
      pair_bonus_4th_usd_threshold: 500.0, pair_bonus_5th_usd_threshold: 1000.0,
      enable_leader_dividend: true, leader_dividend_threshold_pv: 13334,
      leader_dividend_share_usd: 500.0, leader_dividend_tiers: {1: 2, 2: 4, 3: 6, 4: 8},
      enable_horizontal_leader: true, horizontal_leader_share_usd: 250.0,
      horizontal_leader_tiers: {1: 2, 2: 2, 3: 4, 4: 6},
      enable_opportunity_points: false,
    },
  };

  // 公开 API, 后续 Task 3-4 替换 stub
  window.P3 = {
    formState,
    getFormState() { return formState; },
    showToast(msg, type) { console.log(`[toast-${type}]`, msg); },
  };
})();
```

- [ ] **Step 4: 验证 (浏览器加载 `/static/scenario.html` 看 2 栏布局)**

```powershell
python -m uvicorn main:app --port 38089 --host 127.0.0.1
# 浏览器打开 http://127.0.0.1:38089/static/scenario.html
# 期望: 暗背景, 4 个 border-beam 框 (3s 光束旋转), 2 栏布局
```

- [ ] **Step 5: Commit**

```bash
git add static/scenario.html static/scenario.css static/scenario.js
git commit -m "feat(scenario-ui): P3 PR1 Task 1 — scenario.html/css/js 基础布局 (border-beam + 2 栏 + 8 卡片占位)"
```

---

## Task 2: Canvas 树形图渲染 — `static/scenario.js` 完整实现

**Files:**
- Modify: `static/scenario.js`

- [ ] **Step 1: 替换 `static/scenario.js` 完整实现 (Canvas 树形图)**

```javascript
// static/scenario.js (完整实现)
(function() {
  'use strict';

  const COLORS = {
    bg: '#0a0a14', line: '#5AA4AE', root: '#5AA4AE',
    region1: '#5AA4AE', region2: '#C0EBD7', region3: '#F0C239', region4: '#758A99',
    leaf: '#3a3a4e', text: '#fff',
  };

  const TREE = {
    // 1 + 4 + 8 + 16 = 29 节点 (L0-L3)
    root: { x: 0.5, y: 0.10, r: 14, label: '0' },
    l1: [
      { x: 0.18, y: 0.30, r: 10, label: '1' },
      { x: 0.38, y: 0.30, r: 10, label: '2' },
      { x: 0.62, y: 0.30, r: 10, label: '3' },
      { x: 0.82, y: 0.30, r: 10, label: '4' },
    ],
    l2: [], // 8 节点, 4 L1 各 2 子
    l3: [], // 16 节点, 8 L2 各 2 子
  };

  // 生成 L2/L3 坐标
  TREE.l1.forEach((p, i) => {
    for (let j = 0; j < 2; j++) {
      TREE.l2.push({ x: p.x - 0.04 + j * 0.08, y: 0.55, r: 7, label: `${i+1}.${j+1}` });
    }
  });
  TREE.l2.forEach((p, i) => {
    for (let j = 0; j < 2; j++) {
      TREE.l3.push({ x: p.x - 0.025 + j * 0.05, y: 0.82, r: 5, label: '' });
    }
  });

  function drawNode(ctx, node, w, h, color) {
    const x = node.x * w, y = node.y * h;
    ctx.beginPath();
    ctx.arc(x, y, node.r, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    if (node.label) {
      ctx.fillStyle = COLORS.text;
      ctx.font = '9px monospace';
      ctx.textAlign = 'center';
      ctx.fillText(node.label, x, y + 3);
    }
  }
  function drawLine(ctx, n1, n2, w, h) {
    ctx.beginPath();
    ctx.moveTo(n1.x * w, n1.y * h);
    ctx.lineTo(n2.x * w, n2.y * h);
    ctx.strokeStyle = COLORS.line;
    ctx.globalAlpha = 0.4;
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.globalAlpha = 1;
  }

  function renderTree() {
    const canvas = document.getElementById('tree-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width, h = canvas.height;
    ctx.fillStyle = COLORS.bg;
    ctx.fillRect(0, 0, w, h);

    // L0 -> L1 连线
    TREE.l1.forEach(c => drawLine(ctx, TREE.root, c, w, h));
    // L1 -> L2 连线
    TREE.l1.forEach((p, i) => {
      TREE.l2.slice(i * 2, i * 2 + 2).forEach(c => drawLine(ctx, p, c, w, h));
    });
    // L2 -> L3 连线
    TREE.l2.forEach((p, i) => {
      TREE.l3.slice(i * 2, i * 2 + 2).forEach(c => drawLine(ctx, p, c, w, h));
    });

    // 画节点
    drawNode(ctx, TREE.root, w, h, COLORS.root);
    TREE.l1.forEach((c, i) => drawNode(ctx, c, w, h, COLORS[`region${i+1}`]));
    TREE.l2.forEach(c => drawNode(ctx, c, w, h, COLORS.leaf));
    TREE.l3.forEach(c => drawNode(ctx, c, w, h, COLORS.leaf));
  }

  // 文档加载后立即画
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', renderTree);
  } else {
    renderTree();
  }

  // 公开 API
  window.P3_renderTree = renderTree;
})();
```

- [ ] **Step 2: 验证 (浏览器刷新 `/static/scenario.html`)**

期望: Canvas 显示 1 个 L0 root + 4 L1 父 (4 色) + 8 L2 节点 + 16 L3 节点, 共 29 个圆 + 连线.

- [ ] **Step 3: Commit**

```bash
git add static/scenario.js
git commit -m "feat(scenario-ui): P3 PR1 Task 2 — Canvas 树形图渲染 (29 节点 L0-L3 + 4 色 region)"
```

---

## Task 3: POST/GET 路由调用 + 8 报酬卡片更新 — `static/scenario.js` API 集成

**Files:**
- Modify: `static/scenario.js`

- [ ] **Step 1: 加 `submitScenario` + `updateCards` 函数到 `static/scenario.js`**

在 `static/scenario.js` 末尾 (IIFE 内) 加:

```javascript
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  function showToast(msg, type) {
    const t = $('#toast');
    t.textContent = msg;
    t.className = 'p3-toast ' + type;
    t.style.display = 'block';
    setTimeout(() => { t.style.display = 'none'; }, 3000);
  }

  function formatUSD(s) {
    // 服务端返 "1234.5678" (Decimal 序列化), 格式化为 "$1,234.57"
    const n = parseFloat(s);
    if (isNaN(n) || n === 0) return '$0.00';
    return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function updateCards(state, overview) {
    // overview 8 字段 (跟 scenario_routes.py: get_overview 返的 dict 一致)
    const map = {
      ownBasic: overview.ownBasic,
      pairBonus: overview.pairBonus,
      teamBonus: overview.teamBonus,
      savings: overview.savings,
      leader: overview.leader,
      horizontal: overview.horizontal,
      retail: overview.retail,
      total: overview.total,
    };
    $$('.p3-cards .card').forEach(card => {
      const field = card.dataset.field;
      if (map[field] !== undefined) {
        card.querySelector('.val').textContent = formatUSD(map[field]);
      }
    });
  }

  async function submitScenario() {
    const btn = $('#btn-submit');
    btn.disabled = true;
    btn.textContent = '提交中...';

    // JSON 字段 key 转 str (Pydantic v2 Dict[str, int] 要求)
    const body = JSON.parse(JSON.stringify(window.P3.getFormState()));
    body.tree_shape.layer_counts = Object.fromEntries(
      Object.entries(body.tree_shape.layer_counts).map(([k, v]) => [String(k), v])
    );
    body.commission_config.team_bonus_tier_rates = Object.fromEntries(
      Object.entries(body.commission_config.team_bonus_tier_rates).map(([k, v]) => [String(k), v])
    );
    body.commission_config.pair_bonus_ratios = Object.fromEntries(
      Object.entries(body.commission_config.pair_bonus_ratios).map(([k, v]) => [String(k), v])
    );
    body.commission_config.leader_dividend_tiers = Object.fromEntries(
      Object.entries(body.commission_config.leader_dividend_tiers).map(([k, v]) => [String(k), v])
    );
    body.commission_config.horizontal_leader_tiers = Object.fromEntries(
      Object.entries(body.commission_config.horizontal_leader_tiers).map(([k, v]) => [String(k), v])
    );

    try {
      // 1) POST /api/scenarios
      const postResp = await fetch('/api/scenarios', {
        method: 'POST', headers: {'Content-Type': 'application/json; charset=utf-8'},
        body: JSON.stringify(body),
      });
      if (!postResp.ok) {
        const err = await postResp.json();
        showToast('提交失败: ' + (err.detail || postResp.status), 'error');
        return;
      }
      const { id: scenario_id } = await postResp.json();

      // 2) GET /api/scenarios/{id}/overview?month=14
      const ovResp = await fetch(`/api/scenarios/${scenario_id}/overview?month=14`);
      if (!ovResp.ok) {
        showToast('overview 失败: ' + ovResp.status, 'error');
        return;
      }
      const overview = await ovResp.json();

      // 3) 更新卡片
      updateCards(null, overview);
      showToast(`scenario ${scenario_id} 计算完成`, 'success');
    } catch (err) {
      showToast('网络错误: ' + err.message, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = '🎲 提交场景 + 算报酬';
    }
  }

  // 绑定按钮
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      $('#btn-submit').addEventListener('click', submitScenario);
    });
  } else {
    $('#btn-submit').addEventListener('click', submitScenario);
  }
```

- [ ] **Step 2: 验证 (浏览器点提交按钮, 等 2s, 8 卡片显示数字)**

期望: ownBasic ~$30K, pairBonus ~$250K, savings ~$4.5K, horizontal ~$22.5K, total ~$1.25M.

- [ ] **Step 3: Commit**

```bash
git add static/scenario.js
git commit -m "feat(scenario-ui): P3 PR1 Task 3 — POST/GET 路由集成 + 8 报酬卡片更新 + toast 错误处理"
```

---

## Task 4: 主菜单入口 — `static/index.html` 加 1 个 nav link

**Files:**
- Modify: `static/index.html`

- [ ] **Step 1: 找 nav 位置**

用 Select-String 找 `static/index.html` 里 nav 区域:

```powershell
Select-String -Pattern "navbar|nav-link|topbar" static/index.html | Select-Object -First 5
```

期望: 找到 1 个 nav 容器, 里面有 4 个 tab link (运营/订单/...).

- [ ] **Step 2: 在 4 tab 旁边加 1 个新 link**

```html
<a href="/static/scenario.html" class="nav-link">📐 Scenario</a>
```

具体位置 (例):
```html
<nav class="navbar">
  <a href="#tab1" class="nav-link active">运营</a>
  <a href="#tab2" class="nav-link">订单</a>
  <a href="#tab3" class="nav-link">报表</a>
  <a href="#tab4" class="nav-link">设置</a>
  <a href="/static/scenario.html" class="nav-link">📐 Scenario</a>  <!-- ★ P3 PR1 加 -->
</nav>
```

(实际位置根据 Select-String 找到的内容调整)

- [ ] **Step 3: 验证 (浏览器打开 `/static/index.html`, 顶部 nav 看到 "📐 Scenario" 入口)**

- [ ] **Step 4: Commit**

```bash
git add static/index.html
git commit -m "feat(scenario-ui): P3 PR1 Task 4 — static/index.html 主菜单加 📐 Scenario 入口"
```

---

## Task 5: Playwright e2e 测试 — `tests/test_scenario_ui_e2e.py`

**Files:**
- Create: `tests/test_scenario_ui_e2e.py`

- [ ] **Step 1: 写 e2e 测试**

```python
"""P3 PR1: scenario.html e2e 测试 (Playwright)

业务:
  - 加载 /static/scenario.html
  - 填 4 组参数 (默认值)
  - 点提交
  - 校验 8 报酬卡片显示数字 + Canvas 树形有内容
  - 校验 border-beam 4 个框存在
"""
import subprocess
import time
import socket

import pytest

PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass


def _port_open(host, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


@pytest.fixture(scope="module")
def uvicorn_server():
    """启 uvicorn 38089 fixture, yield 后 teardown"""
    if _port_open("127.0.0.1", 38089):
        yield "http://127.0.0.1:38089"
        return
    proc = subprocess.Popen(
        ["python", "-m", "uvicorn", "main:app", "--port", "38089", "--host", "127.0.0.1"],
        cwd=r"D:\Projects\Reward\RewardAgentAnalysis",
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # 等 server ready
    for _ in range(30):
        if _port_open("127.0.0.1", 38089):
            break
        time.sleep(0.5)
    yield "http://127.0.0.1:38089"
    proc.terminate()
    proc.wait(timeout=5)


@pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="playwright not installed")
def test_scenario_page_loads(uvicorn_server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{uvicorn_server}/static/scenario.html")
        # 标题校验
        assert "SCENARIO" in page.title()
        # 4 个 border-beam 框
        beams = page.query_selector_all(".beam-wrap")
        assert len(beams) == 4, f"期望 4 个 border-beam, 实际 {len(beams)}"
        # Canvas 存在
        canvas = page.query_selector("#tree-canvas")
        assert canvas is not None
        # 8 卡片
        cards = page.query_selector_all(".p3-cards .card")
        assert len(cards) == 8, f"期望 8 卡片, 实际 {len(cards)}"
        # 提交按钮文案
        btn = page.query_selector("#btn-submit")
        assert "提交场景" in btn.inner_text()
        browser.close()


@pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="playwright not installed")
def test_scenario_submit_shows_8_cards(uvicorn_server):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{uvicorn_server}/static/scenario.html")
        # 点提交
        page.click("#btn-submit")
        # 等卡片值变化 (2s 预算)
        for _ in range(40):
            total = page.query_selector('.card[data-field="total"] .val').inner_text()
            if total != "—" and total != "$0.00":
                break
            time.sleep(0.1)
        # 校验 8 卡片有数字
        for field in ["ownBasic", "pairBonus", "teamBonus", "savings",
                      "leader", "horizontal", "retail", "total"]:
            val = page.query_selector(f'.card[data-field="{field}"] .val').inner_text()
            assert val.startswith("$"), f"{field} 应该是 $XX.XX, 实际 {val!r}"
        # total > 0
        total = page.query_selector('.card[data-field="total"] .val').inner_text()
        assert total != "$0.00", f"total 应该是 > 0, 实际 {total}"
        browser.close()
```

- [ ] **Step 2: 跑 e2e 测试 (如果有 playwright) + 加 pytest skip**

```powershell
cd D:\Projects\Reward\RewardAgentAnalysis
python -m pytest tests/test_scenario_ui_e2e.py -v
```

期望: 2 passed (有 playwright) 或 2 skipped (无 playwright).

- [ ] **Step 3: Commit**

```bash
git add tests/test_scenario_ui_e2e.py
git commit -m "test(scenario-ui): P3 PR1 Task 5 — Playwright e2e (页面加载 + 提交后 8 卡片)"
```

---

## Task 6: AGENTS.md §6.5 状态记录

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: 加 §6.5 章节**

在 §6.4 (PR4 状态) 之后加:

```markdown
### 6.5 P3 PR1 — 树形动态生长 UI (独立 scenario.html)

**业务**: 招商/路演客户调 4 组参数, 实时看 8 种报酬在 15 月累计 + Canvas 树形图
**完成日**: 2026-08-07 (本轮)
**Commit**: 见 git log (Task 1-6 各 1 commit, Task 5 e2e 用 @skipif 兜底)
**关键文件**:
- `static/scenario.html` — 2 栏布局: 左 4 个 border-beam 表单 + 右 Canvas + 8 卡片
- `static/scenario.css` — 科技感样式 (border-beam 纯 CSS conic-gradient + 暗背景 + 多色 token)
- `static/scenario.js` — Canvas 树形渲染 + POST/GET 路由调用 + 8 卡片更新 + toast
- `static/index.html` — 顶部 nav 加 `<a href="/static/scenario.html">📐 Scenario</a>` 入口
- `tests/test_scenario_ui_e2e.py` — Playwright e2e (skipif 兜底, 没 playwright 不阻塞)

**验收 (5/5 task 验证)**:
- Task 1 基础布局: 浏览器加载 2 栏 + 4 border-beam + 8 卡片占位
- Task 2 Canvas 树形: 29 节点 L0-L3 渲染 (L4+ 提示省略)
- Task 3 API 集成: 1 POST + 1 GET (overview) ≤ 2s, 8 卡片有数字, total > 0
- Task 4 入口: 主菜单 nav 看到 "📐 Scenario" link
- Task 5 e2e: 2 测试 (load + submit), skipif 兜底

**业务价值 (路演场景)**:
- 调 4 组参数 → 提交 → 实时看 8 报酬 (≤2s) → 演示给客户
- 跟 scenario_routes 3 路由 1:1 对接, 0 后端改动
- 科技感视觉 (border-beam 光束) 突出"现代化分析"

**后续 (P3 PR2/PR3)**:
- PR2: 时间轴折线 + 月累计
- PR3: 多 scenario 对比 + 导出 PNG/CSV
```

- [ ] **Step 2: 跑全部 PR1+PR2+PR3 测试 + P3 e2e**

```powershell
cd D:\Projects\Reward\RewardAgentAnalysis
python -m pytest tests/test_scenario_orm.py tests/test_migrate_scenarios.py tests/test_scenario_repository.py tests/test_scenario_routes.py tests/test_scenario_builder.py tests/test_scenario_pv.py tests/test_scenario_cache.py tests/test_scenario_consistency.py tests/test_scenario_model.py tests/test_commission_own_basic.py tests/test_pr2_root_consistency.py tests/test_db_admin.py tests/test_scenario_ui_e2e.py 2>&1 | Select-Object -Last 5
```

期望: 67 + 2 = 69 测试 (PR1+PR2+PR3, P3 e2e skipif 兜底).

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md
git commit -m "docs(agents): §6.5 P3 PR1 状态记录 (独立 scenario.html + border-beam + Canvas 29 节点 + e2e)"
```

---

## 验证清单 (PR1 全部完成后)

- [ ] 4 个 border-beam 表单 (3s 光束周期)
- [ ] Canvas 树形 29 节点 (L0-L3) + 提示省略
- [ ] 8 报酬卡片 + total highlight
- [ ] 提交 ≤ 2s, total > 0
- [ ] toast 错误处理可见
- [ ] 主菜单入口可见
- [ ] Playwright e2e 2 测试 (load + submit) pass 或 skip
- [ ] AGENTS.md §6.5 状态记录
- [ ] 67+2=69 测试 pass

## Self-Review Checklist

- [ ] Spec coverage: 12 章节每章节都对应到 task (5 task)
- [ ] Placeholder scan: 无 TBD / TODO / "类似 Task N"
- [ ] DRY: 4 个表单样式复用 beam-wrap, 8 卡片样式复用 .card
- [ ] YAGNI: 不画 L4+ (2K 节点超出 PR1 范围), 不做拖拽实时调参
- [ ] TDD: Task 5 是 e2e 测试, Task 1-4 走 "实现 + 浏览器验证" (前端不好 TDD)
- [ ] Frequent commits: 6 task = 6 commit
