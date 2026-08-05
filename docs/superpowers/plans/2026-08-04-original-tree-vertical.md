# Original Tree Vertical Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Convert `/original-tree` to a vertical tree layout (root at top center, children horizontal below) and update the minimap to match.

**Architecture:** Modify CSS to make `.tree-node` flex-column and `.tree-node-children` flex-row with connection lines via `::before`. Swap x/y in the minimap's BFS layout. Recompute `fitToScreen` for the new natural size.

**Tech Stack:** vanilla JS, CSS flex, existing d3-free codebase. Playwright for e2e verification. No backend, DB, or API changes.

**Spec:** `docs/superpowers/specs/2026-08-04-original-tree-vertical.md`

**Worktree:** Implementation MUST run inside a `feat-original-tree-vertical` worktree on the main branch. Copy `.env`, `json/`, and `data/` from main.

---

## File Structure

Files modified by this plan:
- `static/original_tree.html` — CSS (`.tree-node`, `.tree-node-children`, connection lines), `fitToScreen`, `minimapLayout` (x/y swap)
- `tests/test_original_tree_minimap.py` — add root-on-top assertion

No new files, no backend changes.

---

## Task V0: Worktree setup + 38082 server

**Files:**
- Create: `.worktrees/feat-original-tree-vertical/`

- [ ] **Step 1: Create worktree off main**
```powershell
cd D:\Projects\Reward\RewardAgentAnalysis
git worktree add -b feat-original-tree-vertical .worktrees/feat-original-tree-vertical main
```
Expected: worktree created at `D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-vertical`.

- [ ] **Step 2: Copy env + json + data into worktree**
```powershell
Copy-Item .env .worktrees\feat-original-tree-vertical\.env -Force
New-Item -ItemType Directory -Path .worktrees\feat-original-tree-vertical\json -Force
Copy-Item json\original_tree.json .worktrees\feat-original-tree-vertical\json\ -Force
New-Item -ItemType Directory -Path .worktrees\feat-original-tree-vertical\data -Force
Copy-Item data\rewarddb.db .worktrees\feat-original-tree-vertical\data\rewarddb.db
```

- [ ] **Step 3: Start uvicorn on port 38082 in the worktree**
```powershell
cd .worktrees\feat-original-tree-vertical
Start-Process python -ArgumentList "-m uvicorn main:app --port 38082 --log-level info" `
  -WorkingDirectory "$PWD" `
  -RedirectStandardOutput "$env:TEMP\uvicorn_vertical.log" `
  -RedirectStandardError "$env:TEMP\uvicorn_vertical.err.log" `
  -NoNewWindow
Start-Sleep -Seconds 5
```
Verify with `python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:38082/api/original_tree/data', timeout=5).read()[:80])"`.

- [ ] **Step 4: Capture baseline screenshot (still horizontal at this point)**
```javascript
const { chromium } = require('C:\\Users\\rainc\\AppData\\Roaming\\npm\\node_modules\\playwright');
(async () => {
  const b = await chromium.launch({ headless: true });
  const p = await b.newPage({ viewport: { width: 1280, height: 800 } });
  await p.goto('http://127.0.0.1:38082/original-tree', { waitUntil: 'networkidle' });
  await p.screenshot({ path: 'C:\\Users\\rainc\\AppData\\Local\\Temp\\vertical_baseline.png', fullPage: false });
  await b.close();
})();
```

- [ ] **Step 5: Commit worktree init (if anything to commit)**
Skip if worktree is clean.

---

## Task V1: CSS — Vertical tree layout + connection lines

**Files:**
- Modify: `static/original_tree.html` (CSS only — replace `.tree-node` and `.tree-node-children` rules; add new rules for connection lines)

- [ ] **Step 1: Replace `.tree-node` CSS rule**

Find (around line 163):
```css
  .tree-node {
    display: flex;
    align-items: stretch;
    margin: 4px 0;
    padding-left: 0;
  }
```

Replace with:
```css
  .tree-node {
    display: flex;
    flex-direction: column;
    align-items: center;
    margin: 0;
    padding: 0;
    position: relative;
  }
```

- [ ] **Step 2: Replace `.tree-node-children` CSS rule**

Find (around line 170):
```css
  .tree-node-children {
    margin-left: 32px;
    padding-left: 16px;
    border-left: 1px dashed var(--border);
  }
```

Replace with:
```css
  .tree-node-children {
    display: flex;
    justify-content: center;
    gap: 24px;
    margin-top: 32px;
    padding: 0;
    position: relative;
  }
  /* 父到子节点的连接线 */
  .tree-node-children::before {
    content: '';
    position: absolute;
    top: -32px;
    left: 0;
    right: 0;
    height: 1px;
    background: var(--border, #D6ECF0);
  }
  .tree-node-children > .tree-node {
    position: relative;
  }
  .tree-node-children > .tree-node::before {
    content: '';
    position: absolute;
    top: -32px;
    left: 50%;
    width: 1px;
    height: 32px;
    background: var(--border, #D6ECF0);
    transform: translateX(-50%);
  }
  /* 单子节点: 隐藏水平 trunk (只画垂直线) */
  .tree-node-children > .tree-node:only-child::before {
    /* 仍然画垂直线 — 仅当 sibling 有 trunk 时才隐藏 trunk (不在 CSS 实现, 接受 trunk 显示) */
  }
```

Note: The horizontal trunk is always shown even for single-child subtrees. This is visually slightly redundant but keeps the CSS simple. If a single-child parent should hide the trunk, add JS: `if (only one child) remove the ::before`. For this task, accept the minor visual redundancy.

- [ ] **Step 3: Verify with Playwright (root should be at top, children horizontal below)**

```javascript
const { chromium } = require('C:\\Users\\rainc\\AppData\\Roaming\\npm\\node_modules\\playwright');
(async () => {
  const b = await chromium.launch({ headless: true });
  const p = await b.newPage({ viewport: { width: 1280, height: 800 } });
  const errs = [];
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));
  p.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
  await p.goto('http://127.0.0.1:38082/original-tree', { waitUntil: 'networkidle' });
  const layout = await p.evaluate(() => {
    const root = document.querySelector('.tree-node');
    const rootBody = document.querySelector('.tree-node-body');
    const rootRect = rootBody?.getBoundingClientRect();
    const viewportRect = document.getElementById('viewport')?.getBoundingClientRect();
    if (!rootRect || !viewportRect) return { error: 'no rootBody or viewport' };
    // Root should be in the top half of viewport
    const rootTopPct = ((rootRect.top - viewportRect.top) / viewportRect.height) * 100;
    // Root should be roughly horizontally centered
    const rootCenterX = rootRect.left + rootRect.width / 2;
    const viewportCenterX = viewportRect.left + viewportRect.width / 2;
    const rootOffsetFromCenter = rootCenterX - viewportCenterX;
    // L1 children (4 of them) should be horizontally laid out below root
    const l1Children = document.querySelectorAll('.tree-node > .tree-node-children > .tree-node');
    const l1Rects = Array.from(l1Children).slice(0, 4).map(c => c.getBoundingClientRect());
    const l1YAligned = l1Rects.every(r => Math.abs(r.top - l1Rects[0].top) < 20);
    return {
      rootTopPct: rootTopPct.toFixed(1),
      rootOffsetFromCenter: rootOffsetFromCenter.toFixed(1),
      l1ChildCount: l1Children.length,
      l1YAligned,
    };
  });
  console.log('layout:', JSON.stringify(layout));
  console.log('errs:', errs);
  await p.screenshot({ path: 'C:\\Users\\rainc\\AppData\\Local\\Temp\\vertical_v1.png', fullPage: false });
  await b.close();
})();
```

Expected:
```
layout: {"rootTopPct":"<small>","rootOffsetFromCenter":"<small>","l1ChildCount":4,"l1YAligned":true}
errs: []
```

`rootTopPct` should be small (root near top); `rootOffsetFromCenter` should be near 0 (root centered); `l1YAligned: true` (4 L1 children at same Y).

- [ ] **Step 4: Commit**
```python
import subprocess
from pathlib import Path
msg = """feat(tree): 原版网体 vertical 树 CSS (root 在顶, 子节点水平排)

- .tree-node 改 flex-direction: column + align-items: center
- .tree-node-children 改 flex + justify-content: center + gap 24px
- 加连接线: ::before 在 children 容器上画水平 trunk
  + 每个 child .tree-node::before 画垂直线
- 边距 32px (跟旧 margin-left 一致)

Task V1 of 5 in vertical layout plan.
"""
p = Path(r"C:\Users\rainc\AppData\Local\Temp\commit_v1.txt")
p.write_bytes(msg.encode("utf-8"))
subprocess.run(["git", "add", "static/original_tree.html"], cwd=r"D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-vertical", check=True)
subprocess.run(["git", "commit", "-F", str(p)], cwd=r"D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-vertical", check=True)
```

---

## Task V2: minimapLayout — swap x/y to vertical

**Files:**
- Modify: `static/original_tree.html` (JS — `minimapLayout` function)

- [ ] **Step 1: Locate the existing `minimapLayout` function and its sizing constants**

Find (around line 880-920):
```javascript
  const MINIMAP_NODE_H = 4;
  const MINIMAP_GAP_X = 1;
  const MINIMAP_GAP_Y = 6;
  const MINIMAP_PAD = 8;
```

These constants are for horizontal layout (H=height, GAP_Y=vertical gap between layers). For vertical layout we swap:
- `MINIMAP_NODE_H` → `MINIMAP_NODE_W` (nodes are now width-tall, drawn as horizontal bars)
- New `MINIMAP_NODE_H` (height, smaller because nodes are now bars)
- `MINIMAP_GAP_X` → `MINIMAP_GAP_Y` (vertical gap between siblings, since siblings stack vertically)
- `MINIMAP_GAP_Y` → `MINIMAP_GAP_X` (horizontal gap between depth layers)

Replace the constants block with:
```javascript
  // vertical minimap: 同层竖排, 不同层横排
  const MINIMAP_NODE_W = Math.log2(2) * 8;  // 节点 width (will scale per node in layout)
  const MINIMAP_NODE_H = 4;                  // 节点 height (固定, 横向条带)
  const MINIMAP_GAP_X = 12;                  // 层间距 (水平)
  const MINIMAP_GAP_Y = 1;                   // 兄弟间距 (垂直)
  const MINIMAP_PAD = 8;
```

- [ ] **Step 2: Rewrite the x/y assignment in `minimapLayout`**

In `minimapLayout` (around line 868-873), the assignment block is:
```javascript
  for (let d = 0; d <= maxDepth; d++) {
    let curX = MINIMAP_PAD;
    for (const node of (byDepth[d] || [])) {
      node.x = curX;
      node.y = MINIMAP_PAD + d * (MINIMAP_NODE_H + MINIMAP_GAP_Y);
      curX += node.w + MINIMAP_GAP_X;
    }
  }
```

Replace with the vertical version (siblings stack vertically, depth layers travel horizontally):
```javascript
  for (let d = 0; d <= maxDepth; d++) {
    let curY = MINIMAP_PAD;
    for (const node of (byDepth[d] || [])) {
      node.x = MINIMAP_PAD + d * (80 + MINIMAP_GAP_X);  // 每层 80px 宽
      node.y = curY;
      curY += node.h + MINIMAP_GAP_Y;
    }
  }
```

Note: We give each depth layer a fixed 80px horizontal slot, regardless of how many nodes are in it. This is simpler and more predictable than computing per-layer max widths.

- [ ] **Step 3: Update node width calculation**

In `minimapLayout` (around line 855-857), the width calculation:
```javascript
      const w = Math.max(1, Math.log2(total + 1) * 4);
```

For vertical minimap, nodes are horizontal bars — their width should reflect subtree size. Keep `w` calculation as is. Update node dimensions to be (w, h):
```javascript
      const w = Math.max(1, Math.log2(total + 1) * 4);
      const h = MINIMAP_NODE_H;
      nodes.push({ n, depth, w, h, subtreeTotal: total });
```
(unchanged — just ensure the node dimensions are set so the renderer can draw rectangles)

- [ ] **Step 4: Verify with Playwright (minimap nodes still 303, positions different)**
```javascript
const { chromium } = require('C:\\Users\rainc\\AppData\\Roaming\\npm\\node_modules\\playwright');
(async () => {
  const b = await chromium.launch({ headless: true });
  const p = await b.newPage({ viewport: { width: 1280, height: 800 } });
  const errs = [];
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));
  p.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
  await p.goto('http://127.0.0.1:38082/original-tree', { waitUntil: 'networkidle' });
  const minimap = await p.evaluate(() => ({
    rectCount: document.querySelectorAll('.minimap-node').length,
    pathCount: document.querySelectorAll('#minimapSvg path').length,
    boxExists: !!document.querySelector('.minimap-viewport-box'),
  }));
  console.log('minimap:', JSON.stringify(minimap));
  console.log('errs:', errs);
  await p.screenshot({ path: 'C:\\Users\\rainc\\AppData\\Local\\Temp\\vertical_v2.png', fullPage: false });
  await b.close();
})();
```
Expected: `minimap: {"rectCount":303,"pathCount":302,"boxExists":true}`, `errs: []`.

- [ ] **Step 5: Commit**
```python
import subprocess
from pathlib import Path
msg = """feat(tree): minimap BFS 改 vertical (sibling 竖排, depth 横排)

- MINIMAP_NODE_H 改 4 (横向条带 height)
- 兄弟 y 累加 (curY)
- 层 x = depth * (80 + GAP)
- node.x/y swap 跟 PR #13 minimapLayout 兼容

Task V2 of 5.
"""
p = Path(r"C:\Users\rainc\AppData\Local\Temp\commit_v2.txt")
p.write_bytes(msg.encode("utf-8"))
subprocess.run(["git", "add", "static/original_tree.html"], cwd=r"D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-vertical", check=True)
subprocess.run(["git", "commit", "-F", str(p)], cwd=r"D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-vertical", check=True)
```

---

## Task V3: fitToScreen — recompute for vertical layout

**Files:**
- Modify: `static/original_tree.html` (JS — `fitToScreen` function)

- [ ] **Step 1: Locate `fitToScreen`**

Find (search for `function fitToScreen`):
```javascript
  function fitToScreen() {
    const c = document.getElementById('treeContainer');
    const vp = document.getElementById('viewport');
    if (!c || !vp) return;
    const cw = vp.clientWidth;
    const ch = vp.clientHeight;
    const nw = c.offsetWidth;
    const nh = c.offsetHeight;
    const scale = Math.min(cw / nw, ch / nh) * 0.95;
    state.zoom = scale;
    state.panX = (cw - nw * scale) / 2;
    state.panY = 32;
    applyTransform();
  }
```

(If the existing implementation is slightly different, only the `state.panX` and `state.panY` logic needs adjustment — the rest of the formula works for any layout.)

- [ ] **Step 2: Adjust panY for vertical layout**

For the vertical layout, root should sit at the very top of the viewport, not centered. Change `state.panY` from `(ch - nh * scale) / 2` (centered) to `32` (small top margin).

Replace `state.panY` assignment:
```javascript
    state.panY = 32;
```

(Already done in the snippet above. If existing code is different, set panY = 32.)

- [ ] **Step 3: Verify root is at top after reload**

Re-run the Playwright check from Task V1 Step 3. The `rootTopPct` should now be small (root near top of viewport).

- [ ] **Step 4: Commit**
```python
import subprocess
from pathlib import Path
msg = """feat(tree): fitToScreen 改 root 在顶 (panY = 32 而非居中)

- state.panY = 32 (top margin)
- state.panX 保持居中 ((cw - nw * scale) / 2)
- 业务效果: root 固定在 viewport 顶部, 树往下展开

Task V3 of 5.
"""
p = Path(r"C:\Users\rainc\AppData\Local\Temp\commit_v3.txt")
p.write_bytes(msg.encode("utf-8"))
subprocess.run(["git", "add", "static/original_tree.html"], cwd=r"D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-vertical", check=True)
subprocess.run(["git", "commit", "-F", str(p)], cwd=r"D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-vertical", check=True)
```

---

## Task V4: Verify minimap viewport box (no formula change, just re-verify)

**Files:**
- Modify: (none — just re-verify Task 6 from PR #13 still works)

- [ ] **Step 1: Re-run the PR #13 e2e test against the worktree port**

Modify the test temporarily to point at port 38082 (or duplicate the test):
```javascript
const { chromium } = require('C:\\Users\\rainc\\AppData\\Roaming\\npm\\node_modules\\playwright');
(async () => {
  const b = await chromium.launch({ headless: true });
  const p = await b.newPage({ viewport: { width: 1280, height: 800 } });
  const errs = [];
  p.on('pageerror', e => errs.push('pageerror: ' + e.message));
  p.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
  await p.goto('http://127.0.0.1:38082/original-tree', { waitUntil: 'networkidle' });

  // 1. Layout
  const layout = await p.evaluate(() => {
    const main = document.querySelector('.main-view-panel');
    const mini = document.getElementById('minimapPanel');
    return {
      mainPct: ((main.offsetWidth / main.parentElement.offsetWidth) * 100).toFixed(1),
      miniPct: ((mini.offsetWidth / mini.parentElement.offsetWidth) * 100).toFixed(1),
    };
  });
  if (layout.mainPct !== '70.0' || layout.miniPct !== '30.0') {
    throw new Error('layout wrong: ' + JSON.stringify(layout));
  }

  // 2. Minimap renders 303 nodes
  const minimap = await p.evaluate(() => ({
    rectCount: document.querySelectorAll('.minimap-node').length,
    pathCount: document.querySelectorAll('#minimapSvg path').length,
    boxExists: !!document.querySelector('.minimap-viewport-box'),
  }));
  if (minimap.rectCount !== 303 || minimap.pathCount !== 302) {
    throw new Error('minimap counts wrong: ' + JSON.stringify(minimap));
  }
  if (!minimap.boxExists) throw new Error('viewport box not found');

  // 3. NEW: root on top
  const rootPos = await p.evaluate(() => {
    const rootBody = document.querySelector('.tree-node-body');
    const viewport = document.getElementById('viewport');
    if (!rootBody || !viewport) return null;
    const rootRect = rootBody.getBoundingClientRect();
    const vpRect = viewport.getBoundingClientRect();
    const rootTopPct = ((rootRect.top - vpRect.top) / vpRect.height) * 100;
    const rootOffsetX = (rootRect.left + rootRect.width / 2) - (vpRect.left + vpRect.width / 2);
    return { rootTopPct, rootOffsetX };
  });
  if (!rootPos) throw new Error('root not found');
  if (rootPos.rootTopPct > 30) {
    throw new Error('root not at top: ' + JSON.stringify(rootPos));
  }
  if (Math.abs(rootPos.rootOffsetX) > 50) {
    throw new Error('root not centered: ' + JSON.stringify(rootPos));
  }

  // 4. Pan → viewport box moves
  await p.mouse.move(500, 400);
  await p.mouse.down({ button: 'right' });
  await p.mouse.move(800, 400, { steps: 10 });
  await p.mouse.up({ button: 'right' });
  await p.waitForTimeout(300);
  const initialBox = await p.evaluate(() => {
    const box = document.querySelector('.minimap-viewport-box');
    return box ? { x: parseFloat(box.getAttribute('x')) } : null;
  });
  const afterBox = await p.evaluate(() => {
    const box = document.querySelector('.minimap-viewport-box');
    return box ? { x: parseFloat(box.getAttribute('x')) } : null;
  });
  if (!afterBox || Math.abs(afterBox.x - initialBox.x) < 1) {
    throw new Error('viewport box did not move on pan');
  }

  // 5. Click minimap → main view selected
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

  if (errs.length > 0) throw new Error('JS errors: ' + errs.join('\n'));

  console.log('OK: all vertical layout e2e checks passed');
  console.log('root pos:', JSON.stringify(rootPos));
  await p.screenshot({ path: 'C:\\Users\\rainc\\AppData\\Local\\Temp\\vertical_e2e.png', fullPage: false });
  await b.close();
})().catch(e => { console.error('FAIL:', e.message); process.exit(1); });
```

Expected: `OK: all vertical layout e2e checks passed`, `root pos: {"rootTopPct":<small>,"rootOffsetX":<small>}`.

- [ ] **Step 2: Commit (no code change — just verification)**

If no code change, skip. Otherwise commit the test or the production fix.

---

## Task V5: e2e test + push PR + merge + 38080 restart

**Files:**
- Modify: `tests/test_original_tree_minimap.py` (add root-on-top assertion)

- [ ] **Step 1: Add root-on-top check to the test file**

In `tests/test_original_tree_minimap.py`, after the layout check (step 1 in the test) and before the click check (step 5), add:

```python
  // 3.5. NEW: root on top (vertical layout)
  const rootPos = await p.evaluate(() => {
    const rootBody = document.querySelector('.tree-node-body');
    const vp = document.getElementById('viewport');
    if (!rootBody || !vp) return null;
    const rootRect = rootBody.getBoundingClientRect();
    const vpRect = vp.getBoundingClientRect();
    return {
      rootTopPct: ((rootRect.top - vpRect.top) / vpRect.height) * 100,
      rootOffsetX: (rootRect.left + rootRect.width / 2) - (vpRect.left + vpRect.width / 2),
    };
  });
  if (!rootPos) throw new Error('root not found in main view');
  if (rootPos.rootTopPct > 30) throw new Error('root not at top: ' + JSON.stringify(rootPos));
  if (Math.abs(rootPos.rootOffsetX) > 50) throw new Error('root not centered: ' + JSON.stringify(rootPos));
```

- [ ] **Step 2: Run the e2e test**

```powershell
cd D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-vertical
python tests\test_original_tree_minimap.py
```

Expected: `OK: all minimap e2e checks passed` (existing message; the new check is silent pass).

- [ ] **Step 3: Stop 38082, commit, push, PR**
```powershell
# 1. Stop 38082
Get-NetTCPConnection -LocalPort 38082 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
# 2. Commit test
git add tests/test_original_tree_minimap.py
git commit -F C:\Users\rainc\AppData\Local\Temp\commit_v5.txt
# 3. Push
git push origin feat-original-tree-vertical
# 4. PR
gh pr create --base main --head feat-original-tree-vertical `
  --title "feat(tree): 原版网体改 vertical 布局 (root 在顶)" `
  --body-file C:\Users\rainc\AppData\Local\Temp\pr_body_v5.md
```

Where `commit_v5.txt` is:
```python
import subprocess
from pathlib import Path
msg = """test(tree): minimap e2e 加 root-on-top 验证 (vertical 布局)

- 3.5 步骤: root 应在 viewport 顶部 30% 内
- 3.5 步骤: root 应水平居中 (offset < 50px)
- 业务: 跟主 5 叉 9 层 tree view 视觉一致 (root 在顶)

Task V5 of 5 (最终验证 + push PR).
"""
p = Path(r"C:\Users\rainc\AppData\Local\Temp\commit_v5.txt")
p.write_bytes(msg.encode("utf-8"))
subprocess.run(["git", "add", "tests/test_original_tree_minimap.py"], cwd=r"D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-vertical", check=True)
subprocess.run(["git", "commit", "-F", str(p)], cwd=r"D:\Projects\Reward\RewardAgentAnalysis\.worktrees\feat-original-tree-vertical", check=True)
```

Where `pr_body_v5.md` is:
```markdown
## Summary
原版网体 (`/original-tree`) 改 vertical 树布局, root 在顶, 子节点水平排, 跟主 5 叉 9 层 tree view 视觉一致. minimap 同步改 vertical (sibling 竖排, depth 横排).

## 变更
- `static/original_tree.html`:
  - CSS: `.tree-node` flex-direction: column, `.tree-node-children` flex row + gap 24px, 加 ::before 连接线
  - fitToScreen: panY = 32 (root 在顶)
  - minimapLayout: swap x/y, 兄弟竖排 / 层横排
- `tests/test_original_tree_minimap.py`: 加 root-on-top 验证

## Spec & Plan
- spec: `docs/superpowers/specs/2026-08-04-original-tree-vertical.md`
- plan: `docs/superpowers/plans/2026-08-04-original-tree-vertical.md`

## 测试
- 7 项 Playwright 检查: 布局 / 节点数 / 蓝框 / pan 同步 / click 跳转 / root 在顶 / 0 JS 错误
- 截图: `C:\Users\rainc\AppData\Local\Temp\vertical_e2e.png`
```

- [ ] **Step 4: Verify PR created**
```powershell
gh pr list --head feat-original-tree-vertical
gh pr view <PR_NUMBER> --json status,url
```
Expected: PR open, URL returned.

- [ ] **Step 5: Wait for user to test (don't auto-merge — vertical layout is a UX change)**

After PR is created, the user will test in the browser. If they approve, the next session merges the PR. Do NOT auto-merge in this task.

---

## Self-Review

**Spec coverage check** (each spec requirement → task mapping):
- §2 Goal: vertical tree, root top, children horizontal → Task V1 (CSS) + V2 (minimap) + V3 (fitToScreen)
- §5.1 CSS vertical → Task V1
- §5.2 renderNode → no JS change needed (DOM already correct)
- §5.3 fitToScreen → Task V3
- §5.4 minimapLayout vertical → Task V2
- §5.5 viewport box → Task V4 (verify formula unchanged)
- §6 Data flow → unchanged from PR #13
- §7 Error handling → unchanged
- §8.1 e2e test → Task V4 + V5
- §8.2 Manual verification → done by user

All 8 spec requirements covered by 5 tasks.

**Placeholder scan:** No "TBD" / "TODO" / "implement later".

**Type consistency:** minimapLayout return shape unchanged (`{nodes, links, totalW, totalH, maxDepth}`); only x/y assignments swap.

---

## Execution Handoff

Plan complete and saved. Inline execution proceeds per the user's choice in the previous turn.
