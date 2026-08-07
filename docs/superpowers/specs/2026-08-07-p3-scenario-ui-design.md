# P3 树形动态生长 UI — Design Spec

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:brainstorming to evolve this design.

**Goal:** 给招商/路演客户做"实时调参计算器" — 调 4 组参数, 实时看 8 种报酬在 15 月累计. 调 scenario_routes 3 API.

**Architecture:** 独立 `static/scenario.html` (跟主运营 `static/index.html` 平级), 调 `scenario_routes.py` 已有的 POST/GET 2 个端点. Canvas 2D 渲染树形图 + border-beam 科技感 CSS 动效 + 提交后刷新数据流. PR1 仅前端 + 0 后端改动 (复用 PR3 路由).

**Tech Stack:** Vanilla HTML + CSS + JS (跟项目其他页面一致), Canvas 2D, 零 npm 依赖.

**Spec:** `docs/superpowers/specs/2026-08-07-p1-scenario-engine-design.md` §4.3 (scenario_routes 端点定义)
**Plan:** `docs/superpowers/plans/2026-08-07-p3-scenario-ui.md` (TBD)

---

## 1. 业务定位 (User Story)

```
作为 招商/路演客户
我想 调 4 组参数, 实时看 8 种报酬在 15 月累计
为了 路演时给客户演示, 客户可以问"如果 PV 改 1500, 团队培育金涨多少?"
```

**3 类用户视角**:
1. **路演客户** — 投屏展示, 看 4 组参数 → 8 种报酬 → 树形图
2. **销售** — 拉客时调参, 跟客户一起看
3. **运营** — 看 1 个参数变化对 8 种报酬的全局影响

**业务目标 (P3 PR1 范围)**:
- 调 4 组参数, 提交后, 实时 (≤ 2s) 看 8 种报酬累计 + 树形图
- 1 次调参 = 1 个 scenario, 存 DB (跟 PR3 路由对接)
- 路演时不需要等, 体验流畅

---

## 2. 范围 (In/Out)

### In Scope (P3 PR1, 1-2 天)
- 独立页面 `static/scenario.html`
- 4 组参数表单 (TreeShape / Growth / Revenue / CommissionConfig)
- Canvas 2D 树形图 (L0-L3 全画, L4+ 提示省略)
- 8 种报酬卡片 (ownBasic / pairBonus / teamBonus / savings / leader / horizontal / retail / total)
- 提交按钮调 POST /api/scenarios
- 拉 GET /api/scenarios/{id}/state + /overview 显示
- 调 scenario_routes 已有 3 个端点, 0 后端改动
- 主菜单加入口

### Out of Scope (P3 PR2/PR3 后续)
- 时间轴折线 (PR2)
- 多 scenario 对比 (PR3)
- 导出 PNG/CSV (PR3)
- 拖拽实时调参 (debounce 1s) (PR2 考虑)
- 移动端适配 (P3 全程不考虑, 桌面浏览器为主)
- 4 组参数折叠面板 / 高级设置 (后续)
- 节点 hover/click 详情 (后续)

---

## 3. File Structure

| 文件 | 责任 |
|---|---|
| `static/scenario.html` | 独立页: 表单 + Canvas 树形 + 8 报酬卡片 |
| `static/scenario.js` | JS: 调 POST/GET 路由 + Canvas 树形渲染 + border-beam 初始化 |
| `static/scenario.css` | CSS: 科技感样式 (border-beam, 多色, 暗背景) |
| `static/index.html` | 修改: 主菜单加 "📐 Scenario" 入口 (5 行) |
| `tests/test_scenario_ui_e2e.py` | Playwright e2e: 加载页 + 填表 + 提交 + 校验 8 报酬显示 |

---

## 4. 页面布局 (Layout)

### 4.1 2 栏布局 (CSS Grid)

```
┌─────────────────────────────────────────────────────────────┐
│ 📐 SCENARIO 招商/路演实时计算器                              │
├──────────────┬──────────────────────────────────────────────┤
│ LEFT (280px) │ RIGHT (1fr)                                  │
│              │                                              │
│ ┌──────────┐ │ 🌲 树形图 (Canvas 2D)                       │
│ │ 🌳 Tree  │ │ ┌──────────────────────────────────────────┐ │
│ │  [BEAM]  │ │ │ ●━━━━●━━━━●━━━━●                         │ │
│ └──────────┘ │ │  ┃     ┃     ┃                            │ │
│              │ │  ●━●   ●━●   ●━●                          │ │
│ ┌──────────┐ │ │  (省略 L4+, 共 2144 节点)                │ │
│ │ 📈 Grow  │ │ └──────────────────────────────────────────┘ │
│ │  [BEAM]  │ │                                              │
│ └──────────┘ │ 💎 8 种报酬 — 月 14 累计                    │
│              │ ┌────┬────┬────┬────┐                        │
│ ┌──────────┐ │ │ownB│pair│team│save│                        │
│ │ 💰 Rev   │ │ ├────┼────┼────┼────┤                        │
│ │  [BEAM]  │ │ │lead│hori│retl│tot │                        │
│ └──────────┘ │ └────┴────┴────┴────┘                        │
│              │                                              │
│ ┌──────────┐ │ [👁 树形预览] [🎲 提交场景 + 算报酬]        │
│ │ 🎁 Comm  │ │                                              │
│ │  [BEAM]  │ │                                              │
│ └──────────┘ │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

### 4.2 border-beam 动效 (4 个表单框)

- 纯 CSS, 跟 npm `border-beam` 包效果一致
- 3s 周期 conic-gradient 旋转
- 主色 #5AA4AE (天水碧), 跟现有 UI 调色板一致
- 4 层级 token:
  - 主色 #5AA4AE (input border, 提交按钮 bg, 树形图节点高亮)
  - 浅色 #D6ECF0 (白色文字, 卡片背景)
  - 辅色 #758A99 (灰色文字, input label)
  - 深色 #C0EBD7 (卡片 active, success)
  - 暗背景 #1a1a2e (卡片, 表单背景)

---

## 5. 数据流 (Data Flow)

### 5.1 流程 (提交后刷新)

```
[User 改 4 组参数]
    ↓
[点 🎲 提交场景]
    ↓
[JS: POST /api/scenarios body=ScenarioIn]
    ↓
[Server: ScenarioRepository.save → DB row id]
    ↓
[Server: 返 {id, name}]
    ↓
[JS: GET /api/scenarios/{id}/state?month=14&bfs_id=0]
    ↓
[JS: GET /api/scenarios/{id}/overview?month=14]
    ↓
[JS: 更新 8 种报酬卡片 + 树形图 Canvas 重画]
    ↓
[User 看结果]
```

### 5.2 错误处理

- POST 422 (校验失败): 显示 "参数不合法: {field}={value}" 红条
- POST 500: 显示 "服务器错误, 请重试" 灰条
- GET 404: 提示 "scenario 已被删, 请重新提交"
- GET 500: 重试 1 次, 失败提示

### 5.3 Loading 状态

- POST 期间: 提交按钮 disable + 灰显 + "提交中..."
- GET 期间: 8 报酬卡片灰显 (半透明)
- 总延迟预算: ≤ 2s (4 组参数 + 2144 节点计算 + 8 种报酬)

---

## 6. 树形图渲染 (Canvas 2D)

### 6.1 算法

- L0 root 居中, 4 L1 父左右排, 每个 L1 父 2 子 L2, 每个 L2 父 2 子 L3
- L4+ 不画 (节点太多), 底部提示 "省略 L4+, 共 2144 节点"
- 节点大小固定 5-12px, 颜色按 4 大区轮换 (region_id 1-4 → 4 色)
- 连线用 1px line, alpha 0.4

### 6.2 性能

- 2144 节点全部画需要画到 L4-L10 太多. PR1 只画 L0-L3 (1+4+8+16=29 节点) + 提示
- 后期 PR2 加 zoom/pan, 客户可缩放看 L4+

### 6.3 数据来源

- 树形结构: 从 `GET /api/scenarios/{id}/state?month=0&bfs_id=N` 拉 (state 返的是单节点 breakdown)
- 业务上 P3 PR1 树形节点展示 ID + region, 暂不展示具体报酬 (避免太多 state 请求)
- 后续 PR2: 树形节点加 hover 展示该节点 ownBasic / pairBonus 详情

---

## 7. 8 种报酬卡片

### 7.1 布局 (4 × 2 网格)

- 8 卡片 = 4 列 2 行
- 每卡片: 上 label (英文), 下值 (USD 数字)
- total 卡片底色用 #C0EBD7 (highlight, 比其他 7 卡片亮)

### 7.2 数据来源

- 拉 `GET /api/scenarios/{id}/overview?month=14` 8 字段:
  - ownBasic / pairBonus / teamBonus / savings / leader / horizontal / retail / total
- Decimal → float (前端格式化 $X.XX)
- 服务端返 string (Decimal JSON 边界), JS parseFloat

---

## 8. 主菜单集成

### 8.1 static/index.html 改动 (5 行)

```html
<!-- 在顶部导航加 -->
<a href="/static/scenario.html" class="nav-link">📐 Scenario</a>
```

### 8.2 入口位置

- 顶部 nav bar, 跟现有 4 tab 平级
- 不破坏现有 4 tab 布局

---

## 9. 测试 (Playwright e2e)

### 9.1 业务场景

1. 打开 `/static/scenario.html`
2. 改 4 组参数 (默认值)
3. 点提交
4. 等 ≤ 2s, 8 报酬卡片显示
5. 校验: ownBasic > 0, total > 0, 树形 Canvas 有内容

### 9.2 校验点

- Page title = "📐 SCENARIO 招商/路演实时计算器"
- 4 个 border-beam 框可见
- 树形 canvas 宽度 ≥ 400px
- 8 报酬卡片 label 跟业务字段对应
- 提交按钮文案 = "🎲 提交场景 + 算报酬"

---

## 10. 风险 & 缓解

| 风险 | 缓解 |
|---|---|
| Canvas 2D 在低性能机器卡 | PR1 只画 29 节点 (L0-L3), 风险低 |
| 8 种报酬计算慢 (>2s) | PR2 优化: 客户端 cache 4 函数结果 (own_basic/savings/horizontal/pair_bonus) |
| 视觉风格跟主页冲突 | 主菜单入口小, 用户知道是独立功能 |
| 提交失败用户不知 | error toast 显式提示 |
| 数据错位 (8 字段不匹配) | 测试校验 key 跟 value 类型 |

---

## 11. 后续 PR (Roadmap)

### P3 PR2 (1-2 天): 时间轴折线 + 月累计
- 拉 GET overview 0-14 月, 画 8 种报酬累计折线
- 月份选择器 (0-14 滑块)
- 实时对比 (8 条折线)

### P3 PR3 (2-3 天): 多 scenario 对比 + 导出
- POST 多个 scenario, 侧栏列表
- 同图对比 (多 scenario 折线)
- 导出 PNG (Canvas → blob → download)
- 导出 CSV (overview + state)

---

## 12. 验收 (Definition of Done)

- [ ] 4 个表单 (Tree/Growth/Revenue/Commission) 跟 spec 一致
- [ ] border-beam 动效可见 (3s 周期 conic-gradient 旋转)
- [ ] Canvas 树形图 29 节点 + 提示省略
- [ ] 8 报酬卡片 + total highlight
- [ ] 提交 ≤ 2s 返回
- [ ] 错误处理 toast 正确
- [ ] Playwright e2e 测试通过
- [ ] 主菜单入口可见
- [ ] AGENTS.md §6.5 更新 P3 PR1 状态
