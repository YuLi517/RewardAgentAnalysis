# Original Tree Minimap — Design Spec

**Date**: 2026-08-04
**Project**: RewardAgentAnalysis
**Target file**: `static/original_tree.html` (single-page app for visualizing `json/original_tree.json`)
**Status**: Design approved, awaiting implementation plan

---

## 1. Problem Statement

`/original-tree` renders the 303-node, 13-level "原版网体" tree from `json/original_tree.json`. The current single-SVG layout works well for a few dozen nodes, but when fully expanded the L8/L9 levels each contain 50+ nodes, making it impossible to grasp the whole-tree structure at a glance. Users want to know "which branch is the thickest" and "where am I inside the tree" without having to pan-and-zoom manually.

## 2. Goal

Add a **right-side fixed minimap** that:

- Renders the full 303-node tree in a compressed 30%-width panel
- Shows a blue viewport rectangle indicating the current main-view position
- Synchronizes with main-view pan/zoom/expand/collapse in real time
- Allows click-to-navigate: clicking a minimap node pans the main view to center that node
- Survives main-view state changes (zoom, pan, expand/collapse) without lag

## 3. Non-Goals

- **Not** changing the existing main-view layout/UX (zoom, pan, expand, collapse, toolbars all stay the same)
- **Not** adding a separate "overview" page (minimap is a side panel, not a full-page swap)
- **Not** implementing treemap/sunburst/icicle (other approaches were considered and rejected — see §10)
- **Not** affecting the 5-叉 9 层 main tree (`/tree` modal) — this design is scoped strictly to `/original-tree`

## 4. Architecture

The existing `/original-tree` page becomes a two-column flex layout:

```
┌─────────────────────────────────────────────┬──────────────┐
│ toolbar: 303 nodes / 13 depth / expand-all  │              │
├─────────────────────────────────────────────┤   minimap    │
│                                             │  (right 30%) │
│   main view SVG (left 70%)                  │              │
│   - existing zoom / pan / node cards        │  full tree   │
│   - right-click drag / Ctrl+wheel           │  rendered at │
│                                             │  fit-to-width│
│                                             │  blue box =  │
│                                             │  viewport    │
└─────────────────────────────────────────────┴──────────────┘
```

- Same `originalTreeData` (303 nodes) is shared between main SVG and minimap SVG
- A shared `viewportState = {scale, offsetX, offsetY, naturalW, naturalH}` drives both
- Main view's existing pan/zoom handlers also dispatch to the minimap to update its blue box
- The minimap dispatches click/drag events back to the main view's pan controller

## 5. Components

### 5.1 Layout container

- HTML: `<div class="original-tree-layout">` wraps the toolbar and a new flex row
- New `<aside id="minimapPanel" class="minimap-panel">` on the right
- Main view moves into `<main class="main-view-panel">` on the left
- CSS: `display: flex; flex: 1 1 auto`; main `flex: 0 0 70%`; aside `flex: 0 0 30%`

### 5.2 Minimap SVG (new)

- Independent `<svg id="minimapSvg">` inside the aside
- Uses d3-hierarchy `d3.tree()` to lay out the full tree (no collapse — the minimap always shows all 303 nodes)
- Computes a `fit-to-width` transform: scale = `(minimapWidth - 2*PAD) / naturalWidth`
- Renders nodes as small rectangles, width ∝ (children count + 1), height fixed, color = `businessLevel` (gold/blue/green/gray, reusing the main view's palette)
- Renders parent-child links as thin 1px lines (lighter than main view, alpha 0.3)
- All 303 nodes render — but each is ≤ 6px, so the whole tree fits in 30% width

### 5.3 Viewport indicator (new)

- A `<rect>` inside the minimap SVG, positioned and sized based on `viewportState`
- Stroke `#3B82F6` 1.5px, fill `rgba(59,130,246,0.12)`
- Position = `minimapX(viewport.offsetX)`, size = `minimapW(viewport.naturalW * scale)` × `minimapH(viewport.naturalH * scale)`
- Updates on every main-view pan/zoom event (debounced to 16ms / rAF)

### 5.4 Interaction handlers (new)

- `bindMinimapHover(node)`: hover a node → highlight it (gold outline) + show tooltip with `name` / `L{level}` / `businessLevel`
- `bindMinimapClick(node)`: click a node → dispatch `panToNode(node)` to main view, reuse existing `selectNode(node)` to highlight
- `bindMinimapDrag(viewport)`: mousedown on minimap background (not on a node) + drag → main view pan tracks pointer position (Figma-style "fast pan")
- Wheel on minimap → ignored (no zoom on minimap; minimap is always fit-to-width)

### 5.5 State sync (new, shared module)

- New file `static/original_tree_minimap.js` (or inline as `<script>` block) defines:
  - `let viewportState = {scale: 1, offsetX: 0, offsetY: 0, naturalW, naturalH}`
  - `function updateViewport(state)` — called by main view's pan/zoom handlers, updates minimap blue box
  - `function panToNode(node)` — exported, called by minimap click handler
  - Subscribes to existing main view's pan/zoom events (add a small emit hook in the existing handlers)

## 6. Data Flow

```
GET /api/original_tree/data
        │
        ↓
  originalTreeData (303 nodes)
        │
   ┌────┴────┐
   ↓         ↓
 mainSvg  minimapSvg
   │         ↑
   └─ viewportState ─┘
      (shared, rAF-throttled updates)
```

Single source of truth for the data; both views re-render from it independently. State sync is one-way: main view pan/zoom → minimap blue box. Reverse direction only on explicit minimap click/drag.

## 7. Error Handling

- **JSON load failure**: main view + minimap both show a fallback "数据加载失败, 重试" placeholder with a retry button. Same handler.
- **Node count > 500**: minimap auto-degrades — nodes render as 2x2 pixel dots, no connecting lines, blue box still works. Threshold constant `MINIMAP_DEGRADE_THRESHOLD = 500`.
- **Minimap init failure** (e.g., d3 not loaded): main view works normally, minimap panel shows blank with `console.warn` once. No throw.
- **Container resize**: ResizeObserver on the minimap container; debounced 100ms re-layout.
- **Minimap node click while main view is animating**: queue the pan, run after animation completes (no race condition).

## 8. Testing

### 8.1 Playwright end-to-end (`tests/test_original_tree_minimap.py` or JS verification script)

- Open `http://127.0.0.1:28080/original-tree`
- Verify minimap SVG renders with 303 node rects (or fewer if collapsed-rect approach)
- Verify blue viewport rect exists and has non-zero size
- Trigger a main-view pan (e.g., simulate wheel event on main SVG)
- Verify blue viewport rect position changes
- Click a minimap node, verify main view scrolls/zooms to that node
- Verify 0 JS console errors throughout
- Screenshot the result for visual regression

### 8.2 Manual verification

- Default state: tree expanded to L2 (11 nodes) — minimap shows full 303 tree, blue box covers L1-L2 region
- Click "全部展开" — minimap stays full, blue box may shrink slightly
- Ctrl+wheel zoom in/out — blue box size scales accordingly
- Right-click drag in main view — blue box follows
- Hover minimap node — tooltip appears with name + level
- Click minimap node — main view jumps, node selected

### 8.3 No live DB pollution

- Changes are scoped to `static/original_tree.html` + optional new `static/original_tree_minimap.js`
- No DB migration, no API change, no Python change
- No tests touch live DB

## 9. Files Touched

- `static/original_tree.html` — add layout flex, aside, minimap SVG, minimap JS, state sync
- Optional: `static/original_tree_minimap.js` — extracted minimap module (if HTML grows too large)
- No Python file changes
- No API changes

## 10. Alternatives Considered (and rejected)

- **A. Minimap in floating bottom-right (VSCode style)**: rejected — user wanted always-visible context
- **B. Right-side fixed column (chosen)**: matches user's mental model, main view shrinks to 70% which is still ample
- **C. Top horizontal icicle strip**: rejected — eats vertical space, less visual richness than 2D minimap
- **D. Treemap replacing main view**: rejected — main view's existing SVG details are valuable; minimap supplements rather than replaces
- **E. Sunburst radial**: rejected — 13 levels too dense for radial, visual style diverges from existing main view

## 11. Open Questions (none — all resolved in design phase)

All design questions resolved during brainstorming:
- Q1 (which tree): `/original-tree` (json/original_tree.json, 303 nodes)
- Q2 (pain point): "一眼看不全整树结构" — want to see whole-tree shape
- Q3 (approach): minimap (over treemap, sunburst, icicle)
- Q4 (position): right-side fixed column at 30% width

## 12. Out of Scope (explicit)

- 5-叉 9 层 main tree (`/tree` modal) is not touched
- The 5-叉 9 层 algorithm layer (`skills/skill_5_3.py`) is not touched
- DB schema and `data/rewarddb.db` are not touched
- Mobile / touch UX is not a goal (desktop primary use)
