"""End-to-end test for /original-tree minimap feature.

Verifies:
- Layout: main view 70% / minimap 30%
- Minimap renders 303 node rects + 302 paths
- Viewport blue box exists and follows main view pan
- Click minimap node → main view scrolls to that node + .selected
- 0 JS console errors throughout

Usage: python tests/test_original_tree_minimap.py
(Requires 28081 server running the worktree code.)
"""
import subprocess
import sys
from pathlib import Path

NODE_SCRIPT = r"""
const { chromium } = require('C:\\Users\\rainc\\AppData\\Roaming\\npm\\node_modules\\playwright');
(async () => {
  const b = await chromium.launch({ headless: true });
  const p = await b.newPage({ viewport: { width: 1280, height: 800 } });
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
    capture_output=True, text=True, timeout=60, encoding='utf-8',
)
print("STDOUT:", result.stdout)
if result.returncode != 0:
    print("STDERR:", result.stderr)
    sys.exit(1)
