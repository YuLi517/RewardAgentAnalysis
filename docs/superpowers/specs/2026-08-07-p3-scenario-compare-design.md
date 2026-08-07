# P3 PR3 多 scenario 对比 + 导出 PNG/CSV — Design Spec

**Goal:** 独立 `static/scenario_compare.html`, 侧栏列出所有 scenario (checkbox 选 2-4 个), 8 报酬 × N scenario 折线对比, 导出 PNG (折线图) + CSV (overview).

**Architecture:** 后端 1 个新 list 端点 + 1 个 CSV 导出端点, 复用 PR3 `ScenarioRepository.list_all()` + PR2 `compute_month_overview`. 前端独立页面, 复用 PR2 8 报酬配色 (subplot 一一对应), Canvas 2D 折线.

**Tech Stack:** 复用栈 (Vanilla HTML + CSS + JS, Canvas 2D, 零 npm 依赖).

**Spec 父**: `docs/superpowers/specs/2026-08-07-p3-scenario-ui-design.md` (PR1) + `...-p3-scenario-heatmap-design.md` (PR2)

---

## 1. 业务定位

```
作为 招商/路演 销售
我想 调 N 个 scenario (不同参数), 同图对比, 选最优给客户演示
为了 路演 时 1 次展示 多个 PV 档位 / 不同培育金率 哪个最优
```

## 2. 范围 (In/Out)

### In Scope (P3 PR3, 2-3 天)
- 后端 2 端点:
  - `GET /api/scenarios` — 返所有 scenarios 列表 (复用 `ScenarioRepository.list_all()`)
  - `GET /api/scenarios/{id}/export/csv?total_months=14` — 返 CSV (8 报酬 × 14 月)
- 独立 `static/scenario_compare.html`
- 侧栏 scenario 列表 (checkbox, 选 2-4 个)
- 8 报酬 × N scenario 折线 (Canvas, 8 个 subplot 一一对应 PR2 热图 8 行)
- 业务配色: scenario 1 用 PR2 8 色, scenario 2 用 8 浅色, scenario 3 8 中色, scenario 4 8 深色
- 导出 PNG (折线图 Canvas → blob → download)
- 导出 CSV (scenario overview 14 月 × 8 报酬 = 112 行)
- 主菜单加 "📊 Scenario 对比" 入口

### Out of Scope
- 移动端适配
- 实时调参 (PR1 拍板, 提交后刷新)
- 节点级 hover 详情
- Excel 导出 (零依赖原则)
- 拖拽添加 scenario

## 3. File Structure

| 文件 | 责任 |
|---|---|
| `scenario_routes.py` | +2 端点: `GET /api/scenarios` 列表 + `GET /api/scenarios/{id}/export/csv` |
| `tests/test_scenario_routes.py` | +2 测试 (list + csv export) |
| `static/scenario_compare.html` | 独立页: 左侧栏 scenario 列表 + 中间 8 subplot 折线 + 底部导出按钮 |
| `static/scenario_compare.js` | Canvas 折线渲染 + checkbox 联动 + PNG/CSV 导出 |
| `static/scenario_compare.css` | 8 subplot 布局 + 侧栏 + 业务分色 4 套 |
| `static/index.html` | 主菜单加 "📊 Scenario 对比" 入口 |
| `AGENTS.md` | §6.7 P3 PR3 状态 |

## 4. 页面布局

```
┌──────────────────────────────────────────────────────────────────────┐
│ 📊 SCENARIO 对比 (招商/路演)                                          │
├────────────┬─────────────────────────────────────────────────────────┤
│ 侧栏 (240) │ 中间 (1fr)                                                │
│            │                                                          │
│ ☑ S1: live │ 8 报酬 × 8 subplot (1 行 4 个 × 2 行)                  │
│ ☐ S2: variantA │  ┌────────┬────────┬────────┬────────┐             │
│ ☐ S3: variantB │  │ownBasic│pairBons│teamBons│savings │             │
│ [+ 提交新]│  │  /\  /\ │/\  /\  │/\  /\  │ /\  /\  │             │
│            │  │ /  \/  │/  \/   │/  \/   │/  \/   │             │
│ [导出 PNG]│  └────────┴────────┴────────┴────────┘             │
│ [导出 CSV]│  ┌────────┬────────┬────────┬────────┐             │
│            │  │ leader │horizont│retail  │total   │             │
│ 0 选 (≥2) │  │ ...... │...... │...... │/\  /\  │             │
│            │  └────────┴────────┴────────┴────────┘             │
└────────────┴─────────────────────────────────────────────────────────┘
```

## 5. 折线图算法

- 8 subplot (Canvas), 2 行 4 列
- 每 subplot 1 报酬, 14 月 x 轴, 0-max 美元 y 轴
- 每个 scenario 1 折线 (4 scenario × 8 折线 = 32 折线)
- 配色: 4 套 (PR2 8 色 + 3 浅/中/深 变体)
  - Scenario 1: PR2 8 色 (#5AA4AE, #758A99, #F0C239, #C0EBD7, ...)
  - Scenario 2: 8 浅色 (alpha 0.5)
  - Scenario 3: 8 中色 (alpha 0.7)
  - Scenario 4: 8 深色 (alpha 1.0, 跟 Scenario 1 区分 by 颜色 hue shift)

## 6. 导出

### 6.1 PNG (折线图)

```javascript
canvas.toBlob((blob) => {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = `scenario_compare_${Date.now()}.png`;
  a.click();
  URL.revokeObjectURL(url);
});
```

### 6.2 CSV (overview 14 月 × 8 报酬)

- 调 GET `/api/scenarios/{id}/export/csv?total_months=14`
- 后端返 `text/csv`, Content-Disposition attachment
- CSV 格式:
  ```
  scenario_id,scenario_name,month,field,value
  1,live,0,ownBasic,0.0000
  1,live,0,pairBonus,0.0000
  ...
  1,live,14,total,1276271.12
  2,variantA,0,ownBasic,0.0000
  ...
  ```
- 前端 Blob → download

## 7. 数据流

```
[用户访问 /static/scenario_compare.html]
    ↓
[JS: GET /api/scenarios 拉列表]
    ↓
[侧栏渲染 scenario 列表 (checkbox)]
    ↓
[用户勾选 2-4 scenario]
    ↓
[JS: 选 1 个 GET /api/scenarios/{id}/export/csv?total_months=14, 拼接]
[JS: 选 2-4 个 → 拉 overview/all?total_months=14 (1 个 scenario 1 GET, 总 4 GET 14 分钟, 业务接受)]
    ↓
[Canvas 8 subplot 折线渲染]
    ↓
[用户点 导出 PNG → Canvas → Blob → download]
[用户点 导出 CSV → GET /export/csv → Blob → download]
```

## 8. 验收

- [ ] 后端 2 端点: list + csv export
- [ ] 独立 static/scenario_compare.html
- [ ] 侧栏 checkbox 选 2-4 scenario
- [ ] 8 subplot 折线 (Canvas)
- [ ] 4 套配色 (浅/中/深)
- [ ] 导出 PNG 成功
- [ ] 导出 CSV 成功 (114 行: 1 header + 14 月 × 8 报酬 = 113 数据行, 1 scenario)
- [ ] 主菜单入口
- [ ] AGENTS.md §6.7
- [ ] 74+2+2=78 测试 pass

## 9. 风险

| 风险 | 缓解 |
|---|---|
| 14 月 × 4 scenario 折线 = 14 × 60s × 4 = 56 分钟 | 业务接受 (跟 PR2 一样) |
| 8 subplot 折线密集, 难读 | hover 1 折线 → tooltip (跟 PR2 heatmap 一致) |
| CSV 114 行不大, 业务能 Excel 打开 | 0 风险 |
| 多 scenario 折线重叠 (8 subplot 5 scenario 拥挤) | 限 2-4 scenario, 多了提示 "已选 4 满" |
