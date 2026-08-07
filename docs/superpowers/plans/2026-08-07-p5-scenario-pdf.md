# P5 商业计划书 PDF 导出 Implementation Plan

**Goal:** 独立 `static/scenario_pdf.html`, 单 scenario 9 页完整版商业计划书 PDF, 实时预览 + 1 键下载 (jsPDF + html2canvas, 0 后端).

**Architecture:** 0 后端改动 (复用 7 个现有 endpoint). 前端独立页面, 9 个 section 容器 + 4 副 Canvas + html2canvas 截图 + jsPDF 拼 9 页 A4.

**Tech Stack:** 复用栈 (Vanilla HTML + CSS + JS, border-beam 纯 CSS) + CDN: jsPDF 2.5 + html2canvas 1.4.

**Spec:** `docs/superpowers/specs/2026-08-07-p5-scenario-pdf-design.md`

---

## File Structure (P5 改动)

| 文件 | 责任 |
|---|---|
| `static/scenario_pdf.html` | 独立页, 9 section 容器 + CDN scripts (~120 行) |
| `static/scenario_pdf.css` | 9 section 排版 + 4 副 canvas + 复 P3 PR1 配色 + border-beam (~200 行) |
| `static/scenario_pdf.js` | 6 段流程: 选 → 拉 → 画 4 canvas → 截图 → 拼 PDF → 下载 (~300 行) |
| `static/index.html` | 主菜单加 "📄 Scenario PDF" 入口 (1 行) |
| `tests/test_scenario_pdf_e2e.py` | Playwright e2e (2 测试: 渲染 + 下载) |
| `AGENTS.md` | §6.9 |

---

## Task 1: spec (DONE)

**Files:**
- Create: `docs/superpowers/specs/2026-08-07-p5-scenario-pdf-design.md`

- [x] **Step 1: 写 spec** (15.6KB, 10 章节, 4 决策拍板)
- [x] **Step 2: Commit** (a9dbba0)

---

## Task 2: scenario_pdf.html + css 基础结构

**Files:**
- Create: `static/scenario_pdf.html`
- Create: `static/scenario_pdf.css`

- [ ] **Step 1: 写 `static/scenario_pdf.html`** (~120 行)

页面骨架:
- 顶部 title "📄 SCENARIO PDF 导出 (商业计划书)"
- 2 栏布局: 左侧栏 (260px) + 右侧 9 section 容器
- 侧栏: scenario 列表 + "📄 生成 PDF" 按钮
- 9 section 容器, 每个 `.pdf-section` class + `data-page` 属性
- 底部 toast
- 头部 CDN: jsPDF + html2canvas

9 section 内容 (按 spec §4):
1. 封面: title + scenario 名 + 日期
2. 执行摘要: 8 报酬卡片 (月 14 累计) + 月均
3. 业务模型图: Canvas 树形 L0-L3 (复 PR1)
4. 参数配置: 4 border-beam (复 PR1)
5-6. 14 月 8 报酬曲线: Canvas 8 subplot 折线 (复 PR3)
7. 14 月 8 报酬热图: Canvas 8×14 (复 PR2)
8. 节点 TOP 5: Canvas 横向条形 + 8 卡片
9. 风险免责 + 签字栏

CDN script:
```html
<script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
```

- [ ] **Step 2: 写 `static/scenario_pdf.css`** (~200 行)

复 P3 PR1 配色:
- bg: `#0a0a14`
- line/region1: `#5AA4AE` (天水碧)
- region2/leaf: `#C0EBD7` (青白)
- region3/highlight: `#F0C239` (缃色)
- region4/text: `#758A99` (墨灰)
- card bg: `#1a1a2e` / `#2a2a3e`

9 section 排版:
- `.pdf-section` { background: #fff; padding: 24px; margin-bottom: 8px; } (PDF 用白底)
- `.pdf-section h2` { color: #5AA4AE; font-size: 18px; margin-bottom: 12px; }
- `.pdf-section .section-content` { font-size: 13px; color: #333; line-height: 1.6; }

侧栏:
- `.pdf-sidebar` { width: 260px; padding: 12px; }
- `.pdf-sidebar-item` { padding: 8px; cursor: pointer; }
- `.pdf-sidebar-item.active` { background: #3a3a4e; border-left: 3px solid #5AA4AE; }

按钮:
- `.btn-generate-pdf` { background: linear-gradient(135deg, #5AA4AE, #C0EBD7); padding: 12px; width: 100%; }

canvas 样式:
- `.pdf-section canvas` { max-width: 100%; height: auto; border: 1px solid #ddd; }

- [ ] **Step 3: 验证 (浏览器加载 `/static/scenario_pdf.html`, 看 2 栏布局 + 9 section 占位)**

- [ ] **Step 4: Commit**

```bash
git add static/scenario_pdf.html static/scenario_pdf.css
git commit -m "feat(scenario-ui): P5 Task 2 — scenario_pdf.html/css 基础结构 (9 section 容器 + 复 PR1 配色 + jsPDF/html2canvas CDN)"
```

---

## Task 3: scenario_pdf.js 6 段流程 (核心)

**Files:**
- Create: `static/scenario_pdf.js`

- [ ] **Step 1: 写 `static/scenario_pdf.js`** (~300 行)

6 段流程:
1. **页面加载** → 调 `GET /api/scenarios` 拉列表, 侧栏渲染
2. **用户点 S1** → 调 3 个端点 (state M14 bfs_id=0 + overview/all M14 + state M14 bfs_id=0/1/2/3/4 TOP 5)
3. **渲染 9 section**:
   - Section 1-2, 4, 9: 文本 (同步, DOM 直接填)
   - Section 3: 树形 Canvas (复 PR1 `drawNode` / `drawLine`)
   - Section 5-6: 14 月 8 折线 Canvas (复 PR3 4 色 + 多 scenario 区分简化)
   - Section 7: 14 月 8 报酬热图 Canvas (复 PR2 业务分色)
   - Section 8: TOP 5 横向条形 Canvas (新增)
4. **用户点 "📄 生成 PDF"**:
   - toast "正在生成第 X/9 页..."
   - for i in 0..9:
     - section = sections[i]
     - canvas = html2canvas(section, {scale: 2, backgroundColor: '#ffffff'})
     - if i > 0: pdf.addPage()
     - imgData = canvas.toDataURL('image/jpeg', 0.95)
     - imgHeight = canvas.height * 210 / canvas.width (mm)
     - pdf.addImage(imgData, 'JPEG', 0, 0, 210, min(imgHeight, 297))
5. **jsPDF doc.save(`scenario_${sid}_${name}_plan_${YYYY-MM-DD}.pdf`)** 触发下载
6. **toast 提示 "✅ PDF 已下载"**

**TOP 5 实现** (业务接受简化版, 跟 spec §6 一致):
- 固定 5 个 bfs_id = [0, 1, 2, 3, 4]
- 循环 5 次 `state?bfs_id=N` 拉每个节点的 8 报酬
- 业务接受 5×60s = 5min, toast 进度 "拉取节点 1/5..."

**复用的工具函数** (从 scenario.js / scenario_compare.js 复制):
- `drawNode` / `drawLine` (树形)
- `formatUSD`
- `showToast`
- 8 报酬业务分色 (COLORS.reward)

**关键函数骨架**:
```javascript
// static/scenario_pdf.js
(function() {
  'use strict';

  const COLORS = { /* 复 P3 PR1 + 8 报酬业务分色 */ };
  const REWARD_FIELDS = ['ownBasic', 'pairBonus', 'teamBonus', 'savings', 'leader', 'horizontal', 'retail', 'total'];
  const REWARD_COLORS = ['#5AA4AE', '#758A99', '#F0C239', '#C0EBD7', '#5AA4AE80', '#758A9980', '#C0EBD780', '#5AA4AE'];

  const $ = (s) => document.querySelector(s);
  const $$ = (s) => document.querySelectorAll(s);

  let allScenarios = [];
  let currentId = null;
  let currentData = null;  // {params, state, overview, top5}

  function showToast(msg, type) { /* ... */ }
  function formatUSD(s) { /* ... */ }

  async function loadList() { /* GET /api/scenarios, 渲染侧栏 */ }
  function renderList() { /* 跟 P4 一样 */ }
  async function selectScenario(id) {
    // 1) 拉 state M14 bfs_id=0
    // 2) 拉 overview/all M14
    // 3) 循环拉 state M14 bfs_id=0/1/2/3/4 (TOP 5 固定抽样)
    // 4) 渲染 9 section
  }

  function renderCover() { /* Section 1 封面 */ }
  function renderSummary(state) { /* Section 2 摘要 8 卡片 */ }
  function renderTreeCanvas() { /* Section 3 树形 Canvas (复 PR1 drawNode) */ }
  function renderParams() { /* Section 4 4 border-beam (复 PR1) */ }
  function renderLineChart(overviewAll) { /* Section 5-6 14月 8 折线 (复 PR3) */ }
  function renderHeatmap(overviewAll) { /* Section 7 8×14 热图 (复 PR2) */ }
  function renderTop5(top5Data) { /* Section 8 TOP 5 横向条形 + 8 卡片 */ }
  function renderDisclaimer() { /* Section 9 风险免责 (静态) */ }

  async function generatePDF() {
    if (!currentId) { showToast('先选 1 个 scenario', 'error'); return; }
    const sections = $$('.pdf-section');
    const { jsPDF } = window.jspdf;
    const pdf = new jsPDF('p', 'mm', 'a4');
    for (let i = 0; i < sections.length; i++) {
      showToast(`正在生成第 ${i+1}/${sections.length} 页...`, 'info');
      const canvas = await html2canvas(sections[i], { scale: 2, backgroundColor: '#ffffff', logging: false });
      const imgData = canvas.toDataURL('image/jpeg', 0.95);
      const imgHeight = (canvas.height * 210) / canvas.width;
      if (i > 0) pdf.addPage();
      pdf.addImage(imgData, 'JPEG', 0, 0, 210, Math.min(imgHeight, 297));
      // 短暂等待让 UI 更新 (避免浏览器卡死)
      await new Promise(r => setTimeout(r, 50));
    }
    const today = new Date().toISOString().slice(0, 10);
    const s = allScenarios.find(x => x.id === currentId);
    pdf.save(`scenario_${currentId}_${s ? s.name : 'plan'}_${today}.pdf`);
    showToast('✅ PDF 已下载', 'success');
  }

  document.addEventListener('DOMContentLoaded', () => {
    loadList();
    $('#btn-generate-pdf').addEventListener('click', generatePDF);
  });
})();
```

- [ ] **Step 2: 验证**
- 浏览器访问 `/static/scenario_pdf.html`, 选 S1
- 9 section 全部渲染 (树形/曲线/热图/TOP5 4 副 canvas + 8 卡片 + 4 border-beam)
- 点 "📄 生成 PDF", 浏览器下载 `scenario_1_live_2026-08-07.pdf`
- 打开 PDF, 9 页内容完整, 中文不乱码

- [ ] **Step 3: Commit**

```bash
git add static/scenario_pdf.js
git commit -m "feat(scenario-ui): P5 Task 3 — scenario_pdf.js 6 段流程 (选/拉/画4 canvas/截图/jsPDF拼9页/下载)"
```

---

## Task 4: 主菜单入口

**Files:**
- Modify: `static/index.html`

- [ ] **Step 1: 找现有 3 个 nav link (PR1 + PR3 + P4), 加 "📄 Scenario PDF" link**

```bash
Select-String -Pattern "scenario.html|scenario_compare.html|scenario_library.html" static/index.html
```

加:
```html
<a href="/static/scenario_pdf.html" class="nav-link">📄 Scenario PDF</a>
```

- [ ] **Step 2: 验证 (浏览器访问 `/static/`, 看主菜单有 4 个 nav link)**

- [ ] **Step 3: Commit**

```bash
git add static/index.html
git commit -m "feat(scenario-ui): P5 Task 4 — static/index.html 主菜单加 📄 Scenario PDF 入口"
```

---

## Task 5: Playwright e2e 测试

**Files:**
- Create: `tests/test_scenario_pdf_e2e.py`

- [ ] **Step 1: 写测试** (~80 行, 2 测试)

```python
# tests/test_scenario_pdf_e2e.py
import pytest
import subprocess
import time
import os
from playwright.sync_api import sync_playwright, expect

BASE_URL = "http://127.0.0.1:38089"

@pytest.fixture(scope="module", autouse=True)
def server():
    """启动 uvicorn 测试服务器 (独立端口)"""
    proc = subprocess.Popen(
        ["python", "-m", "uvicorn", "main:app", "--port", "38089", "--host", "127.0.0.1"],
        cwd=r"D:\Projects\Reward\RewardAgentAnalysis",
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(3)  # 等待 server 启动
    yield proc
    proc.terminate()
    proc.wait()

def test_pdf_page_renders():
    """测试 1: scenario_pdf.html 渲染 + 选 scenario + 9 section 可见"""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{BASE_URL}/static/scenario_pdf.html")
        page.wait_for_selector("#scenario-list", timeout=10000)
        # 等列表加载, 选第 1 个
        page.wait_for_function("document.querySelectorAll('.pdf-sidebar-item').length > 0", timeout=10000)
        page.locator(".pdf-sidebar-item").first.click()
        # 等 9 section 全部渲染 (60s, 跟 PR1 一样 已知)
        page.wait_for_selector(".pdf-section", timeout=60000)
        sections = page.locator(".pdf-section").count()
        assert sections == 9, f"期望 9 section, 实际 {sections}"
        # 验证 4 副 canvas 存在
        canvases = page.locator(".pdf-section canvas").count()
        assert canvases >= 4, f"期望 ≥4 副 canvas, 实际 {canvases}"
        browser.close()

def test_pdf_download():
    """测试 2: 点 '📄 生成 PDF' 触发 download 事件"""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.goto(f"{BASE_URL}/static/scenario_pdf.html")
        page.wait_for_function("document.querySelectorAll('.pdf-sidebar-item').length > 0", timeout=10000)
        page.locator(".pdf-sidebar-item").first.click()
        page.wait_for_selector(".pdf-section", timeout=60000)
        # 点生成按钮, 等 download
        with page.expect_download(timeout=120000) as download_info:
            page.locator("#btn-generate-pdf").click()
        download = download_info.value
        assert download.suggested_filename.startswith("scenario_")
        assert download.suggested_filename.endswith(".pdf")
        browser.close()
```

- [ ] **Step 2: 跑测试 (业务接受 60s+ 提交延迟)**

```powershell
cd D:\Projects\Reward\RewardAgentAnalysis
python -m pytest tests/test_scenario_pdf_e2e.py -v 2>&1 | Select-Object -Last 20
```

期望: 2 pass (业务接受慢)

- [ ] **Step 3: Commit**

```bash
git add tests/test_scenario_pdf_e2e.py
git commit -m "test(scenario-ui): P5 Task 5 — Playwright e2e (scenario_pdf.html 渲染验证 + PDF 下载验证)"
```

---

## Task 6: AGENTS.md §6.9 P5 状态

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: 追加 §6.9 (用 `_append_pr3_compare_section.py` 模式追加)**

```markdown
### 6.9 P5 — 商业计划书 PDF 导出 (独立 scenario_pdf.html + jsPDF + html2canvas)

**业务**: 招商/路演场景, 把调好的 scenario 一键导出 9 页完整版商业计划书 PDF
**完成日**: 2026-08-07
**Commit 链**: spec (a9dbba0) + Task 2 (HTML+CSS) + Task 3 (JS) + Task 4 (主菜单) + Task 5 (e2e) + 本 commit
**关键文件**:
- `static/scenario_pdf.html` — 独立页, 9 section 容器 + CDN
- `static/scenario_pdf.css` — 复 P3 PR1 配色 + 9 section 排版
- `static/scenario_pdf.js` — 6 段流程: 选/拉/画4 canvas/截图/jsPDF拼9页/下载
- `static/index.html` — 主菜单加 "📄 Scenario PDF" 入口
- `tests/test_scenario_pdf_e2e.py` — Playwright 2 测试 (渲染 + 下载)
- `AGENTS.md` — §6.9 状态记录 (本 task)
- `docs/superpowers/specs/2026-08-07-p5-scenario-pdf-design.md` — spec
- `docs/superpowers/plans/2026-08-07-p5-scenario-pdf.md` — plan

**验收 (5 task 验证)**:
- Task 1 spec ✅
- Task 2 前端 HTML+CSS: 独立页 2 栏 + 9 section + CDN
- Task 3 前端 JS: 6 段流程 + 4 副 canvas + html2canvas 截图 + jsPDF 拼 9 页
- Task 4 主菜单入口
- Task 5 Playwright e2e 2 测试

**业务价值**:
- 商业计划书 PDF 是"对外交付物", 邮件附件/印刷品场景必需
- 9 页完整版含 树形/参数/曲线/热图/TOP5, 招商路演"一方案一文档"标准化
- 1 键下载: 选 scenario → 实时预览 → 点按钮 → 浏览器下载

**技术细节**:
- 0 后端改动, 复用 7 个现有 endpoint (PR1 state + PR2 overview/all + PR3 list)
- 0 npm 装包, 2 个 CDN script 引入 (jsPDF 2.5 + html2canvas 1.4)
- 中文支持: html2canvas 整段截图, jsPDF addImage 装图 (Canvas 用浏览器原生字体, 不走 jsPDF text 模式, 0 字体问题)
- 4 副 Canvas: 树形 L0-L3 / 14 月 8 折线 / 14 月 8 报酬热图 / 节点 TOP 5 横向条形
- TOP 5 节点: 业务接受简化版 (bfs_id=0/1/2/3/4 固定抽样, 5×60s=5min, toast 进度)

**业务定位 (大重构 P1 阶段 第 5 子项目)**:
- P1 场景核心引擎 ✅
- P2 8 种报酬 v2 ✅
- P3 树形动态生长 UI ✅
- P4 方案库 + 分享 ✅
- P5 商业计划书 PDF ✅ (本 PR)
- P6 旧运营兼容层 (待拍板)

**风险**:
- html2canvas 截图速度 10-20s (9 section), 业务接受, toast 进度
- TOP 5 节点 5×60s = 5 分钟, 业务接受, toast 进度
- CDN 不可达: 加 fallback 提示

**后续 (P5.1+)**:
- 多 scenario 拼 PDF (主推+备选, 12 页)
- 服务端 PDF 生成 (python reportlab, 解决 10-20s 延迟)
- PDF 编辑
- 短链接 + QR 码
```

注意字符 "兜" 不用 "兑".

- [ ] **Step 2: 跑全部测试**

```powershell
cd D:\Projects\Reward\RewardAgentAnalysis
python -m pytest tests/test_scenario_orm.py tests/test_migrate_scenarios.py tests/test_scenario_repository.py tests/test_scenario_routes.py tests/test_scenario_builder.py tests/test_scenario_pv.py tests/test_scenario_cache.py tests/test_scenario_consistency.py tests/test_scenario_model.py tests/test_commission_own_basic.py tests/test_pr2_root_consistency.py tests/test_db_admin.py tests/test_scenario_ui_e2e.py tests/test_scenario_pdf_e2e.py 2>&1 | Select-Object -Last 5
```

期望: 73+2=75 (PR1 1 fail 已知, P5 2 e2e pass)

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md
git commit -m "docs(agents): §6.9 P5 状态记录 (商业计划书 PDF 导出 + 独立 scenario_pdf.html + jsPDF + html2canvas)"
```

---

## 验证清单 (P5 全部完成后)

- [ ] 独立 static/scenario_pdf.html
- [ ] 9 section 实时预览
- [ ] 4 副 Canvas 渲染 (树形/曲线/热图/TOP5)
- [ ] 1 键下载: 文件名 `scenario_{id}_{name}_plan_{date}.pdf`
- [ ] 9 页内容完整: 封面/摘要/树形/参数/曲线/热图/TOP5/免责
- [ ] 中文不乱码
- [ ] 主菜单 "📄 Scenario PDF" 入口
- [ ] Playwright e2e 2 测试 pass
- [ ] 0 后端改动
- [ ] 0 npm 装包
- [ ] 75 测试 pass (73 + 2 P5 e2e)
- [ ] 0 回归 (P1+P2+P3+P4 全部 50+ commit 稳定)

## Self-Review Checklist

- [ ] Spec coverage: 10 章节对应 6 task
- [ ] Placeholder scan: 无 TBD / TODO
- [ ] DRY: 复 P3 PR1 配色 + P3 PR2 热图 + P3 PR3 折线 + P4 侧栏
- [ ] YAGNI: 不做多 scenario 拼 PDF / 服务端 PDF / 短链接 (后续 P5.1+)
- [ ] TDD: 2 Playwright e2e 测试 (业务接受 60-120s 慢)
- [ ] Frequent commits: 6 task = 6 commit (1 spec + 4 task + 1 docs)
