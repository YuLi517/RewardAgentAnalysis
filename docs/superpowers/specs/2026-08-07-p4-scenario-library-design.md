# P4 方案库 + URL 分享 — Design Spec

**Goal:** 独立 `static/scenario_library.html`, 侧栏所有 scenarios 列表, 中间 4 组参数 + 8 报酬 详情, URL `?id=123` 分享 + 复制链接.

**Architecture:** 0 后端改动 (复用 PR3 list + load 端点). 前端独立页面, 读 URL `?id=` 自动加载, 详情用 border-beam 风格 (跟 PR1 一致).

**Tech Stack:** 复用栈 (Vanilla HTML + CSS + JS, border-beam 纯 CSS, 零 npm 依赖).

**Spec 父**: `docs/superpowers/specs/2026-08-07-p3-scenario-compare-design.md` (PR3 列表端点)

---

## 1. 业务定位

```
作为 招商/路演销售
我想 调好的 scenario 保存为方案, 复制 URL 发客户, 客户打开看到同一方案
为了 路演后发客户, 客户自己调参, 不用重述参数
```

## 2. 范围 (In/Out)

### In Scope (P4, 1-2 天)
- 独立 `static/scenario_library.html`
- 侧栏 scenarios 列表 (复用 GET /api/scenarios, 跟 PR3 列表同源)
- 中间 详情: 4 组参数 + 8 报酬卡片 (跟 PR1 scenario.html 一样 4 个 border-beam + 8 卡片)
- URL `?id=123` 自动加载指定 scenario, 0 id 列表全部
- 分享按钮: 复制 `${origin}/static/scenario_library.html?id=${sid}` 到剪贴板
- 主菜单加 "📚 Scenario 库" 入口

### Out of Scope
- 多用户隔离 (admin 共享)
- 短链接 / QR 码 (后续 PR)
- 方案编辑 / 重命名
- 方案删除 (admin only, 后续)
- 方案版本控制 (后续)

## 3. File Structure

| 文件 | 责任 |
|---|---|
| `static/scenario_library.html` | 独立页 (~80 行) |
| `static/scenario_library.js` | 列表 + 详情 + URL 参数 + 复制 (~120 行) |
| `static/scenario_library.css` | 侧栏 + 详情 + 分享按钮 (~80 行, 复用 PR1 border-beam 样式) |
| `static/index.html` | 主菜单加 "📚 Scenario 库" 入口 |
| `AGENTS.md` | §6.8 状态记录 |

## 4. 页面布局

```
┌──────────────────────────────────────────────────────────────────────┐
│ 📚 SCENARIO 库 (招商/路演方案管理)                                    │
├────────────┬─────────────────────────────────────────────────────────┤
│ 侧栏 (260) │ 详情 (1fr)                                                │
│            │                                                          │
│ S1: live  *│  📌 S1: live (创建 2026-08-07 14:30)                   │
│ S2: variantA│  ┌────────┬────────┬────────┬────────┐  [🔗 分享]     │
│ S3: variantB│  │🌳 Tree │📈 Grow │💰 Rev  │🎁 Comm │  [📊 对比]     │
│ ...        │  │[beam]  │[beam]  │[beam]  │[beam]  │                  │
│            │  └────────┴────────┴────────┴────────┘                  │
│            │                                                          │
│            │  💎 8 种报酬 — 月 14 累计                              │
│            │  ┌────┬────┬────┬────┐                                │
│            │  │ownB│pair│team│save│                                │
│            │  ├────┼────┼────┼────┤                                │
│            │  │lead│hori│retl│tot │                                │
│            │  └────┴────┴────┴────┘                                │
│            │                                                          │
│            │  URL: http://127.0.0.1:38089/static/scenario_library.html?id=1 │
└────────────┴─────────────────────────────────────────────────────────┘
```

## 5. URL 分享

### 5.1 URL 格式

`http://host:port/static/scenario_library.html?id={scenario_id}`

- 0 id: 列表显示, 详情空
- 有 id: 自动加载详情, 侧栏对应行高亮

### 5.2 复制按钮

```javascript
const url = `${window.location.origin}/static/scenario_library.html?id=${sid}`;
navigator.clipboard.writeText(url).then(() => showToast('链接已复制: ' + url));
```

## 6. 数据流

```
[用户访问 /static/scenario_library.html?id=5]
    ↓
[JS: URLSearchParams 读 id=5]
    ↓
[JS: GET /api/scenarios 拉列表, 侧栏渲染]
    ↓
[JS: GET /api/scenarios/5/state?month=14&bfs_id=0 (复 PR1 拍板 用 bfs_id=0 展示根节点)]
[JS: GET /api/scenarios/5/overview?month=14 拉 8 报酬]
    ↓
[JS: 渲染 4 border-beam 参数 + 8 报酬卡片]
    ↓
[用户点 分享 → 复制 URL 到剪贴板]
[用户点 对比 → 跳 /static/scenario_compare.html 自动选此 scenario]
```

## 7. 验收

- [ ] 独立 static/scenario_library.html
- [ ] 侧栏 scenario 列表 (复 PR3 列表)
- [ ] 4 border-beam 参数 (复 PR1 样式)
- [ ] 8 报酬卡片 (复 PR1 样式)
- [ ] URL `?id=123` 自动加载
- [ ] 分享按钮: 复制 URL 到剪贴板
- [ ] 对比按钮: 跳 scenario_compare.html
- [ ] 主菜单入口
- [ ] AGENTS.md §6.8
- [ ] 0 后端改动
- [ ] 72+ 测试 pass (PR1 1 fail 已知)

## 8. 风险

| 风险 | 缓解 |
|---|---|
| 60s 提交延迟 (跟 PR1 一样) | 业务接受, 0 改动 |
| URL 复制 clipboard 失败 (旧浏览器) | fallback: 显示 prompt 让用户手动复制 |
| 0 后端改动意味着无法加"方案重命名/删除" | spec 拍板 out of scope, 后续 PR |
