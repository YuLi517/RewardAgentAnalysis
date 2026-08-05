# Original Tree Minimap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a right-side fixed minimap panel to the `/original-tree` page so users can see the whole 303-node tree structure at a glance while exploring the detailed main view.

**Architecture:** Convert the existing single-SVG `/original-tree` layout into a flex two-column page (main view 70% left, minimap 30% right). The minimap renders the full 303-node tree using vanilla JS (no new dependencies — project doesn't use d3 today). A shared `viewportState` object is emitted by the main view's existing pan/zoom handlers; the minimap listens to that and updates a blue viewport rectangle in real time. Click/drag on the minimap pans the main view.

**Tech Stack:** vanilla JS, SVG, CSS flex, existing d3-free codebase. Playwright for e2e verification. No backend, DB, or API changes.

**Spec:** `docs/superpowers/specs/2026-08-04-original-tree-minimap-design.md`

**Worktree:** Implementation MUST run inside a `feat-original-tree-minimap` worktree on the main branch. Copy `.env` and `data/rewarddb.db` from main into the worktree before starting the server.

---

## File Structure

Files created or modified by this plan:

- `static/original_tree.html` — main change target. Adds flex layout, minimap SVG, layout algorithm, viewport state sync, click/drag handlers, error handling.
- `static/original_tree_minimap.css` — NEW. Isolates minimap styles (panel, viewport box, hover highlight, tooltip). Keeps `original_tree.html` clean.
- `tests/test_original_tree_minimap.py` — NEW. Playwright e2e test that exercises minimap render, viewport sync, click-to-pan, and zero JS errors.

No backend, no DB, no API changes. JSON fixture is read-only via existing `GET /api/original_tree/data`.

---

## Task 1: Worktree setup + 28081 server up

**Files:**
- Create: `.worktrees/feat-original-tree-minimap/`

- [ ] **Step 1: Create worktree off main**
```powershell
cd D:\Projects\Reward\RewardAgentAnalysis
git worktree add -b feat-original-tree-minimap .worktrees/feat-original-tree-minimap main
```
Expected: worktree created. Branch `feat-original-tree-minimap` listed under `git branch`.

- [ ] **Step 2: Copy env + json + data into worktree**
```powershell
Copy-Item .env .worktrees\feat-original-tree-minimap\.env -Force
New-Item -ItemType Directory -Path .worktrees\feat-original-tree-minimap\json -Force
Copy-Item json\original_tree.json .worktrees\feat-original-tree-minimap\json\ -Force
New-Item -ItemType Directory -Path .worktrees\feat-original-tree-minimap\data -Force
Copy-Item data\rewarddb.db .worktrees\feat-original-tree-minimap\data\rewarddb.db
```
Expected: all three files present in worktree. `git status` in worktree shows clean (data is gitignored).

- [ ] **Step 3: Start uvicorn on port 28081 in the worktree**
```powershell
cd .worktrees\feat-original-tree-minimap
Start-Process python -ArgumentList "-m uvicorn main:app --port 28081 --log-level info" `
  -WorkingDirectory "$PWD" `
  -RedirectStandardOutput "$env:TEMP\uvicorn_minimap.log" `
  -RedirectStandardError "$env:TEMP\uvicorn_minimap.err.log" `
  -NoNewWindow
Start-Sleep -Seconds 5
```
Expected: `python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:28081/api/original_tree/data', timeout=5).read()[:80])"` prints JSON bytes (not connection error).

- [ ] **Step 4: Smoke test the existing /original-tree page**
Run via Playwright (headless, no save):
```javascript
const { chromium } = require('C:\\Users\\rainc\\AppData\\Roaming\\npm\\node_modules\\playwright');
(async () => {
  const b = await chromium.launch({ headless: true });
  const p = await b.newPage();
  const errs = [];
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));
  p.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
  await p.goto('http://127.0.0.1:28081/original-tree', { waitUntil: 'networkidle' });
  const stats = await p.evaluate(() => ({
    total: document.getElementById('statTotal')?.textContent,
    depth: document.getElementById('statDepth')?.textContent,
    minimapExists: !!document.getElementById('minimapPanel'),
  }));
  console.log('stats:', JSON.stringify(stats));
  console.log('errs:', errs.length);
  await b.close();
})();
```
Expected: `stats: {"total":"303","depth":"13","minimapExists":false}` (minimap doesn't exist yet — this is the **failing baseline** for the next task).

- [ ] **Step 5: Commit (no changes — worktree init commit only if needed)**
If worktree is clean, skip. Otherwise commit with message `chore: worktree init for minimap feature`.

---

## Task 2: Add flex layout + minimap panel placeholder

**Files:**
- Modify: `static/original_tree.html` (HTML structure + CSS)
- Create: `static/original_tree_minimap.css` (new file)

- [ ] **Step 1: Create the new CSS file with minimap panel base styles**

Create file `static/original_tree_minimap.css`:
```css
/* ★ 2026-08-04: 原版网体 minimap 样式 (右侧 30% 固定栏) */

/* 整体布局: 工具栏下 flex 横向分栏 */
.original-tree-layout {
  display: flex;
  flex: 1 1 auto;
  min-height: 0;
  position: relative;
}

.main-view-panel {
  flex: 0 0 70%;
  min-width: 0;
  position: relative;
  overflow: hidden;
}

.minimap-panel {
  flex: 0 0 30%;
  min-width: 0;
  border-left: 1px solid var(--border, #D6ECF0);
  background: #FAFBFC;
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.minimap-header {
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 600;
  color: #475569;
  border-bottom: 1px solid var(--border, #D6ECF0);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.minimap-svg-container {
  flex: 1 1 auto;
  position: relative;
  min-height: 0;
}

.minimap-svg {
  width: 100%;
  height: 100%;
  display: block;
  cursor: pointer;
  user-select: none;
}

.minimap-viewport-box {
  fill: rgba(59, 130, 246, 0.12);
  stroke: #3B82F6;
  stroke-width: 1.5;
  pointer-events: none;
}

.minimap-node {
  stroke: #FFFFFF;
  stroke-width: 0.5;
  cursor: pointer;
  transition: stroke 0.1s, stroke-width 0.1s;
}

.minimap-node:hover {
  stroke: #F0C239;
  stroke-width: 1.5;
}

.minimap-tooltip {
  position: absolute;
  pointer-events: none;
  background: rgba(15, 23, 42, 0.95);
  color: #FFFFFF;
  font-size: 11px;
  padding: 4px 8px;
  border-radius: 4px;
  white-space: nowrap;
  z-index: 1000;
  opacity: 0;
  transition: opacity 0.1s;
}

.minimap-tooltip.visible {
  opacity: 1;
}

.minimap-error {
  padding: 16px;
  color: #EF4444;
  font-size: 13px;
  text-align: center;
}
```

- [ ] **Step 2: Modify `static/original_tree.html` to wrap the tree in flex layout and add the aside**

In `static/original_tree.html`, find the existing `<div class="tree-container" id="treeContainer">` (search for `id="treeContainer"`). It is wrapped by some outer div. Replace the outer wrapper with a flex container that includes both the main view and a new minimap aside.

Find this structure (around line 360-440):
```html
<div class="tree-canvas" id="treeCanvas">
  <div class="tree-container" id="treeContainer">...</div>
</div>
```

Replace with:
```html
<div class="original-tree-layout">
  <main class="main-view-panel">
    <div class="tree-canvas" id="treeCanvas">
      <div class="tree-container" id="treeContainer">...</div>
    </div>
  </main>
  <aside class="minimap-panel" id="minimapPanel">
    <div class="minimap-header">
      <span>网体缩略</span>
      <span id="minimapStats" style="font-weight:400;color:#64748B"></span>
    </div>
    <div class="minimap-svg-container" id="minimapSvgContainer">
      <svg class="minimap-svg" id="minimapSvg" xmlns="http://www.w3.org/2000/svg"></svg>
    </div>
  </aside>
</div>
```

- [ ] **Step 3: Link the new CSS file**

Find the existing `<link>` tags in the `<head>` of `static/original_tree.html` (around line 5-15). Add the new CSS file:
```html
<link rel="stylesheet" href="original_tree_minimap.css">
```

- [ ] **Step 4: Verify with Playwright (expect 30% panel + 70% main + 0 errors)**

Run via Playwright:
```javascript
const { chromium } = require('C:\\Users\\rainc\\AppData\\Roaming\\npm\\node_modules\\playwright');
(async () => {
  const b = await chromium.launch({ headless: true });
  const p = await b.newPage();
  const errs = [];
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));
  p.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
  await p.goto('http://127.0.0.1:28081/original-tree', { waitUntil: 'networkidle' });
  const layout = await p.evaluate(() => {
    const main = document.querySelector('.main-view-panel');
    const mini = document.getElementById('minimapPanel');
    const total = main.parentElement.offsetWidth;
    return {
      mainWidthPct: ((main.offsetWidth / total) * 100).toFixed(1),
      miniWidthPct: ((mini.offsetWidth / total) * 100).toFixed(1),
      mainExists: !!main,
      miniExists: !!mini,
      treeStillRenders: !!document.querySelector('.tree-node'),
    };
  });
  console.log('layout:', JSON.stringify(layout));
  console.log('errs:', errs);
  await b.close();
})();
```
Expected: `layout: {"mainWidthPct":"70.0","miniWidthPct":"30.0","mainExists":true,"miniExists":true,"treeStillRenders":true}`, `errs: []`.

- [ ] **Step 5: Commit**
Use Python write-bytes pattern (avoid PowerShell GBK trap — see AGENTS.md §5.13):
```python
import subprocess
from pathlib import Path
msg = """feat(tree): 原版网体加右侧 30% 缩略图占位

- flex 布局: 主视图 70% 宽, 缩略图 30% 宽
- 加 <aside id=minimapPanel> + minimap-header + minimap-svg 占位
- 新 static/original_tree_minimap.css (panel + 后续 viewport 框样式)
- 主视图保持 100% 渲染不变
- 0 JS 错误

Task 2 of 9 in minimap implementation plan.
"""
p = Path(r"C:\Users\rainc\AppData\Local\Temp\commit_t2.txt")
p.write_bytes(msg.encode("utf-8"))
subprocess.run(["git", "add", "static/original_tree.html", "static/original_tree_minimap.css"], cwd=r"D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-minimap", check=True)
subprocess.run(["git", "commit", "-F", str(p)], cwd=r"D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-minimap", check=True)
```
Verify message bytes (avoid PowerShell GBK):
```python
import subprocess, zlib
from pathlib import Path
sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=r"D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-minimap", capture_output=True, text=True, check=True).stdout.strip()
git_file = Path(r"D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-minimap\.git").read_text().strip()
git_dir = Path(git_file.split(": ", 1)[1])
commondir_rel = (git_dir / "commondir").read_text().strip()
commondir = (git_dir / commondir_rel).resolve()
obj = commondir / "objects" / sha[:2] / sha[2:]
raw = zlib.decompress(obj.read_bytes())
msg_bytes = raw.split(b"\n\n", 1)[-1]
assert "右侧 30%" in msg_bytes.decode("utf-8"), "message corrupted"
print(f"OK: commit {sha[:8]}, msg {len(msg_bytes)} bytes clean UTF-8")
```

---

## Task 3: Add viewportState + emit hook from main view

**Files:**
- Modify: `static/original_tree.html` (JS only — append after existing `state` declaration)

- [ ] **Step 1: Add viewportState + emit hook in the existing state block**

In `static/original_tree.html`, find the existing `const state = {...}` block (around line 446). Add a separate `viewportState` object AFTER the state declaration (so existing code is untouched):

```javascript
// ★ 2026-08-04: viewport state (minimap 蓝框订阅这个)
const viewportState = {
  scale: 1,        // 主视图当前 zoom 比例
  offsetX: 0,      // 主视图 pan 偏移 (px)
  offsetY: 0,      // 主视图 pan 偏移 (px)
  naturalW: 0,     // 主视图 SVG 内容的自然宽度 (px, 未缩放)
  naturalH: 0,     // 主视图 SVG 内容的自然高度 (px, 未缩放)
  containerW: 0,   // 主视图容器可视宽 (px)
  containerH: 0,   // 主视图容器可视高 (px)
};

// 通知订阅者 (minimap 用)
const _viewportSubscribers = new Set();
function subscribeViewport(fn) { _viewportSubscribers.add(fn); return () => _viewportSubscribers.delete(fn); }
function emitViewport() {
  for (const fn of _viewportSubscribers) {
    try { fn(viewportState); } catch (e) { console.warn('[viewport sub] error', e); }
  }
}
```

- [ ] **Step 2: Hook existing pan/zoom into emitViewport**

Find the existing `applyTransform()` function in `static/original_tree.html` (search for `function applyTransform`). After the existing transform-application code, append:

```javascript
  // ★ 2026-08-04: emit viewport state for minimap
  const treeCanvas = document.getElementById('treeCanvas');
  const treeContainer = document.getElementById('treeContainer');
  if (treeCanvas && treeContainer) {
    viewportState.scale = state.zoom;
    viewportState.offsetX = state.panX;
    viewportState.offsetY = state.panY;
    // natural size = container offset (before transform)
    viewportState.naturalW = treeContainer.offsetWidth;
    viewportState.naturalH = treeContainer.offsetHeight;
    viewportState.containerW = treeCanvas.offsetWidth;
    viewportState.containerH = treeCanvas.offsetHeight;
    emitViewport();
  }
```

Find the existing `render()` function (around line 493) and ensure it calls `applyTransform()` at the end (it already does, per the existing code). If `applyTransform` already runs on init, then emitViewport will be called on initial render too — good.

- [ ] **Step 3: Verify emit fires on init (Playwright)**
```javascript
const { chromium } = require('C:\\Users\rainc\\AppData\\Roaming\\npm\\node_modules\\playwright');
(async () => {
  const b = await chromium.launch({ headless: true });
  const p = await b.newPage();
  const errs = [];
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));
  p.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
  await p.goto('http://127.0.0.1:28081/original-tree', { waitUntil: 'networkidle' });
  const state = await p.evaluate(() => ({
    scale: window.viewportState?.scale,
    naturalW: window.viewportState?.naturalW,
    containerW: window.viewportState?.containerW,
    hasEmit: typeof window.emitViewport === 'function',
  }));
  console.log('state:', JSON.stringify(state));
  console.log('errs:', errs);
  await b.close();
})();
```
Wait — the variables were declared with `const` and are scoped to the module, not exposed on `window`. To verify, expose them for testing:
```javascript
// Add to the bottom of the script (test-only hook)
if (typeof window !== 'undefined') {
  window.__test = { viewportState, emitViewport, state };
}
```

Then re-run the Playwright check. Expected: `state: {"scale":1,"naturalW":<number>,"containerW":<number>,"hasEmit":true}`.

- [ ] **Step 4: Remove the test-only `window.__test` exposure before commit**

Delete the lines added in Step 3. The test will re-add it temporarily OR use `page.evaluate` with `Function.prototype.toString` tricks — for now, use a simpler check: subscribe to viewport from inside the page and read the first emission:
```javascript
const state = await p.evaluate(async () => {
  return new Promise((resolve) => {
    // subscribe, wait for first emit
    let captured = null;
    const unsub = window.subscribeViewport
      ? window.subscribeViewport((s) => { captured = s; })
      : null;
    // Trigger emit by calling applyTransform via window if available
    if (unsub) {
      setTimeout(() => {
        unsub();
        resolve(captured);
      }, 500);
    } else {
      resolve({ error: 'subscribeViewport not on window' });
    }
  });
});
```

To make this work, expose the helpers on `window` ONLY in dev mode (the `subscribeViewport`, `viewportState`, `emitViewport` symbols). Add this to the bottom of the script:
```javascript
// Dev/test hook (no-op in production since main is dev server only)
if (typeof window !== 'undefined') {
  window.subscribeViewport = subscribeViewport;
  window.viewportState = viewportState;
  window.emitViewport = emitViewport;
}
```

This stays in the code — it's a small harmless exposure for debugging.

- [ ] **Step 5: Verify and commit**
Run the Playwright check from Step 3 again. Expected: `state: {"scale":1,"naturalW":<number>,"containerW":<number>}` (no `error` field).

Commit:
```python
import subprocess
from pathlib import Path
msg = """feat(tree): 加 viewportState + emit 钩子 (minimap 订阅源)

- 新 viewportState: scale / offsetX/Y / naturalW/H / containerW/H
- subscribeViewport(fn) / emitViewport() 简单 pub-sub
- applyTransform 末尾 emit (主视图 pan/zoom 触发 minimap 跟)
- window 暴露 hook (debug 用, 单文件 dev server 风险小)

Task 3 of 9.
"""
p = Path(r"C:\Users\rainc\AppData\Local\Temp\commit_t3.txt")
p.write_bytes(msg.encode("utf-8"))
subprocess.run(["git", "add", "static/original_tree.html"], cwd=r"D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-minimap", check=True)
subprocess.run(["git", "commit", "-F", str(p)], cwd=r"D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-minimap", check=True)
```

---

## Task 4: Minimap layout algorithm (vanilla JS, BFS horizontal)

**Files:**
- Modify: `static/original_tree.html` (JS only)

- [ ] **Step 1: Add the layout function**

Append to the bottom of the `<script>` block in `static/original_tree.html` (after the existing `applyTransform` function and the `window` exposure from Task 3):

```javascript
// ★ 2026-08-04: minimap layout — 简单 BFS 横向 layout
// 每个节点的 width ∝ (1 + 子孙总数), height 固定
// 整树 fit-to-width 缩放由调用方决定
const MINIMAP_NODE_H = 4;     // 节点 height (px, before fit-to-width scale)
const MINIMAP_GAP_X = 1;      // 兄弟间距 (px)
const MINIMAP_GAP_Y = 6;      // 层间距 (px)
const MINIMAP_PAD = 8;        // 整树 padding (px)

function minimapLayout(root) {
  // 1. BFS 计算每个节点 depth + 子孙数
  const nodes = [];
  const queue = [{ n: root, depth: 0, parentX: 0, parentW: 0 }];
  while (queue.length) {
    const { n, depth, parentX, parentW } = queue.shift();
    const childCount = (n.children || []).length;
    const subtreeCount = 1 + childCount;  // 自身 + 直接子 (递归会扩展)
    // 算子孙总数 (递归)
    let total = 1;
    for (const c of (n.children || [])) {
      total += countSubtree(c);
    }
    function countSubtree(node) {
      let c = 1;
      for (const ch of (node.children || [])) c += countSubtree(ch);
      return c;
    }
    const w = Math.max(1, Math.log2(total + 1) * 4);  // log 缩放, 大分支粗
    const h = MINIMAP_NODE_H;
    nodes.push({ n, depth, w, h, subtreeTotal: total });
    for (const c of (n.children || [])) {
      queue.push({ n: c, depth: depth + 1, parentX: 0, parentW: 0 });
    }
  }
  // 2. 按 (depth, sibling-index) 算 x: 同层 x 累加前一兄弟 width + gap
  const byDepth = {};
  for (const node of nodes) {
    if (!byDepth[node.depth]) byDepth[node.depth] = [];
    byDepth[node.depth].push(node);
  }
  const maxDepth = Math.max(...Object.keys(byDepth).map(Number));
  let cursorX = MINIMAP_PAD;
  for (const node of byDepth[0]) {
    node.x = cursorX;
    node.y = MINIMAP_PAD + node.depth * (MINIMAP_NODE_H + MINIMAP_GAP_Y);
    cursorX += node.w + MINIMAP_GAP_X;
  }
  for (let d = 1; d <= maxDepth; d++) {
    let curX = MINIMAP_PAD;
    for (const node of (byDepth[d] || [])) {
      node.x = curX;
      node.y = MINIMAP_PAD + d * (MINIMAP_NODE_H + MINIMAP_GAP_Y);
      curX += node.w + MINIMAP_GAP_X;
    }
  }
  // 3. 算总尺寸
  const totalW = Math.max(...nodes.map(n => n.x + n.w)) + MINIMAP_PAD;
  const totalH = Math.max(...nodes.map(n => n.y + n.h)) + MINIMAP_PAD;
  // 4. 算 links (parent-child)
  const links = [];
  const nodeByData = new Map(nodes.map(node => [node.n, node]));
  for (const node of nodes) {
    for (const c of (node.n.children || [])) {
      const cn = nodeByData.get(c);
      if (cn) links.push({ from: node, to: cn });
    }
  }
  return { nodes, links, totalW, totalH, maxDepth };
}
```

- [ ] **Step 2: Verify with console log (browser dev tools OR Playwright)**

In the browser, open `http://127.0.0.1:28081/original-tree`, then in the console:
```javascript
const d = await (await fetch('/api/original_tree/data')).json();
const layout = minimapLayout(d);
console.log({ nodeCount: layout.nodes.length, linkCount: layout.links.length, totalW: layout.totalW, totalH: layout.totalH, maxDepth: layout.maxDepth });
```
Expected: `{ nodeCount: 303, linkCount: 302, totalW: <number>, totalH: <number>, maxDepth: 12 }`.

If `nodeCount` is not 303, the BFS is wrong — debug the `queue` / `byDepth` logic.

- [ ] **Step 3: Commit**
```python
import subprocess
from pathlib import Path
msg = """feat(tree): minimap BFS 横向 layout 算法 (vanilla JS, 不引 d3)

- minimapLayout(root): BFS 算 depth + 子孙数, 按 sibling 累加 x
- 节点 width ∝ log2(子孙数 + 1) * 4 (大分支视觉粗)
- 节点 height 固定 4px, 层间距 6px
- 返回 {nodes, links, totalW, totalH, maxDepth}
- 业务级算法: 整树 303 节点, 302 links, 12 层深

Task 4 of 9.
"""
p = Path(r"C:\Users\rainc\AppData\Local\Temp\commit_t4.txt")
p.write_bytes(msg.encode("utf-8"))
subprocess.run(["git", "add", "static/original_tree.html"], cwd=r"D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-minimap", check=True)
subprocess.run(["git", "commit", "-F", str(p)], cwd=r"D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-minimap", check=True)
```

---

## Task 5: Render minimap SVG (nodes + links)

**Files:**
- Modify: `static/original_tree.html` (JS only)

- [ ] **Step 1: Add the render function**

Append to the bottom of the script in `static/original_tree.html`:

```javascript
// ★ 2026-08-04: 渲染缩略图 (一次性绘制 303 节点 + links)
function renderMinimap() {
  if (!state.data) return;
  const svg = document.getElementById('minimapSvg');
  if (!svg) return;
  const layout = minimapLayout(state.data);
  // 1. fit-to-width 缩放
  const container = document.getElementById('minimapSvgContainer');
  const containerW = container.offsetWidth;
  const containerH = container.offsetHeight;
  const fitScale = Math.min(
    (containerW - 2) / layout.totalW,
    (containerH - 2) / layout.totalH
  );
  // 2. 渲染
  svg.innerHTML = '';  // clear
  svg.setAttribute('viewBox', `0 0 ${layout.totalW} ${layout.totalH}`);
  svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
  // links 先画 (在节点下面)
  for (const link of layout.links) {
    const cx = (link.from.x + link.from.w / 2);
    const cy = (link.from.y + link.from.h);
    const tx = (link.to.x + link.to.w / 2);
    const ty = link.to.y;
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    const mx = (cx + tx) / 2;
    path.setAttribute('d', `M ${cx} ${cy} C ${cx} ${mx}, ${tx} ${mx}, ${tx} ${ty}`);
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', '#94A3B8');
    path.setAttribute('stroke-width', '0.5');
    path.setAttribute('opacity', '0.3');
    svg.appendChild(path);
  }
  // 节点
  const BUSINESS_COLOR = {
    ULTIMATE: '#F0C239',
    ELITE: '#5AA4AE',
    BUSINESS: '#10B981',
    MEMBER: '#94A3B8',
  };
  for (const node of layout.nodes) {
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('x', node.x);
    rect.setAttribute('y', node.y);
    rect.setAttribute('width', node.w);
    rect.setAttribute('height', node.h);
    const lvl = (node.n.businessLevel || 'MEMBER').toUpperCase();
    rect.setAttribute('fill', BUSINESS_COLOR[lvl] || BUSINESS_COLOR.MEMBER);
    rect.setAttribute('class', 'minimap-node');
    rect.setAttribute('data-dist-id', node.n.distId || '');
    rect.setAttribute('data-name', node.n.name || '');
    rect.setAttribute('data-level', node.depth + 1);
    rect.setAttribute('data-business-level', lvl);
    svg.appendChild(rect);
  }
  // stats
  const stats = document.getElementById('minimapStats');
  if (stats) {
    stats.textContent = `${layout.nodes.length} 节点 / ${layout.maxDepth + 1} 层`;
  }
  // 存 layout (后续 viewport box 用)
  window.__minimapLayout = layout;
  // 触发初始 viewport 渲染
  emitViewport();
}
```

- [ ] **Step 2: Wire `renderMinimap()` into the existing `render()` function**

Find `function render()` in `static/original_tree.html` (around line 493). Add `renderMinimap();` after `applyTransform();`:

```javascript
function render() {
  if (!state.data) return;
  computeStats(state.data);
  updateStats();
  const root = renderNode(state.data, 0);
  const container = document.getElementById('treeContainer');
  container.innerHTML = '';
  container.appendChild(root);
  applyTransform();
  updateZoomDisplay();
  renderMinimap();  // ★ 2026-08-04: 同步渲染缩略图
}
```

- [ ] **Step 3: Verify minimap renders 303 rects (Playwright)**
```javascript
const { chromium } = require('C:\\Users\rainc\\AppData\\Roaming\\npm\\node_modules\\playwright');
(async () => {
  const b = await chromium.launch({ headless: true });
  const p = await b.newPage();
  const errs = [];
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));
  p.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
  await p.goto('http://127.0.0.1:28081/original-tree', { waitUntil: 'networkidle' });
  const minimap = await p.evaluate(() => {
    const svg = document.getElementById('minimapSvg');
    return {
      rectCount: svg.querySelectorAll('rect.minimap-node').length,
      pathCount: svg.querySelectorAll('path').length,
      stats: document.getElementById('minimapStats')?.textContent,
    };
  });
  console.log('minimap:', JSON.stringify(minimap));
  console.log('errs:', errs);
  await p.screenshot({ path: 'C:\\Users\\rainc\\AppData\\Local\\Temp\\minimap_t5.png', fullPage: true });
  await b.close();
})();
```
Expected: `minimap: {"rectCount":303,"pathCount":302,"stats":"303 节点 / 13 层"}`, `errs: []`.

Open `C:\Users\rainc\AppData\Local\Temp\minimap_t5.png` and confirm visually: minimap on the right shows the full tree in tiny colored rects, with thin lines connecting them. Main view on the left still shows the original tree.

- [ ] **Step 4: Commit**
```python
import subprocess
from pathlib import Path
msg = """feat(tree): 渲染缩略图 (303 节点 + 302 links)

- renderMinimap(): fit-to-width 缩放 + d3-join 风格 (这里用 innerHTML clear + append)
- 节点颜色按 businessLevel (ULTIMATE 金 / ELITE 蓝 / BUSINESS 绿 / MEMBER 灰)
- 链接用贝塞尔曲线 (parent 底 → child 顶), alpha 0.3
- 工具栏 stats 同步显示 "303 节点 / 13 层"
- window.__minimapLayout 暴露供后续 viewport box 用

Task 5 of 9.
"""
p = Path(r"C:\Users\rainc\AppData\Local\Temp\commit_t5.txt")
p.write_bytes(msg.encode("utf-8"))
subprocess.run(["git", "add", "static/original_tree.html"], cwd=r"D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-minimap", check=True)
subprocess.run(["git", "commit", "-F", str(p)], cwd=r"D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-minimap", check=True)
```

---

## Task 6: Viewport indicator (blue box follows main view)

**Files:**
- Modify: `static/original_tree.html` (JS only)

- [ ] **Step 1: Add the viewport box renderer**

Append to the bottom of the script in `static/original_tree.html`:

```javascript
// ★ 2026-08-04: 蓝框 — 主视图 viewport 在缩略图上的投影
function renderViewportBox(vs) {
  const svg = document.getElementById('minimapSvg');
  if (!svg) return;
  const layout = window.__minimapLayout;
  if (!layout) return;
  // 1. 删旧蓝框
  const old = svg.querySelector('.minimap-viewport-box');
  if (old) old.remove();
  // 2. 算 main view 的可视区 (in 缩略图坐标)
  // main view 显示的是 [offsetX, offsetX + containerW/scale] 这个范围
  // 蓝框 x = offsetX, 宽 = containerW / scale
  const fitScale = Math.min(
    (svg.clientWidth - 2) / layout.totalW,
    (svg.clientHeight - 2) / layout.totalH
  );
  if (fitScale <= 0) return;
  // 缩略图是用 viewBox 渲染, fit-to-width 缩放在 viewBox 内
  // 蓝框直接画在 layout 坐标 (用同一 fitScale 通过 viewBox 缩放)
  const boxX = vs.offsetX;
  const boxY = vs.offsetY;
  const boxW = Math.max(20, vs.containerW / vs.scale);
  const boxH = Math.max(20, vs.containerH / vs.scale);
  const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  rect.setAttribute('x', boxX);
  rect.setAttribute('y', boxY);
  rect.setAttribute('width', boxW);
  rect.setAttribute('height', boxH);
  rect.setAttribute('class', 'minimap-viewport-box');
  // 蓝框放在最上层 (links + nodes 之后)
  svg.appendChild(rect);
}

// 订阅 viewport
subscribeViewport(renderViewportBox);
```

- [ ] **Step 2: Verify blue box appears + moves on main view pan (Playwright)**
```javascript
const { chromium } = require('C:\\Users\rainc\\AppData\\Roaming\\npm\\node_modules\\playwright');
(async () => {
  const b = await chromium.launch({ headless: true });
  const p = await b.newPage();
  const errs = [];
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));
  p.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
  await p.goto('http://127.0.0.1:28081/original-tree', { waitUntil: 'networkidle' });
  // 1. 初始蓝框存在
  const initial = await p.evaluate(() => {
    const box = document.querySelector('.minimap-viewport-box');
    return box ? { x: box.getAttribute('x'), y: box.getAttribute('y'), w: box.getAttribute('width'), h: box.getAttribute('height') } : null;
  });
  console.log('initial box:', JSON.stringify(initial));
  // 2. 模拟主视图 pan (用 mouse 拖动 treeCanvas)
  await p.mouse.move(500, 400);
  await p.mouse.down({ button: 'right' });
  await p.mouse.move(700, 400, { steps: 10 });
  await p.mouse.up({ button: 'right' });
  await p.waitForTimeout(300);
  // 3. 蓝框位置应该变
  const afterPan = await p.evaluate(() => {
    const box = document.querySelector('.minimap-viewport-box');
    return box ? { x: box.getAttribute('x'), y: box.getAttribute('y'), w: box.getAttribute('width'), h: box.getAttribute('height') } : null;
  });
  console.log('after pan box:', JSON.stringify(afterPan));
  console.log('errs:', errs);
  await b.close();
})();
```
Expected: `initial box: {x: "32", y: "32", w: "<number>", h: "<number>"}` and `after pan box: {x: "<different number>", ...}`. Box should move on pan.

- [ ] **Step 3: Commit**
```python
import subprocess
from pathlib import Path
msg = """feat(tree): 缩略图蓝框 viewport 指示器

- renderViewportBox(vs): 删旧 + 重画 (避免 SVG 累积)
- 蓝框 x/y/width/height 从 viewportState.offsetX/Y + containerW/H/scale 算
- 蓝框最小 20x20 (避免 main view 缩太远时看不见)
- subscribeViewport 订阅, 主视图 pan/zoom 触发同步跟

Task 6 of 9.
"""
p = Path(r"C:\Users\rainc\AppData\Local\Temp\commit_t6.txt")
p.write_bytes(msg.encode("utf-8"))
subprocess.run(["git", "add", "static/original_tree.html"], cwd=r"D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-minimap", check=True)
subprocess.run(["git", "commit", "-F", str(p)], cwd=r"D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-minimap", check=True)
```

---

## Task 7: Click + hover + drag handlers on minimap

**Files:**
- Modify: `static/original_tree.html` (JS only)

- [ ] **Step 1: Add tooltip element + click/hover/drag handlers**

Append to the bottom of the script in `static/original_tree.html`:

```javascript
// ★ 2026-08-04: minimap 交互 (hover tooltip + click pan + drag fast-pan)
let minimapTooltip = null;

function ensureTooltip() {
  if (minimapTooltip) return minimapTooltip;
  minimapTooltip = document.createElement('div');
  minimapTooltip.className = 'minimap-tooltip';
  minimapTooltip.id = 'minimapTooltip';
  document.getElementById('minimapPanel').appendChild(minimapTooltip);
  return minimapTooltip;
}

function bindMinimapInteractions() {
  const svg = document.getElementById('minimapSvg');
  if (!svg) return;
  const tooltip = ensureTooltip();

  // Hover: 高亮 + tooltip
  svg.addEventListener('mousemove', (e) => {
    const target = e.target;
    if (target.classList && target.classList.contains('minimap-node')) {
      const name = target.getAttribute('data-name') || '(无名)';
      const distId = target.getAttribute('data-dist-id') || '';
      const level = target.getAttribute('data-level') || '';
      const biz = target.getAttribute('data-business-level') || '';
      tooltip.innerHTML = `<b>${escapeHtml(name)}</b> · L${level} · ${biz}<br><span style="opacity:0.7">${escapeHtml(distId)}</span>`;
      tooltip.classList.add('visible');
      // 定位 (panel 相对坐标)
      const panel = document.getElementById('minimapPanel');
      const panelRect = panel.getBoundingClientRect();
      tooltip.style.left = (e.clientX - panelRect.left + 12) + 'px';
      tooltip.style.top = (e.clientY - panelRect.top + 12) + 'px';
    } else {
      tooltip.classList.remove('visible');
    }
  });
  svg.addEventListener('mouseleave', () => tooltip.classList.remove('visible'));

  // Click 节点: 主视图 pan 居中 + select
  svg.addEventListener('click', (e) => {
    const target = e.target;
    if (target.classList && target.classList.contains('minimap-node')) {
      const distId = target.getAttribute('data-dist-id');
      panMainViewToNode(distId);
    }
  });

  // Drag 背景: 主视图快速 pan (Figma style)
  let isDragging = false;
  let dragStartX = 0, dragStartY = 0;
  let panStartX = 0, panStartY = 0;
  svg.addEventListener('mousedown', (e) => {
    if (e.target.classList && e.target.classList.contains('minimap-node')) return;
    if (e.button !== 0) return;  // 只左键
    isDragging = true;
    dragStartX = e.clientX;
    dragStartY = e.clientY;
    panStartX = state.panX;
    panStartY = state.panY;
    e.preventDefault();
  });
  document.addEventListener('mousemove', (e) => {
    if (!isDragging) return;
    const layout = window.__minimapLayout;
    if (!layout) return;
    // 缩略图 → 主视图 缩放比
    const fitScale = Math.min(
      (svg.clientWidth - 2) / layout.totalW,
      (svg.clientHeight - 2) / layout.totalH
    );
    const dx = (e.clientX - dragStartX) / fitScale;
    const dy = (e.clientY - dragStartY) / fitScale;
    state.panX = panStartX - dx;
    state.panY = panStartY - dy;
    applyTransform();
  });
  document.addEventListener('mouseup', () => { isDragging = false; });
}

// 主视图 pan 到指定节点
function panMainViewToNode(distId) {
  if (!distId) return;
  // 1. 找到主视图 DOM 节点
  const mainNode = document.querySelector(`.tree-node-body[data-dist-id="${distId}"]`);
  if (!mainNode) {
    console.warn('[panToNode] not found in main view:', distId);
    return;
  }
  // 2. 算节点在主视图的绝对位置 (从 main view 内 layer 取)
  // tree-node-body 是 absolute 在 treeCanvas 内
  const nodeRect = mainNode.getBoundingClientRect();
  const canvasRect = document.getElementById('treeCanvas').getBoundingClientRect();
  // 节点相对 canvas 中心点
  const nodeCenterX = nodeRect.left + nodeRect.width / 2 - canvasRect.left;
  const nodeCenterY = nodeRect.top + nodeRect.height / 2 - canvasRect.top;
  // 3. 算 pan: 让节点居中
  // applyTransform: translate(state.panX, state.panY) scale(state.zoom)
  // 节点视觉位置 = node.naturalX * zoom + pan
  // 想要 nodeCenterX = canvasW / 2, 解 panX = canvasW/2 - naturalX * zoom
  const zoom = state.zoom;
  const naturalX = (nodeCenterX - state.panX) / zoom;
  const naturalY = (nodeCenterY - state.panY) / zoom;
  state.panX = canvasRect.width / 2 - naturalX * zoom;
  state.panY = canvasRect.height / 2 - naturalY * zoom;
  applyTransform();
  // 4. 选中节点 (高亮)
  document.querySelectorAll('.tree-node-body.selected').forEach(el => el.classList.remove('selected'));
  mainNode.classList.add('selected');
  mainNode.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

// 渲染完成后绑定
bindMinimapInteractions();
```

- [ ] **Step 2: Verify click navigates main view to clicked node (Playwright)**

The minimap node's `data-dist-id` is the same as the main view's `tree-node-body` data-dist-id. First, ensure the main view node has `data-dist-id`. Find `function renderNode` in `static/original_tree.html` (around line 505). Inside the function, after `body.className = ...` add:

```javascript
    if (node.distId) body.setAttribute('data-dist-id', node.distId);
```

Now run the Playwright check:
```javascript
const { chromium } = require('C:\\Users\rainc\\AppData\\Roaming\\npm\\node_modules\\playwright');
(async () => {
  const b = await chromium.launch({ headless: true });
  const p = await b.newPage();
  const errs = [];
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));
  p.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
  await p.goto('http://127.0.0.1:28081/original-tree', { waitUntil: 'networkidle' });
  // 1. 拿一个 minimap 节点的 distId
  const distId = await p.evaluate(() => {
    const node = document.querySelector('.minimap-node');
    return node?.getAttribute('data-dist-id');
  });
  console.log('clicking distId:', distId);
  // 2. 点击这个 minimap 节点
  await p.evaluate((id) => {
    const node = document.querySelector(`.minimap-node[data-dist-id="${id}"]`);
    node?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  }, distId);
  await p.waitForTimeout(500);
  // 3. 主视图应该有 .selected 的对应节点
  const selected = await p.evaluate((id) => {
    const main = document.querySelector(`.tree-node-body.selected[data-dist-id="${id}"]`);
    return !!main;
  }, distId);
  console.log('main view selected:', selected);
  console.log('errs:', errs);
  await b.close();
})();
```
Expected: `main view selected: true`, `errs: []`.

- [ ] **Step 3: Commit**
```python
import subprocess
from pathlib import Path
msg = """feat(tree): minimap hover/click/drag 交互

- hover: 节点高亮 + tooltip (name / L{N} / businessLevel / distId)
- click 节点: panMainViewToNode(distId) → 主视图居中 + .selected 高亮 + scrollIntoView
- drag 背景: 主视图快速 pan (Figma 风格, 缩略图→主视图 fitScale 换算)
- 主视图 renderNode 加 data-dist-id 属性 (供 click 查找)

Task 7 of 9.
"""
p = Path(r"C:\Users\rainc\AppData\Local\Temp\commit_t7.txt")
p.write_bytes(msg.encode("utf-8"))
subprocess.run(["git", "add", "static/original_tree.html"], cwd=r"D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-minimap", check=True)
subprocess.run(["git", "commit", "-F", str(p)], cwd=r"D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-minimap", check=True)
```

---

## Task 8: Error handling + degradation

**Files:**
- Modify: `static/original_tree.html` (JS only)

- [ ] **Step 1: Add error handling in `renderMinimap` and `renderViewportBox`**

Find `function renderMinimap()` in `static/original_tree.html` (added in Task 5). Replace the entire function with the version below that includes error handling:

```javascript
const MINIMAP_DEGRADE_THRESHOLD = 500;

function renderMinimap() {
  if (!state.data) return;
  const svg = document.getElementById('minimapSvg');
  if (!svg) return;
  let layout;
  try {
    layout = minimapLayout(state.data);
  } catch (e) {
    console.warn('[minimap] layout failed:', e);
    const panel = document.getElementById('minimapPanel');
    if (panel) {
      const container = document.getElementById('minimapSvgContainer');
      if (container) container.innerHTML = '<div class="minimap-error">缩略图加载失败</div>';
    }
    return;
  }
  // 1. fit-to-width 缩放
  const container = document.getElementById('minimapSvgContainer');
  if (!container) return;
  const containerW = container.offsetWidth;
  const containerH = container.offsetHeight;
  if (containerW <= 0 || containerH <= 0) {
    // 容器还没 layout, 延迟一帧
    requestAnimationFrame(renderMinimap);
    return;
  }
  const fitScale = Math.min(
    (containerW - 2) / layout.totalW,
    (containerH - 2) / layout.totalH
  );
  // 2. 降级 (>500 节点 → 2x2 像素点, 无链接)
  const degraded = layout.nodes.length > MINIMAP_DEGRADE_THRESHOLD;
  // 3. 渲染
  svg.innerHTML = '';
  svg.setAttribute('viewBox', `0 0 ${layout.totalW} ${layout.totalH}`);
  svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
  if (!degraded) {
    for (const link of layout.links) {
      const cx = (link.from.x + link.from.w / 2);
      const cy = (link.from.y + link.from.h);
      const tx = (link.to.x + link.to.w / 2);
      const ty = link.to.y;
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      const mx = (cx + tx) / 2;
      path.setAttribute('d', `M ${cx} ${cy} C ${cx} ${mx}, ${tx} ${mx}, ${tx} ${ty}`);
      path.setAttribute('fill', 'none');
      path.setAttribute('stroke', '#94A3B8');
      path.setAttribute('stroke-width', '0.5');
      path.setAttribute('opacity', '0.3');
      svg.appendChild(path);
    }
  }
  const BUSINESS_COLOR = {
    ULTIMATE: '#F0C239',
    ELITE: '#5AA4AE',
    BUSINESS: '#10B981',
    MEMBER: '#94A3B8',
  };
  for (const node of layout.nodes) {
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('x', node.x);
    rect.setAttribute('y', node.y);
    rect.setAttribute('width', degraded ? 2 : node.w);
    rect.setAttribute('height', degraded ? 2 : node.h);
    const lvl = (node.n.businessLevel || 'MEMBER').toUpperCase();
    rect.setAttribute('fill', BUSINESS_COLOR[lvl] || BUSINESS_COLOR.MEMBER);
    rect.setAttribute('class', 'minimap-node');
    rect.setAttribute('data-dist-id', node.n.distId || '');
    rect.setAttribute('data-name', node.n.name || '');
    rect.setAttribute('data-level', node.depth + 1);
    rect.setAttribute('data-business-level', lvl);
    if (degraded) {
      rect.style.cursor = 'default';
    }
    svg.appendChild(rect);
  }
  const stats = document.getElementById('minimapStats');
  if (stats) {
    stats.textContent = degraded
      ? `${layout.nodes.length} 节点 (已降级)`
      : `${layout.nodes.length} 节点 / ${layout.maxDepth + 1} 层`;
  }
  window.__minimapLayout = layout;
  emitViewport();
}
```

Also find `function renderViewportBox(vs)` (Task 6) and wrap with try/catch:

```javascript
function renderViewportBox(vs) {
  try {
    const svg = document.getElementById('minimapSvg');
    if (!svg) return;
    const layout = window.__minimapLayout;
    if (!layout) return;
    const old = svg.querySelector('.minimap-viewport-box');
    if (old) old.remove();
    const fitScale = Math.min(
      (svg.clientWidth - 2) / layout.totalW,
      (svg.clientHeight - 2) / layout.totalH
    );
    if (fitScale <= 0) return;
    const boxX = vs.offsetX;
    const boxY = vs.offsetY;
    const boxW = Math.max(20, vs.containerW / vs.scale);
    const boxH = Math.max(20, vs.containerH / vs.scale);
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('x', boxX);
    rect.setAttribute('y', boxY);
    rect.setAttribute('width', boxW);
    rect.setAttribute('height', boxH);
    rect.setAttribute('class', 'minimap-viewport-box');
    svg.appendChild(rect);
  } catch (e) {
    console.warn('[viewport box] render failed:', e);
  }
}
```

- [ ] **Step 2: Add ResizeObserver to re-render minimap on panel resize**

Find `bindMinimapInteractions()` (Task 7) and add at the end of the function (before the final `}`):

```javascript
  // Resize observer
  const ro = new ResizeObserver(() => {
    requestAnimationFrame(renderMinimap);
  });
  ro.observe(document.getElementById('minimapSvgContainer'));
```

- [ ] **Step 3: Verify error handling + degradation doesn't break normal flow (Playwright)**

Normal flow should still work. Verify the same checks from Task 5/6/7 still pass with the error handling added.

```javascript
const { chromium } = require('C:\\Users\rainc\\AppData\\Roaming\\npm\\node_modules\\playwright');
(async () => {
  const b = await chromium.launch({ headless: true });
  const p = await b.newPage();
  const errs = [];
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));
  p.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
  await p.goto('http://127.0.0.1:28081/original-tree', { waitUntil: 'networkidle' });
  const stats = await p.evaluate(() => ({
    rectCount: document.querySelectorAll('.minimap-node').length,
    boxExists: !!document.querySelector('.minimap-viewport-box'),
    statsText: document.getElementById('minimapStats')?.textContent,
  }));
  console.log('stats:', JSON.stringify(stats));
  console.log('errs:', errs);
  await b.close();
})();
```
Expected: `stats: {"rectCount":303,"boxExists":true,"statsText":"303 节点 / 13 层"}`, `errs: []`.

- [ ] **Step 4: Commit**
```python
import subprocess
from pathlib import Path
msg = """feat(tree): minimap 错误处理 + 降级 + ResizeObserver

- renderMinimap wrap try/catch, 失败显示 "缩略图加载失败" 占位
- 容器未 layout (W=0/H=0) → requestAnimationFrame 延迟重试
- > 500 节点 → 降级: 2x2 像素点, 无链接, stats 显示 "(已降级)"
- renderViewportBox wrap try/catch, 不影响主视图
- ResizeObserver 监听 panel resize → 重渲染

Task 8 of 9.
"""
p = Path(r"C:\Users\rainc\AppData\Local\Temp\commit_t8.txt")
p.write_bytes(msg.encode("utf-8"))
subprocess.run(["git", "add", "static/original_tree.html"], cwd=r"D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-minimap", check=True)
subprocess.run(["git", "commit", "-F", str(p)], cwd=r"D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-minimap", check=True)
```

---

## Task 9: Playwright e2e test + push PR

**Files:**
- Create: `tests/test_original_tree_minimap.py`
- Modify: (no other files)

- [ ] **Step 1: Write the e2e test**

Create `tests/test_original_tree_minimap.py`:

```python
"""End-to-end test for /original-tree minimap feature.

Verifies:
- Layout: main view 70% / minimap 30%
- Minimap renders 303 node rects + 302 paths
- Viewport blue box exists and follows main view pan
- Click minimap node → main view scrolls to that node + .selected
- 0 JS console errors throughout
"""
import sys
import subprocess
from pathlib import Path
import urllib.request

# Playwright Python: requires `pip install playwright && playwright install chromium`
# AGENTS.md §4.2: Node playwright is the project's standard. This test uses Node.
# If the project adopts Python playwright later, port to pytest.

NODE_SCRIPT = r"""
const { chromium } = require('C:\\Users\\rainc\\AppData\\Roaming\\npm\\node_modules\\playwright');
(async () => {
  const b = await chromium.launch({ headless: true });
  const p = await b.newPage();
  const errs = [];
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));
  p.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
  await p.goto('http://127.0.0.1:28081/original-tree', { waitUntil: 'networkidle' });

  // 1. Layout
  const layout = await p.evaluate(() => {
    const main = document.querySelector('.main-view-panel');
    const mini = document.getElementById('minimapPanel');
    const total = main.parentElement.offsetWidth;
    return {
      mainPct: ((main.offsetWidth / total) * 100).toFixed(1),
      miniPct: ((mini.offsetWidth / total) * 100).toFixed(1),
    };
  });
  if (layout.mainPct !== '70.0' || layout.miniPct !== '30.0') {
    throw new Error('layout wrong: ' + JSON.stringify(layout));
  }

  // 2. Minimap renders 303 nodes
  const minimap = await p.evaluate(() => ({
    rectCount: document.querySelectorAll('.minimap-node').length,
    pathCount: document.querySelectorAll('#minimapSvg path').length,
    stats: document.getElementById('minimapStats')?.textContent,
  }));
  if (minimap.rectCount !== 303) throw new Error('rect count: ' + minimap.rectCount);
  if (minimap.pathCount !== 302) throw new Error('path count: ' + minimap.pathCount);

  // 3. Viewport box exists
  const initialBox = await p.evaluate(() => {
    const box = document.querySelector('.minimap-viewport-box');
    return box ? { x: parseFloat(box.getAttribute('x')), w: parseFloat(box.getAttribute('width')) } : null;
  });
  if (!initialBox) throw new Error('viewport box not found');

  // 4. Pan main view → viewport box should change
  await p.mouse.move(500, 400);
  await p.mouse.down({ button: 'right' });
  await p.mouse.move(800, 400, { steps: 10 });
  await p.mouse.up({ button: 'right' });
  await p.waitForTimeout(300);
  const afterPanBox = await p.evaluate(() => {
    const box = document.querySelector('.minimap-viewport-box');
    return box ? { x: parseFloat(box.getAttribute('x')), w: parseFloat(box.getAttribute('width')) } : null;
  });
  if (!afterPanBox || Math.abs(afterPanBox.x - initialBox.x) < 1) {
    throw new Error('viewport box did not move on pan: ' + JSON.stringify({ initialBox, afterPanBox }));
  }

  // 5. Click minimap node → main view .selected
  const distId = await p.evaluate(() => {
    const node = document.querySelector('.minimap-node');
    return node?.getAttribute('data-dist-id');
  });
  await p.evaluate((id) => {
    const node = document.querySelector(`.minimap-node[data-dist-id="${id}"]`);
    node?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  }, distId);
  await p.waitForTimeout(500);
  const selected = await p.evaluate((id) => {
    return !!document.querySelector(`.tree-node-body.selected[data-dist-id="${id}"]`);
  }, distId);
  if (!selected) throw new Error('main view not selected after click');

  // 6. 0 JS errors
  if (errs.length > 0) throw new Error('JS errors: ' + errs.join('\n'));

  console.log('OK: all minimap e2e checks passed');
  console.log('layout:', JSON.stringify(layout));
  console.log('minimap:', JSON.stringify(minimap));
  console.log('box before/after pan:', JSON.stringify({ initialBox, afterPanBox }));
  console.log('clicked distId:', distId);
  await p.screenshot({ path: 'C:\\Users\\rainc\\AppData\\Local\\Temp\\minimap_e2e.png', fullPage: true });
  await b.close();
})().catch(e => { console.error('FAIL:', e.message); process.exit(1); });
"""

JS_PATH = r"C:\Users\rainc\AppData\Local\Temp\test_minimap_e2e.js"
Path(JS_PATH).write_bytes(NODE_SCRIPT.encode("utf-8"))

result = subprocess.run(
    ["node", JS_PATH],
    capture_output=True, text=True, timeout=60,
)
print("STDOUT:", result.stdout)
if result.returncode != 0:
    print("STDERR:", result.stderr)
    sys.exit(1)
```

- [ ] **Step 2: Run the test**

```powershell
cd D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-minimap
python tests\test_original_tree_minimap.py
```

Expected output:
```
STDOUT: OK: all minimap e2e checks passed
layout: {"mainPct":"70.0","miniPct":"30.0"}
minimap: {"rectCount":303,"pathCount":302,"stats":"303 节点 / 13 层"}
box before/after pan: {"initialBox":{"x":32,"w":<number>},"afterPanBox":{"x":<different>,"w":<number>}}
clicked distId: A8066781.1
```

If the test fails, do NOT proceed — debug the failing check (the `errs` array in the Node script will tell you which console.error fired).

- [ ] **Step 3: Manual smoke test**

Open `http://127.0.0.1:28081/original-tree` in a browser. Verify:
- Minimap on the right shows 303 small colored rects
- Main view on the left unchanged
- Pan/zoom the main view → blue box in minimap follows
- Click a minimap node → main view jumps to that node
- Hover a minimap node → tooltip with name / level / distId appears
- Drag the empty space in minimap → main view pans

- [ ] **Step 4: Stop worktree server, commit test, push, PR**
```powershell
# 1. Stop 28081
Get-NetTCPConnection -LocalPort 28081 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
# 2. Commit test
git add tests/test_original_tree_minimap.py
git commit -F C:\Users\rainc\AppData\Local\Temp\commit_t9.txt
# 3. Push
git push origin feat-original-tree-minimap
# 4. PR
gh pr create --base main --head feat-original-tree-minimap `
  --title "feat(tree): 原版网体加右侧 30% minimap" `
  --body-file C:\Users\rainc\AppData\Local\Temp\pr_body_t9.md
```

Where `commit_t9.txt` is:
```python
import subprocess
from pathlib import Path
msg = """test(tree): minimap e2e Playwright 测试 + 截图

- tests/test_original_tree_minimap.py: 6 项检查
  1. 布局 70%/30%
  2. 303 节点 + 302 链接
  3. 蓝框初始存在
  4. 主视图 pan → 蓝框跟
  5. 缩略图 click → 主视图 .selected
  6. 0 JS 错误
- 截图保存 C:\\Users\\rainc\\AppData\\Local\\Temp\\minimap_e2e.png

Task 9 of 9 (最终验证 + push PR).
"""
p = Path(r"C:\Users\rainc\AppData\Local\Temp\commit_t9.txt")
p.write_bytes(msg.encode("utf-8"))
subprocess.run(["git", "add", "tests/test_original_tree_minimap.py"], cwd=r"D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-minimap", check=True)
subprocess.run(["git", "commit", "-F", str(p)], cwd=r"D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-minimap", check=True)
```

Where `pr_body_t9.md` contains:
```markdown
## Summary
- Add right-side fixed minimap (30% width) to `/original-tree` page
- Renders the full 303-node tree with viewport blue box that follows main view pan/zoom
- Click/hover/drag interactions: click node → main view centers, hover → tooltip, drag → fast-pan

## Changes
- `static/original_tree.html`: flex layout, viewport state + emit hook, BFS layout algorithm, render function, viewport box, click/hover/drag handlers, error handling + degradation + ResizeObserver
- `static/original_tree_minimap.css`: panel + node + viewport box + tooltip styles
- `tests/test_original_tree_minimap.py`: 6-check e2e test

## Spec
`docs/superpowers/specs/2026-08-04-original-tree-minimap-design.md`

## Plan
`docs/superpowers/plans/2026-08-04-original-tree-minimap.md`

## Test
- 303 nodes, 302 links, 13 levels
- 0 JS console errors
- Viewport box follows main view pan
- Click minimap → main view navigates

## Out of scope
- 5-叉 9 层 main tree (`/tree` modal)
- Backend / DB / API
```

- [ ] **Step 5: Verify PR created + CI pass**
```powershell
gh pr list --head feat-original-tree-minimap
gh pr view <PR_NUMBER> --json status,url
```
Expected: PR open, URL returned. Wait for CI (if configured) to pass before merge.

---

## Self-Review

**Spec coverage check** (each spec requirement → task mapping):
- §2 Goal: 右侧 minimap → Task 2/5
- §2 Goal: 蓝框同步主视图 → Task 3/6
- §2 Goal: click-to-navigate → Task 7
- §2 Goal: 折叠/展开同步 → Task 6 (viewportState 包含 naturalW/H, 蓝框随之变)
- §5.1 Layout container → Task 2
- §5.2 Minimap SVG → Task 4 (layout) + Task 5 (render)
- §5.3 Viewport indicator → Task 6
- §5.4 Interaction handlers → Task 7
- §5.5 State sync → Task 3
- §6 Data flow → Task 3 (shared state)
- §7 Error handling → Task 8
- §8 Testing → Task 9

All 11 spec requirements covered by 9 tasks.

**Placeholder scan:** No "TBD" / "TODO" / "implement later" / "add appropriate error handling" without code.

**Type consistency:** viewportState, layout, MINIMAP_* constants used consistently across Tasks 3-8.

**File paths:** All exact. No `Path(...)` placeholders.

---

## Execution Handoff

This plan is now complete. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
