# P5 商业计划书 PDF 导出 — Design Spec

**Goal:** 独立 `static/scenario_pdf.html`, 单 scenario 9 页完整版商业计划书, 实时预览 + 1 键下载 (jsPDF + html2canvas, 0 后端).

**Architecture:** 0 后端改动 (复用 7 个现有 endpoint). 前端独立页面, 9 个 section 容器 + 4 副 Canvas (树形/曲线/热图/TOP5) + html2canvas 整段截图 + jsPDF 拼 9 页 PDF.

**Tech Stack:** 复用栈 (Vanilla HTML + CSS + JS, border-beam 纯 CSS) + CDN 引入 jsPDF 2.5 + html2canvas 1.4 (零 npm 依赖).

**Spec 父**: `docs/superpowers/specs/2026-08-07-p3-scenario-compare-design.md` (PR3 list 端点) + P4 (scenario_library 模板)

---

## 1. 业务定位

```
作为 招商/路演销售
我想 把调好的 scenario 一键导出 9 页完整版商业计划书 PDF
为了 路演后发客户 (PDF 邮件/打印), 客户离线可看, 不用 web 服务
```

**核心价值**:
- 商业计划书是"对外交付物", 邮件附件/印刷品场景必需
- 9 页完整版含 树形/参数/曲线/热图/TOP5, 招商路演"一方案一文档"标准化
- 1 键下载: 选 scenario → 实时预览 9 section → 点按钮 → 浏览器下载 PDF

## 2. 范围 (In/Out)

### In Scope (P5, 1.5-2 天, 6 commit)
- 独立 `static/scenario_pdf.html` + `.css` + `.js`
- 9 个 section 容器: 封面/执行摘要/树形图/参数配置/14月曲线/14月热图/节点TOP5/风险免责/签字栏
- 4 副 Canvas: 树形 L0-L3 + 14 月 8 折线 + 14 月 8 报酬热图 + 节点 TOP 5 横向条形
- CDN 引入 jsPDF 2.5 + html2canvas 1.4
- html2canvas 整段截图 + jsPDF addImage 拼 9 页 A4 portrait
- 实时预览: 选 scenario → 拉数据 → 渲染 4 副 Canvas + 8 卡片 + 4 参数
- 1 键下载: 点 "📄 生成 PDF" → 浏览器下载 `scenario_{id}_{name}_plan_{date}.pdf`
- 主菜单加 "📄 Scenario PDF" 入口 (跟 P3 PR1 / P3 PR3 / P4 一致)
- tests/test_scenario_pdf_e2e.py Playwright (2 测试: 渲染 + 下载)

### Out of Scope
- 多 scenario 拼 PDF (后续 P5.1)
- 短链接 / QR 码 (后续)
- PDF 编辑 (客户手动改, 业务接受 PDF 是只读)
- 印刷品出血位 (后续如有印刷需求)
- 服务端 PDF 生成 (用户拍板 0 后端, 避免 python reportlab 引入)

## 3. File Structure

| 文件 | 责任 |
|---|---|
| `static/scenario_pdf.html` | 独立页, 9 section 容器 + jsPDF/html2canvas CDN (~120 行) |
| `static/scenario_pdf.css` | 9 section 排版 + 4 副 canvas 样式 + 复 P3 PR1 配色 + border-beam (~200 行) |
| `static/scenario_pdf.js` | 6 段流程: 选 → 拉数据 → 渲染 4 canvas → html2canvas 截图 → jsPDF 拼 9 页 → 浏览器下载 (~300 行) |
| `static/index.html` | 主菜单加 "📄 Scenario PDF" 入口 (1 行) |
| `tests/test_scenario_pdf_e2e.py` | Playwright e2e (2 测试: 渲染 + 下载) |
| `AGENTS.md` | §6.9 状态记录 |

## 4. PDF 9 页内容 (A4 portrait, jsPDF 默认 210×297mm)

```
Page 1: 封面
  ┌─────────────────────────────────────────┐
  │  📘 商业计划书                            │
  │  Scenario {id}: {name}                   │
  │  生成日期: {YYYY-MM-DD}                  │
  │  联系人: _________________              │
  └─────────────────────────────────────────┘

Page 2: 执行摘要
  ┌─────────────────────────────────────────┐
  │  📋 执行摘要                              │
  │  8 种报酬 月 14 累计 (bfs_id=0 root):    │
  │  ownBasic $X / pairBonus $Y / teamBonus $Z│
  │  savings $A / leader $B / horizontal $C  │
  │  retail $D / total $TOTAL                │
  │  月均: $TOTAL/14                         │
  │  业务术语: 1 区/2 区/对等奖/团队培育       │
  └─────────────────────────────────────────┘

Page 3: 业务模型图 (树形 L0-L3 简图)
  ┌─────────────────────────────────────────┐
  │  🌳 业务模型图 (5/2 叉树)                │
  │  [Canvas 600x400 树形]                   │
  │  L0=1 / L1=4 / L2=8 / L3=16 / ... 省略  │
  │  L4+ 共 2144 节点                        │
  └─────────────────────────────────────────┘

Page 4: 参数配置
  ┌─────────────────────────────────────────┐
  │  ⚙️ 参数配置                              │
  │  ┌────────┬────────┬────────┬────────┐  │
  │  │🌳 Tree │📈 Grow │💰 Rev  │🎁 Comm │  │
  │  │[beam]  │[beam]  │[beam]  │[beam]  │  │
  │  └────────┴────────┴────────┴────────┘  │
  └─────────────────────────────────────────┘

Page 5-6: 14 月 8 报酬曲线 (8 subplot 折线)
  ┌─────────────────────────────────────────┐
  │  📈 14 月 8 报酬增长曲线                  │
  │  [Canvas 800x600 8 subplot 折线]        │
  │  - ownBasic/pairBonus/teamBonus/        │
  │    savings/leader/horizontal/retail/total│
  └─────────────────────────────────────────┘

Page 7: 14 月 8 报酬热图
  ┌─────────────────────────────────────────┐
  │  📊 14 月 8 报酬热图                      │
  │  [Canvas 800x400 8×14 颜色矩阵]         │
  │  业务分色 (ownBasic #5AA4AE / ...)      │
  │  颜色深 = 金额高                          │
  └─────────────────────────────────────────┘

Page 8: 节点 TOP 5
  ┌─────────────────────────────────────────┐
  │  🏆 节点 TOP 5 (月 14 累计 total)         │
  │  [Canvas 800x300 横向条形]               │
  │  bfs_id=0 (root 王常军) $X              │
  │  bfs_id=N (top 4) ...                    │
  │  8 报酬明细 (TOP 5 卡片)                 │
  └─────────────────────────────────────────┘

Page 9: 风险免责 + 签字
  ┌─────────────────────────────────────────┐
  │  ⚠️ 风险声明 + 免责                       │
  │  1. 本计划书基于模型推演, 实际业务可能有  │
  │     出入, 仅供参考.                      │
  │  2. 报酬计算基于 {commission_config 摘要}│
  │  3. 不构成投资建议.                      │
  │                                          │
  │  ✍️ 签字栏:                              │
  │  销售: _____________  日期: _________    │
  │  客户: _____________  日期: _________    │
  └─────────────────────────────────────────┘
```

## 5. 页面布局 (实时预览)

```
┌──────────────────────────────────────────────────────────────────────┐
│ 📄 SCENARIO PDF 导出 (商业计划书)                                    │
├────────────┬─────────────────────────────────────────────────────────┤
│ 侧栏 (260) │ 9 section 实时预览 (1fr)                                │
│            │                                                          │
│ S1: live  *│  ┌─[Section 1: 封面]──────────────────┐                │
│ S2: varA  │  │  📘 商业计划书                       │                │
│ S3: varB  │  │  Scenario 1: live                   │                │
│ ...        │  │  生成日期: 2026-08-07               │                │
│            │  └────────────────────────────────────┘                │
│            │  ┌─[Section 2: 执行摘要]──────────────┐                │
│            │  │  📋 8 种报酬 月 14 累计            │                │
│            │  │  total $X                          │                │
│            │  └────────────────────────────────────┘                │
│            │  ┌─[Section 3: 树形]──────────────────┐                │
│            │  │  [Canvas 树形 L0-L3]              │                │
│            │  └────────────────────────────────────┘                │
│            │  ┌─[Section 4: 参数]──────────────────┐                │
│            │  │  [4 border-beam]                  │                │
│            │  └────────────────────────────────────┘                │
│            │  ... 9 section 全部渲染                                 │
│            │                                                          │
│ [📄 生成 PDF]│                                                          │
└────────────┴─────────────────────────────────────────────────────────┘
```

**关键交互**:
- 侧栏点击 → 拉数据 → 9 section 全部重渲染
- 侧栏顶部 "📄 生成 PDF" 按钮 → 触发下载
- 加载中显示 toast "渲染中..." / "生成中..."

## 6. 数据流

```
[用户访问 /static/scenario_pdf.html]
    ↓
[JS: GET /api/scenarios 拉列表, 侧栏渲染]
    ↓
[用户点 S1: live]
    ↓
[JS: GET /api/scenarios/1/state?month=14&bfs_id=0 拉 root 当月 8 报酬]
[JS: GET /api/scenarios/1/overview/all?total_months=14 拉 14 月 8 报酬矩阵]
[JS: GET /api/scenarios/1/state?month=14&bfs_id=N top 5 节点 bfs_id (后端 8 报酬循环)]
    ↓
[JS: 渲染 9 section]
  - Section 1-2: 文本 + 数字 (同步)
  - Section 3-8: Canvas 异步渲染 (树形/曲线/热图/TOP5)
  - Section 9: 静态文本
    ↓
[用户点 "📄 生成 PDF"]
    ↓
[JS: html2canvas 把 9 section 逐一截图 (A4 宽度 794px @ 96dpi)]
[JS: jsPDF.addPage() + addImage() 拼 9 页]
[JS: doc.save(`scenario_${id}_${name}_plan_${date}.pdf`)]
    ↓
[浏览器下载 PDF]
```

**关键端点复用**:
- `GET /api/scenarios` (PR3 列表)
- `GET /api/scenarios/{id}/state?month=14&bfs_id=0` (PR1 根节点)
- `GET /api/scenarios/{id}/overview/all?total_months=14` (PR2 热图)
- TOP 5 节点: 循环调 `state?bfs_id=N` (N=top 5 by total_usd)

**TOP 5 实现 (业务接受简化版)**:
- 当前后端无 "top 5 节点 by total_usd" 端点
- 算法 top 5 需要后端全网遍历 2144 节点 × 14 月, 太重
- **业务接受简化版**: 固定展示 5 个节点 bfs_id=0/1/2/3/4 (root + L1 大区前 4)
- 5 次 `state?bfs_id=N` 循环 ≈ 5×60s = 5 分钟, 业务接受 (后台异步 + toast 进度)
- 注: bfs_id=0 是 root, bfs_id=1-4 是 L1 大区 (fork_type=binary 二叉只有 bfs_id=1, 2; fork_type=4-way 才有 4 个大区)
- 后续 P5.1 加后端 "top 5 节点" 端点可优化

## 7. 技术细节

### 7.1 CDN 引入 (head 顶部)
```html
<script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
```

### 7.2 中文支持
- jsPDF 默认字体不支持中文
- **方案**: html2canvas 整段截图, jsPDF addImage 装图, 文字直接画在 canvas 上
- 这样中文字体不会乱码 (Canvas 用浏览器原生字体, 跟 HTML 一致)

### 7.3 多 section 拼 PDF
```javascript
const pdf = new jspdf.jsPDF('p', 'mm', 'a4');
const sections = document.querySelectorAll('.pdf-section');
for (let i = 0; i < sections.length; i++) {
  const canvas = await html2canvas(sections[i], { scale: 2, backgroundColor: '#ffffff' });
  const imgData = canvas.toDataURL('image/jpeg', 0.95);
  const imgWidth = 210; // A4 宽 mm
  const pageHeight = 297; // A4 高 mm
  const imgHeight = (canvas.height * imgWidth) / canvas.width;
  if (i > 0) pdf.addPage();
  // 超长 section 截断 + addPage 续接 (本 spec 简化: 1 section = 1 页, 高度超 A4 自动缩放)
  pdf.addImage(imgData, 'JPEG', 0, 0, imgWidth, Math.min(imgHeight, pageHeight));
}
pdf.save(`scenario_${sid}_${name}_plan_${date}.pdf`);
```

### 7.4 性能
- 9 section × html2canvas 截图: 1-2s/页, 总 10-20s
- 业务接受, 进度用 toast "正在生成第 X/9 页..."

### 7.5 实时预览
- 9 section 在 `<div id="pdf-preview">` 内可见 (用户可滚动预览)
- 跟生成 PDF 用同一个 section DOM, 保证视觉一致
- canvas 截图时 `display: block` 强制可见 (避免 display:none 时 canvas 渲染空白)

## 8. 验收

- [ ] 独立 static/scenario_pdf.html
- [ ] 侧栏 scenario 列表 (复 P3 PR3 列表)
- [ ] 9 section 实时预览
- [ ] 4 副 Canvas 渲染 (树形/曲线/热图/TOP5)
- [ ] 1 键下载: 文件名 `scenario_{id}_{name}_plan_{date}.pdf`
- [ ] 9 页内容完整: 封面/摘要/树形/参数/曲线/热图/TOP5/免责
- [ ] 中文不乱码 (用 html2canvas 整段截图)
- [ ] 主菜单 "📄 Scenario PDF" 入口
- [ ] Playwright e2e 2 测试 pass (渲染 + 下载)
- [ ] 0 后端改动
- [ ] 0 npm 装包 (CDN 引入)
- [ ] 75 测试 pass (73 + 2 P5 e2e)

## 9. 风险

| 风险 | 缓解 |
|---|---|
| html2canvas 截图速度 10-20s | toast "正在生成第 X/9 页...", 业务接受 |
| 中文乱码 (jsPDF 默认字体) | 用 html2canvas 整段截图, 文字在 canvas 上, 0 字体问题 |
| 浏览器首次访问拉 CDN 慢 | 浏览器缓存, 二次访问 0 延迟 |
| TOP 5 节点循环 5×60s = 5 分钟太长 | 业务接受只展示 root + 固定 4 个抽样节点 (bfs_id=0/1/2/3/4), toast 进度提示 |
| section 高度超 A4 自动缩放 | pdf.addImage 高度 clip 到 297mm, 不截断, 视觉损失 |
| CDN 不可达 (防火墙) | 加 fallback: 检查 typeof jspdf === 'undefined' 提示用户 |
| html2canvas 不支持某些 CSS (e.g. conic-gradient border-beam) | Section 内 canvas + 普通 div, 不用 border-beam (改 static border 即可) |

## 10. Roadmap (后续 PR)

- P5.1 多 scenario 拼 PDF (主推+备选, 12 页)
- P5.2 服务端 PDF 生成 (python reportlab, 解决 10-20s 延迟)
- P5.3 PDF 编辑 (客户手动填字段)
- P5.4 短链接 / QR 码分享
