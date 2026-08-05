# Original Tree Vertical Layout — Design Spec

**Date**: 2026-08-04
**Project**: RewardAgentAnalysis
**Target file**: `static/original_tree.html` (single-page app for visualizing `json/original_tree.json`)
**Status**: Design approved, awaiting implementation plan

---

## 1. Problem Statement

`/original-tree` currently renders the 303-node tree horizontally (root at the left, 13 levels of descendants expanding to the right). This is visually inconsistent with the user's main 5-叉 9 层 tree view, where root is at the top and descendants expand downward. The user wants the same root-on-top convention here so they don't have to mentally reorient when switching between the two views.

## 2. Goal

Convert `/original-tree` to a **vertical** tree layout:

- Root node at the top center of the main view
- Children of any node laid out horizontally (left-to-right) below the parent
- Connection lines from each parent to each of its children
- The minimap (right-side panel) mirrors the new vertical layout: root at top, descendants flowing downward

Existing minimap functionality (blue box sync, click/hover/drag) MUST continue to work.

## 3. Non-Goals

- **Not** changing the 5-叉 9 层 main tree (`/tree` modal) — it's already vertical
- **Not** changing the node card design (businessLevel colors, gold/iix badges, PV display) — cards are reused
- **Not** changing pan/zoom controls, expand/collapse buttons, or any other UX
- **Not** adding new API endpoints or data structures
- **Not** changing the minimap panel size, position, or interaction model

## 4. Architecture

The DOM structure is already correct for vertical layout (each node is `wrapper > [body, children]`, with children recursively nested). The current **horizontal** appearance comes from CSS that indents children to the right (`.tree-node-children { margin-left: 32px }`) and draws a vertical border on the left. We need to:

- Center each node horizontally within its parent's children strip
- Stack children vertically under each parent
- Lay out children **horizontally** as siblings
- Draw proper connection lines (parent bottom → each child top)

The minimap's BFS layout also needs to be inverted: previously "x = sibling accumulator, y = depth layer"; now "y = sibling accumulator, x = depth layer".

## 5. Components

### 5.1 CSS — Vertical Tree (modify)

**`.tree-node`** — change from flex-row to flex-column:
```css
.tree-node {
  display: flex;
  flex-direction: column;  /* body on top, children below */
  align-items: center;     /* children centered horizontally */
  padding: 0;
  margin: 0;
  position: relative;      /* for connection line positioning */
}
```

**`.tree-node-body`** — keep card visual, but make it `flex-shrink: 0` to prevent children from squashing it.

**`.tree-node-children`** — change from indented box to horizontal flex:
```css
.tree-node-children {
  display: flex;            /* siblings lay out horizontally */
  justify-content: center;  /* centered under parent */
  gap: 24px;                /* space between siblings */
  margin-top: 32px;         /* vertical distance from parent */
  padding-top: 0;
  border-left: none;        /* remove the old vertical border */
  position: relative;
}
```

**Connection lines** — drawn with `::before` on each child wrapper:
```css
.tree-node-children > .tree-node {
  position: relative;
}
.tree-node-children > .tree-node::before {
  /* vertical line from parent bottom down to this child top */
  content: '';
  position: absolute;
  top: -32px;        /* meet parent's bottom */
  left: 50%;
  width: 1px;
  height: 32px;      /* matches .tree-node-children margin-top */
  background: var(--border, #D6ECF0);
  transform: translateX(-50%);
}
.tree-node-children::before {
  /* horizontal "trunk" line from parent center to siblings */
  content: '';
  position: absolute;
  top: -32px;
  left: 0;
  right: 0;
  height: 1px;
  background: var(--border, #D6ECF0);
}
```

Edge cases:
- Single child: skip the horizontal trunk (no siblings to connect), still draw vertical line
- Leaf node: no `.tree-node-children` → no lines
- Collapsed subtree: hide lines (CSS already hides children with `.tree-node-collapsed > .tree-node-children { display: none }`)

### 5.2 renderNode — minor structural change (modify)

The current renderNode already produces the right DOM shape:
```
.tree-node
  .tree-node-body (card)
  .tree-node-children (if has children)
    .tree-node (recursive)
```

No JS change is required for the main view, but the connection-line CSS depends on `.tree-node-children > .tree-node` matching direct child wrappers. Verify by inspection (already correct from the existing recursive render).

### 5.3 fitToScreen — re-target root top-center (modify)

Current `fitToScreen` computes scale and panX/panY to fit the entire tree. The tree's natural size after the vertical CSS change:
- `naturalW` = max sum of sibling widths at any layer (probably 4-5 cards wide × ~280px = 1120-1400px)
- `naturalH` = sum of all layer heights + gaps (13 layers × ~80px = ~1040px)

The fit logic should:
- `scale = min(containerW / naturalW, containerH / naturalH)` (same as before)
- `panX = (containerW - naturalW * scale) / 2` (horizontally center)
- `panY = 32` (small top margin, root sits near top)

No DOM measurement change needed beyond recomputing after the vertical layout.

### 5.4 minimap BFS layout — vertical (modify)

The current `minimapLayout` (in `static/original_tree.html`) lays out:
- x = sibling accumulator (horizontal siblings at same depth)
- y = depth * (MINIMAP_NODE_H + MINIMAP_GAP_Y) (vertical layer)

The vertical version swaps x and y:
- y = sibling accumulator (vertical siblings at same depth — i.e., siblings of the same parent)
- x = depth * (MINIMAP_NODE_W + MINIMAP_GAP_X) (horizontal layer)

This means minimap shows:
- Root at top-left corner
- L2 children stacked vertically on the right of root
- L3 children stacked further right, etc.

The depth layers travel left-to-right in the minimap, which matches the user's mental model of "root at top, descendants flowing downward" when they scan left-to-right.

### 5.5 minimap viewport box (modify)

The viewport box currently fits the main view's natural size (vertical, ~1040px tall × ~1400px wide) onto the minimap viewBox. After the layout swap:
- `minimap viewBox`: `0 0 totalW totalH` (where totalW = max depth layer width, totalH = max sibling stack height)
- `ratioX = layout.totalW / vs.naturalW` (unchanged in form, but different values)
- `ratioY = layout.totalH / vs.naturalH` (unchanged in form, but different values)

No formula change — just verify the existing renderViewportBox function still produces the correct box position.

## 6. Data Flow

Unchanged from PR #13. Same `originalTreeData` (303 nodes), same `viewportState`, same `subscribeViewport/emitViewport` pub-sub. Only the layout math (CSS + BFS) and the visual orientation change.

## 7. Error Handling

Unchanged from PR #13. Same try/catch wrappers, same degradation rules, same ResizeObserver.

## 8. Testing

### 8.1 Playwright e2e (modify existing test)

`tests/test_original_tree_minimap.py` (from PR #13) still applies but with one additional check:
- After the vertical layout change, the root node's bounding box should be in the top portion of the main view (top 30% of viewport height)
- The 4 L1 children should be horizontally arranged below root
- Minimap still shows 303 nodes, blue box still syncs on pan, click still navigates

### 8.2 Manual verification

Open `http://127.0.0.1:38080/original-tree` (or worktree port) and verify:
- Root at top center
- 4 L1 children in a horizontal row below root
- Each L1 child's subtree expanding downward
- Connection lines visible
- Minimap root at top, descendants flowing right
- Pan/zoom/expand/collapse all still work
- Blue viewport box in minimap still tracks main view

## 9. Files Touched

- `static/original_tree.html` — CSS (`.tree-node`, `.tree-node-children`, connection lines), `fitToScreen` (recompute), `minimapLayout` (swap x/y)
- `tests/test_original_tree_minimap.py` — add root-on-top check

No backend, no DB, no API changes. No new files.

## 10. Alternatives Considered (and rejected)

- **A. Mirror main 5-叉 9 层 SVG layout exactly** (relayoutTreeAsSvg): rejected — adds 600+ lines of complex SVG positioning. The current flex-based approach is simpler and gets us 90% of the visual goal.
- **B. Use d3-hierarchy tree layout**: rejected — adds a 200KB dependency for a small layout change.
- **C. Add a "horizontal/vertical" toggle button**: rejected — user explicitly wants vertical, not optional.
- **D. Reuse the main 5-叉 9 层 rendering pipeline**: rejected — different data shape, different code path, would create coupling.

## 11. Open Questions (none — resolved in design phase)

All questions resolved:
- Layout: vertical (root top, children below, horizontal siblings)
- Connection lines: yes, via CSS ::before
- Minimap orientation: same vertical orientation
- No toggle — vertical only

## 12. Out of Scope (explicit)

- 5-叉 9 层 main tree (`/tree` modal) — already vertical, not touched
- `/tree` modal's SVG layout — separate component, not touched
- DB schema, API endpoints, Python code
- Mobile / touch UX
- Animation of the layout transition (instant swap is fine)
