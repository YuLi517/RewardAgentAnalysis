# archive/v1.0.2-vite-react — Vite 沙箱归档

> v1.0.2 阶段在 `D:/Projects/RewardAgentAnalysis-vite` 沙箱里做的 React 19 + Vite 探索
> 2026-08-07 拍板 v1.0.5 用纯 CSS conic-gradient 旋转光带后, 沙箱价值结束, 全删
> 核心 React 组件归档到这里, 以后想 React 化重做有参考

## 文件清单

| 文件 | 用途 |
|---|---|
| `ScenarioPage.tsx` | 顶层 React 组件, layout = left form + right canvas + cards |
| `ScenarioForm.tsx` | 4 个 GlowCard (form: tree/growth/revenue/commission) |
| `TreeCanvas.tsx` | Canvas 2D 树形 (L0-L3, 4 大区, 4 色) |
| `CommissionCards.tsx` | 8 张 GlowCard (报酬卡片, 2x4 grid) |
| `Heatmap.tsx` | 8 × 14 月热图 (Canvas 2D) |
| `GlowCard.tsx` | 纯 CSS 旋转光带组件 (v1.0.5 引入, 替换 BorderBeam 1.3) |
| `BeamCard.tsx` | BorderBeam 1.3 wrapper (v1.0.4 及之前, v1.0.5 起 re-export GlowCard) |
| `api.ts` | postScenario / getOverview / getOverviewAll |
| `types.ts` | FormState / Overview / HeatmapData TypeScript 类型 |
| `scenario.css` | v1.0.5 纯 CSS 流光样式 (跟主仓 `static/scenario.css` 一致) |
| `main.tsx` | React 入口 |
| `vite.config.ts` | Vite + React plugin 配置 |
| `package.json` | deps: react 19 / vite 8 (已移除 border-beam) |

## 关键决策历史

- **v1.0.2 (commit 5170184)**: scenario.html React 化, 引入 border-beam 1.3
- **v1.0.3 (commit 0072800)**: beam-content 改浅色, light theme, 失败 (opacity 0.12 几乎不可见)
- **v1.0.4 (commit 0f4214e)**: 改回深色 + dark theme + box-shadow 青色外发光
- **v1.0.4b (commit c6f82dd)**: 8 报酬卡片加 box-shadow
- **v1.0.5 (commit 6e3cf3b)**: **拍板** BorderBeam 1.3 替换为纯 CSS `conic-gradient` 旋转光带
- **2026-08-08**: 流光效果整合到主仓 (`15a7282`), 沙箱价值结束
