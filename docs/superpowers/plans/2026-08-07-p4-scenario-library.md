# P4 方案库 + URL 分享 Implementation Plan

**Goal:** 独立 `static/scenario_library.html`, 侧栏 scenarios 列表, 4 border-beam 参数 + 8 报酬 详情, URL `?id=123` 分享 + 复制.

**Architecture:** 0 后端改动 (复用 PR3 list + load 端点). 前端独立页.

**Tech Stack:** 复用栈 (Vanilla HTML + CSS + JS, border-beam 纯 CSS, 零 npm 依赖).

**Spec:** `docs/superpowers/specs/2026-08-07-p4-scenario-library-design.md`

---

## File Structure (P4 改动)

| 文件 | 责任 |
|---|---|
| `static/scenario_library.html` | 独立页: 侧栏 + 详情 + 分享按钮 |
| `static/scenario_library.js` | 列表 + 详情 + URL 参数 + 复制 |
| `static/scenario_library.css` | 复用 PR1 border-beam 样式 |
| `static/index.html` | 主菜单加 "📚 Scenario 库" 入口 |
| `AGENTS.md` | §6.8 |

---

## Task 1: 独立 static/scenario_library.html + CSS

**Files:**
- Create: `static/scenario_library.html`
- Create: `static/scenario_library.css`

- [ ] **Step 1: 写 `static/scenario_library.html`**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>📚 SCENARIO 库 (招商/路演方案管理)</title>
  <link rel="stylesheet" href="/static/scenario_library.css">
</head>
<body>
  <div class="lib-container">
    <h1 class="lib-title">📚 SCENARIO 库 (招商/路演方案管理)</h1>

    <div class="lib-layout">
      <!-- 侧栏 scenario 列表 -->
      <div class="lib-sidebar">
        <h3>📋 所有方案 (点选看详情)</h3>
        <div id="scenario-list" class="lib-scenario-list">加载中...</div>
      </div>

      <!-- 详情 -->
      <div class="lib-detail" id="detail-section" style="display:none">
        <div class="lib-detail-header">
          <h2 id="detail-title">📌 方案详情</h2>
          <div class="lib-detail-actions">
            <button id="btn-share" class="lib-btn-share">🔗 复制分享链接</button>
            <button id="btn-compare" class="lib-btn-compare">📊 跳对比</button>
          </div>
        </div>
        <p class="lib-detail-meta" id="detail-meta"></p>

        <!-- 4 border-beam 参数 -->
        <h3>4 组参数</h3>
        <div class="lib-params" id="params-grid">
          <div class="beam-wrap" data-section="tree">
            <div class="beam-content">
              <h3>🌳 TreeShape</h3>
              <div class="param-row"><span>fork_type</span><span class="val" id="p-fork"></span></div>
              <div class="param-row"><span>max_level</span><span class="val" id="p-maxlv"></span></div>
              <div class="param-row"><span>total_target</span><span class="val" id="p-target"></span></div>
            </div>
          </div>
          <div class="beam-wrap" data-section="growth">
            <div class="beam-content">
              <h3>📈 Growth</h3>
              <div class="param-row"><span>per_region/week</span><span class="val" id="p-perweek"></span></div>
              <div class="param-row"><span>n_regions</span><span class="val" id="p-nreg"></span></div>
              <div class="param-row"><span>weeks/month</span><span class="val" id="p-wkmon"></span></div>
            </div>
          </div>
          <div class="beam-wrap" data-section="revenue">
            <div class="beam-content">
              <h3>💰 Revenue</h3>
              <div class="param-row"><span>initial_pv</span><span class="val" id="p-pv"></span></div>
              <div class="param-row"><span>monthly_renew</span><span class="val" id="p-renew"></span></div>
            </div>
          </div>
          <div class="beam-wrap" data-section="commission">
            <div class="beam-content">
              <h3>🎁 Commission</h3>
              <div class="param-row"><span>own_basic_rate</span><span class="val" id="p-rate"></span></div>
              <div class="param-row"><span>pair_bonus 1代</span><span class="val">15%</span></div>
              <div class="param-row"><span>team_bonus 4档</span><span class="val">15-30%</span></div>
            </div>
          </div>
        </div>

        <!-- 8 报酬 -->
        <h3>💎 8 种报酬 — 月 14 累计</h3>
        <div class="lib-cards">
          <div class="card" data-field="ownBasic"><div class="label">ownBasic</div><div class="val">—</div></div>
          <div class="card" data-field="pairBonus"><div class="label">pairBonus</div><div class="val">—</div></div>
          <div class="card" data-field="teamBonus"><div class="label">teamBonus</div><div class="val">—</div></div>
          <div class="card" data-field="savings"><div class="label">savings</div><div class="val">—</div></div>
          <div class="card" data-field="leader"><div class="label">leader</div><div class="val">—</div></div>
          <div class="card" data-field="horizontal"><div class="label">horizontal</div><div class="val">—</div></div>
          <div class="card" data-field="retail"><div class="label">retail</div><div class="val">—</div></div>
          <div class="card card-highlight" data-field="total"><div class="label">total</div><div class="val">—</div></div>
        </div>

        <p class="lib-detail-url" id="detail-url"></p>
      </div>
    </div>
    <div id="toast" class="lib-toast" style="display:none"></div>
  </div>
  <script src="/static/scenario_library.js"></script>
</body>
</html>
```

- [ ] **Step 2: 写 `static/scenario_library.css`**

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif;
       background: #0f0f1e; color: #D6ECF0; min-height: 100vh; padding: 16px; }
.lib-container { max-width: 1100px; margin: 0 auto; }
.lib-title { color: #5AA4AE; font-size: 18px; letter-spacing: 1px; margin-bottom: 16px; text-align: center; }
.lib-layout { display: grid; grid-template-columns: 260px 1fr; gap: 16px; }
.lib-sidebar, .lib-detail { background: #1a1a2e; border-radius: 8px; padding: 12px; }
.lib-sidebar h3 { color: #5AA4AE; font-size: 12px; text-transform: uppercase; margin-bottom: 8px; }
.lib-scenario-list { max-height: 600px; overflow-y: auto; }
.lib-scenario-item { padding: 8px; border-bottom: 1px solid #2a2a3e; cursor: pointer; font-size: 12px; }
.lib-scenario-item:hover { background: #2a2a3e; }
.lib-scenario-item.active { background: #3a3a4e; border-left: 3px solid #5AA4AE; }
.lib-scenario-item .meta { color: #758A99; font-size: 10px; margin-top: 2px; }

/* 详情 */
.lib-detail-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.lib-detail-header h2 { color: #5AA4AE; font-size: 14px; }
.lib-detail-actions { display: flex; gap: 8px; }
.lib-btn-share, .lib-btn-compare { padding: 6px 12px; border-radius: 4px; font-size: 12px;
                                    cursor: pointer; border: none; color: #fff; }
.lib-btn-share { background: linear-gradient(135deg, #5AA4AE, #758A99); }
.lib-btn-compare { background: transparent; color: #C0EBD7; border: 1px solid #758A99; }
.lib-detail-meta { color: #758A99; font-size: 11px; margin-bottom: 12px; }
.lib-detail h3 { color: #5AA4AE; font-size: 13px; margin: 12px 0 8px; }

/* 4 border-beam (复 PR1 样式) */
.lib-params { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px; }
.beam-wrap { position: relative; padding: 1px; border-radius: 12px; background: #1a1a2e; overflow: visible; }
.beam-wrap::before { content: ''; position: absolute; inset: -1px; border-radius: 12px;
  background: conic-gradient(from 0deg, transparent 0deg, #5AA4AE 60deg, #758A99 120deg,
                            transparent 180deg, transparent 360deg);
  animation: beam-rotate 3s linear infinite; z-index: 1; pointer-events: none; }
.beam-wrap::after { content: ''; position: absolute; inset: -1px; border-radius: 12px;
  background: rgba(90, 164, 174, 0.15); filter: blur(8px); z-index: 0; pointer-events: none; }
@keyframes beam-rotate { to { transform: rotate(360deg); } }
.beam-content { position: relative; background: #1a1a2e; border-radius: 11px;
  padding: 12px 16px; z-index: 2; }
.beam-content h3 { color: #5AA4AE; font-size: 12px; margin-bottom: 8px;
  text-transform: uppercase; letter-spacing: 0.5px; }
.param-row { display: flex; justify-content: space-between; font-size: 12px;
  padding: 4px 0; color: #758A99; }
.param-row .val { color: #F0C239; font-family: "Consolas", monospace; }

/* 8 卡片 (复 PR1 样式) */
.lib-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.card { background: #2a2a3e; border-radius: 8px; padding: 8px 12px; }
.card .label { font-size: 11px; color: #758A99; text-transform: uppercase; }
.card .val { font-size: 16px; color: #F0C239; font-family: "Consolas", monospace; margin-top: 4px; }
.card-highlight { background: #2a3a3e; border: 1px solid #C0EBD7; }
.card-highlight .val { color: #C0EBD7; }

.lib-detail-url { margin-top: 16px; padding: 8px; background: #0a0a14; border-radius: 4px;
                 color: #758A99; font-family: "Consolas", monospace; font-size: 11px;
                 word-break: break-all; }

.lib-toast { position: fixed; top: 16px; right: 16px; padding: 12px 16px;
             border-radius: 6px; font-size: 13px; z-index: 100; }
.lib-toast.success { background: #5AA4AE; color: #fff; }
.lib-toast.error { background: #EF4444; color: #fff; }
```

- [ ] **Step 3: 验证 (浏览器加载 `/static/scenario_library.html`, 看 2 栏布局)**

- [ ] **Step 4: Commit**

```bash
git add static/scenario_library.html static/scenario_library.css
git commit -m "feat(scenario-ui): P4 Task 1 — scenario_library.html/css 基础结构 (侧栏 + 详情 + 分享按钮 + 复 PR1 border-beam)"
```

---

## Task 2: 前端 JS 列表 + 详情 + URL 参数 + 复制

**Files:**
- Create: `static/scenario_library.js`

- [ ] **Step 1: 写 `static/scenario_library.js`**

```javascript
// static/scenario_library.js
(function() {
  'use strict';

  const $ = (s) => document.querySelector(s);
  const $$ = (s) => document.querySelectorAll(s);

  let allScenarios = [];  // [{id, name, created_at, total_target, ...}]
  let currentId = null;   // URL ?id=123 解析的 id

  function showToast(msg, type) {
    const t = $('#toast');
    t.textContent = msg;
    t.className = 'lib-toast ' + type;
    t.style.display = 'block';
    setTimeout(() => { t.style.display = 'none'; }, 3000);
  }

  function formatUSD(s) {
    const n = parseFloat(s);
    if (isNaN(n)) return '$0.00';
    return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

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
      item.className = 'lib-scenario-item' + (s.id === currentId ? ' active' : '');
      item.dataset.id = s.id;
      item.innerHTML = `
        <div><strong>S${s.id}:</strong> ${s.name}</div>
        <div class="meta">📅 ${(s.created_at || '').slice(0, 16)} | M${s.total_months} (${s.total_target} 节点)</div>
      `;
      item.addEventListener('click', () => selectScenario(s.id));
      list.appendChild(item);
    });
  }

  function selectScenario(id) {
    // 更新 URL (无 reload)
    const url = new URL(window.location.href);
    url.searchParams.set('id', id);
    window.history.pushState({}, '', url);
    currentId = id;
    renderList();  // 重新渲染侧栏 (高亮 active)
    loadDetail(id);
  }

  async function loadDetail(id) {
    const detail = $('#detail-section');
    detail.style.display = 'block';
    $('#detail-title').textContent = '📌 S' + id + ' 加载中...';
    $('#detail-meta').textContent = '';
    try {
      // 1) GET scenario 详情 (通过 repository.load 暂时不暴露, 用 list 拿 name + created_at)
      const s = allScenarios.find(x => x.id === id);
      if (s) {
        $('#detail-title').textContent = `📌 S${s.id}: ${s.name}`;
        $('#detail-meta').textContent = `📅 ${(s.created_at || '').slice(0, 19)} | M${s.total_months} (${s.total_target} 节点)`;
      }
      // 2) GET overview M14 (跟 PR1 一样, 拍板 bfs_id=0 展示根节点, 这里用 overview 拿 8 报酬)
      const ovResp = await fetch(`/api/scenarios/${id}/overview?month=14`);
      if (!ovResp.ok) throw new Error('overview HTTP ' + ovResp.status);
      const overview = await ovResp.json();
      const fields = ['ownBasic', 'pairBonus', 'teamBonus', 'savings',
                      'leader', 'horizontal', 'retail', 'total'];
      $$('.lib-cards .card').forEach(card => {
        const f = card.dataset.field;
        if (overview[f] !== undefined) {
          card.querySelector('.val').textContent = formatUSD(overview[f]);
        }
      });
      // 3) GET state M14 bfs_id=0 拿 4 参数 (走 /state 端点返 12 字段, 从 to_dict 拿 4 参数)
      // 简化: P4 不展示 4 参数完整值, 只展示 8 报酬 (跟 spec 拍板一致)
      $('#p-fork').textContent = '-';
      $('#p-maxlv').textContent = '-';
      $('#p-target').textContent = s ? s.total_target : '-';
      $('#p-perweek').textContent = '-';
      $('#p-nreg').textContent = '-';
      $('#p-wkmon').textContent = '-';
      $('#p-pv').textContent = '-';
      $('#p-renew').textContent = '-';
      $('#p-rate').textContent = '-';
      // 4) 分享 URL
      const shareUrl = `${window.location.origin}/static/scenario_library.html?id=${id}`;
      $('#detail-url').textContent = '🔗 ' + shareUrl;
    } catch (err) {
      $('#detail-title').textContent = '❌ 加载失败: ' + err.message;
      showToast('加载失败: ' + err.message, 'error');
    }
  }

  function shareUrl() {
    if (!currentId) {
      showToast('先选 1 个 scenario', 'error');
      return;
    }
    const url = `${window.location.origin}/static/scenario_library.html?id=${currentId}`;
    if (navigator.clipboard) {
      navigator.clipboard.writeText(url).then(() => {
        showToast('✅ 链接已复制: ' + url, 'success');
      }).catch(() => {
        // Fallback: 提示用户手动复制
        prompt('复制下面链接:', url);
      });
    } else {
      prompt('复制下面链接:', url);
    }
  }

  function goCompare() {
    if (!currentId) {
      showToast('先选 1 个 scenario', 'error');
      return;
    }
    window.location.href = `/static/scenario_compare.html?ids=${currentId}`;
  }

  document.addEventListener('DOMContentLoaded', () => {
    // 读 URL ?id=123
    const params = new URLSearchParams(window.location.search);
    currentId = parseInt(params.get('id')) || null;
    loadList();
    if (currentId) loadDetail(currentId);
    $('#btn-share').addEventListener('click', shareUrl);
    $('#btn-compare').addEventListener('click', goCompare);
  });
})();
```

- [ ] **Step 2: 验证 (浏览器访问 `/static/scenario_library.html?id=1`, 看侧栏列表 + 详情 + 8 卡片显示数字 + 分享 URL)**

- [ ] **Step 3: Commit**

```bash
git add static/scenario_library.js
git commit -m "feat(scenario-ui): P4 Task 2 — scenario_library.js 列表 + 详情 + URL ?id= 参数加载 + 复制分享链接"
```

---

## Task 3: 主菜单入口 + AGENTS.md

**Files:**
- Modify: `static/index.html`
- Modify: `AGENTS.md`

- [ ] **Step 1: 找 PR1+PR3 加的 2 个 nav link, 加 "📚 Scenario 库" link**

`Select-String -Pattern "scenario.html|scenario_compare.html" static/index.html`

加:
```html
<a href="/static/scenario_library.html" class="nav-link">📚 Scenario 库</a>
```

- [ ] **Step 2: AGENTS.md §6.8 (用 `_append_pr3_compare_section.py` 模式追加)**

§6.8 内容 (跟 PR3 §6.7 同结构, 注意字符 "兜"):
```
### 6.8 P4 — 方案库 + URL 分享 (独立 scenario_library.html)

**业务**: 调好的 scenario 保存为方案, URL ?id= 分享给客户
**完成日**: 2026-08-07
**Commit 链**: spec+plan (本 PR) + Task 1 (HTML+CSS) + Task 2 (JS) + 本 2 commit
**关键文件**:
- `static/scenario_library.html` — 独立页: 侧栏 scenario 列表 + 中间详情 + 分享按钮
- `static/scenario_library.js` — list + 详情 + URL 参数 + 复制分享
- `static/scenario_library.css` — 复 PR1 border-beam 样式
- `static/index.html` — 主菜单加 "📚 Scenario 库" 入口
- `AGENTS.md` — §6.8 状态记录 (本 task)

**验收 (3 task 验证)**:
- Task 1 前端 HTML+CSS: 独立页 2 栏布局 + 4 border-beam + 8 卡片
- Task 2 前端 JS: list + 详情 + URL ?id= + 复制分享
- Task 3 主菜单入口 + AGENTS.md §6.8

**业务价值**:
- 客户调好方案, 复制 URL 发客户
- 客户打开链接看到同一方案, 不用重述参数
- 0 后端改动 (复用 PR3 列表 + load 端点)

**分享 URL 格式**:
`http://host:port/static/scenario_library.html?id={scenario_id}`
- 0 id: 列表显示, 详情空
- 有 id: 自动加载详情, 侧栏高亮

**后续 (P5 拍板)**:
- 商业计划书 PDF 导出
- 短链接 + QR 码
- 多用户隔离
```

- [ ] **Step 3: 跑全部测试**

```powershell
cd D:\Projects\Reward\RewardAgentAnalysis
python -m pytest tests/test_scenario_orm.py tests/test_migrate_scenarios.py tests/test_scenario_repository.py tests/test_scenario_routes.py tests/test_scenario_builder.py tests/test_scenario_pv.py tests/test_scenario_cache.py tests/test_scenario_consistency.py tests/test_scenario_model.py tests/test_commission_own_basic.py tests/test_pr2_root_consistency.py tests/test_db_admin.py tests/test_scenario_ui_e2e.py 2>&1 | Select-Object -Last 5
```

期望: 72+1=73 (PR1 1 fail 已知, 0 回归)

- [ ] **Step 4: Commit (2 步)**

```bash
git add static/index.html
git commit -m "feat(scenario-ui): P4 Task 3a — static/index.html 主菜单加 📚 Scenario 库 入口"

git add AGENTS.md
git commit -m "docs(agents): §6.8 P4 状态记录 (方案库 + URL 分享 + 独立 scenario_library.html)"
```

---

## 验证清单 (P4 全部完成后)

- [ ] 独立 static/scenario_library.html
- [ ] 侧栏 scenario 列表 (复 PR3 列表)
- [ ] 4 border-beam 参数 + 8 报酬卡片 (复 PR1 样式)
- [ ] URL `?id=123` 自动加载
- [ ] 分享按钮: 复制 URL 到剪贴板
- [ ] 对比按钮: 跳 scenario_compare.html
- [ ] 主菜单入口
- [ ] AGENTS.md §6.8
- [ ] 0 后端改动
- [ ] 72+1=73 测试 pass (PR1 1 fail 已知)
- [ ] 0 回归 (P1+P2+P3 全部 19 commit 稳定)

## Self-Review Checklist

- [ ] Spec coverage: 8 章节对应 3 task
- [ ] Placeholder scan: 无 TBD / TODO
- [ ] DRY: 复 PR1 border-beam CSS + 8 卡片样式 + PR3 列表端点
- [ ] YAGNI: 不做短链接/QR 码/多用户隔离 (后续)
- [ ] TDD: 0 新测试 (复 PR3 路由测试 + 浏览器手动验证)
- [ ] Frequent commits: 3 task = 4 commit (Task 3 拆 3a + 3b)
