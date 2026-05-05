---
name: infographic
description: >
  Update interactive infographics to reflect current project state. Keeps test
  counts, container topology, wired flows, and phase details in sync. Works with
  any project using SVG/HTML infographics with the phased-tab pattern.
---

# Infographic Skill

## Purpose

Keep interactive infographics accurate and up-to-date with the project's implementation state. This skill is project-agnostic — adapt the **Project Configuration** section below for your project.

## When to Use

Invoke this skill when:
- Test counts change (new scenarios, new steps)
- Container topology changes (added/removed services, new networks)
- A service's implementation status changes (stub → wired, not built → implemented)
- A new endpoint is added or removed
- A new message type or protocol is supported
- Error code mappings change
- A new architectural decision is made
- The user asks to update or verify the infographic
- SVG paths or state machine diagrams need orthogonal routing fixes

## Project Configuration

Replace the values below with your project's specifics. This is the **only section** that needs updating when adapting this skill to a new project.

```yaml
# ── File locations ──────────────────────────────────────────────────
component_infographic: "docs/stablecoin-flows-infographic.html"
component_data: "docs/infographic-data/component-data.js"
sequence_infographic: "docs/stablecoin-sequence-infographic.html"
sequence_data: "docs/infographic-data/sequence-data.js"
test_runner: "cd /project && python -m pytest service/tests/ -q"

# ── Component Flows phases ──────────────────────────────────────────
# Tab lookup: tag → approximate data line (in component-data.js) and draw function line (in HTML).
# Offsets may drift after edits — use Grep for `id: N,` or
# `function drawXxxFlows` to find current positions.
component_phases:
  1:  { tag: "OVERVIEW",            data_line: "~5",   draw_fn: "drawOverviewFlows",           draw_line: "~150" }
  2:  { tag: "ASSET LIFECYCLE",     data_line: "~35",  draw_fn: "drawAssetLifecycleFlows",     draw_line: "~160" }
  3:  { tag: "IDEMPOTENCY",         data_line: "~65",  draw_fn: "drawIdempotencyFlows",        draw_line: "~170" }
  4:  { tag: "KEY NAMESPACES",      data_line: "~95",  draw_fn: "drawKeyNamespaceFlows",       draw_line: "~180" }
  5:  { tag: "PBM WRAP",           data_line: "~125", draw_fn: "drawPbmWrapFlows",            draw_line: "~190" }
  6:  { tag: "PBM TRANSFER",       data_line: "~155", draw_fn: "drawPbmTransferFlows",       draw_line: "~200" }
  7:  { tag: "PBM UNWRAP",         data_line: "~185", draw_fn: "drawPbmUnwrapFlows",          draw_line: "~210" }
  8:  { tag: "DVP RESERVE",        data_line: "~215", draw_fn: "drawDvpReserveFlows",         draw_line: "~220" }
  9:  { tag: "DVP COMMIT",         data_line: "~245", draw_fn: "drawDvpCommitFlows",          draw_line: "~230" }
  10: { tag: "DVP COMPENSATE",     data_line: "~275", draw_fn: "drawDvpCompensateFlows",      draw_line: "~240" }
  11: { tag: "PVP FLOW",           data_line: "~305", draw_fn: "drawPvpFlows",               draw_line: "~250" }
  12: { tag: "IDENTITY MAP",        data_line: "~335", draw_fn: "drawIdentityMapFlows",        draw_line: "~260" }
  13: { tag: "BLOCK LISTENER",      data_line: "~365", draw_fn: "drawBlockListenerFlows",      draw_line: "~270" }
  14: { tag: "RECONCILIATION",      data_line: "~395", draw_fn: "drawReconciliationFlows",      draw_line: "~280" }
  15: { tag: "ERROR HANDLING",      data_line: "~425", draw_fn: "drawErrorHandlingFlows",       draw_line: "~290" }
  16: { tag: "MVCC AVOIDANCE",      data_line: "~455", draw_fn: "drawMvccAvoidanceFlows",       draw_line: "~300" }
  17: { tag: "COMPLETE FLOW",        data_line: "~485", draw_fn: "drawCompleteFlows",            draw_line: "~310" }

# ── Sequence Flows phases ───────────────────────────────────────────
sequence_phases:
  1:  { tag: "TOKEN ISSUE",       data_line: "~5" }
  2:  { tag: "TOKEN REDEEM",     data_line: "~40" }
  3:  { tag: "SIMPLE TRANSFER",  data_line: "~75" }
  4:  { tag: "PBM WRAP",         data_line: "~110" }
  5:  { tag: "PBM TRANSFER",     data_line: "~160" }
  6:  { tag: "PBM UNWRAP",       data_line: "~210" }
  7:  { tag: "DVP SETTLEMENT",   data_line: "~260" }
  8:  { tag: "DVP COMPENSATE",   data_line: "~330" }
  9:  { tag: "RECONCILIATION",   data_line: "~400" }

# ── Node definitions ────────────────────────────────────────────────
# Nodes are now in component-data.js (window.COMPONENT_NODES)
node_data_file: "docs/infographic-data/component-data.js"
node_objects: ["access", "service", "asset", "platform", "data"]  # keys within window.COMPONENT_NODES
node_lines: "~5-30"  # line range in component-data.js

# ── Header ──────────────────────────────────────────────────────────
header_tagLine_line: "~15"
header_test_count_line: "~17"

# ── Implementation status box ───────────────────────────────────────
# Search for "IMPLEMENTATION STATUS" or "impl-wired" / "impl-stub"
status_box_line: "~75"

# ── SVG dimensions ──────────────────────────────────────────────────
component_viewBox: "0 0 960 440"
sequence_viewBox: "0 0 900 700"

# ── State machine corridors (for orthogonal routing) ────────────────
# These define "highway lanes" for routing paths without crossing nodes.
# Discover from node positions: find gaps between rows of state boxes.
corridors:
  left_margin: 40       # x position, before leftmost node
  right_margin: 920     # x position, after rightmost node
  wallet_to_access: 80    # y gap between wallet row and access row
  access_to_service: 180  # y gap between access and service rows
  service_to_asset: 60    # y gap between service and asset rows
  asset_to_platform: 220  # y gap between asset and platform rows

# ── Color variables (from CSS <style> block) ────────────────────────
colors:
  core: "#58a6ff"      # Core Asset logic (Token)
  adapter: "#a371f7"   # Fabric adapter
  service: "#3fb950"   # Service layer (orchestrators)
  access: "#f0883e"    # Access layer (API, VC)
  platform: "#79c0ff"  # Platform layer (Fabric peers)
  database: "#d29922"  # Database (PostgreSQL, CouchDB)
  escrow: "#f778ba"    # Escrow addresses
  success: "#3fb950"   # Success, confirmed
  error: "#f85149"     # Failure, rejection
  warn: "#d29922"      # Warning, stub
  saga: "#00f2ff"      # Saga orchestration
  idem: "#ff7b72"      # Idempotency check
  external: "#8b949e"  # External / user

# ── Project-specific caveats ────────────────────────────────────────
# Add any architectural gotchas that affect how the infographic should
# represent flows (e.g., "Asset layer metadata is opaque — only
# idempotency key extraction is permitted").
caveats:
  - "Asset layer metadata is opaque — only idempotency key extraction is permitted"
  - "Fabric MVCC conflicts kill throughput — use per-transaction escrow addresses, not shared escrows"
  - "No time.Now() in Fabric chaincode — use ctx.GetTxTimestamp() for consensus-safe timestamps"
  - "Same-account concurrent transfers serialize on that account's key — acceptable for POC"
  - "Python Fabric SDK (fabric-gateway) has less maturity than Go/Node.js SDKs — have Go proxy fallback plan"
```

## Data vs. Rendering

Each infographic separates **data** (descriptions, metrics, logs, node positions) from **rendering** (CSS, draw functions, SVG).

| What changes | Where to edit | Typical size |
|-------------|---------------|-------------|
| Phase descriptions, metrics, logs | Data section (inline or external JS) | ~30-40 lines per phase |
| Node/actor positions | Node definition object | ~15-30 lines total |
| Test counts, endpoint lists | Header or metrics within phases | ~5 lines |
| SVG paths, animations, visual layout | Draw functions in HTML | ~50-100 lines per phase |
| Colors, fonts, spacing | CSS `<style>` block | ~130 lines total |

**For typical updates (test counts, descriptions, metrics), only edit the data section.** The rendering code rarely changes.

## Update Checklist

### E2E Test Count Changes
- [ ] Header test count number
- [ ] Phase(s) that reference the count in their metrics
- [ ] Any status box that shows test totals

### New Endpoint Added
- [ ] Phase data `logs`: Add `[REST|JMS] Service → Target: METHOD /path (ClientClass)`
- [ ] Phase data `metrics`: Add `['Endpoint Name', 'METHOD /path']`
- [ ] Implementation status in the relevant draw function

### Container Topology Changes
- [ ] Phase data metrics/logs: Update container count and IPs
- [ ] Node definitions: Add/remove entries
- [ ] Sequence data actors: Update if applicable

### Service Implementation Status Change
- [ ] Status box: Move between WIRED/STUB/NOT BUILT
- [ ] Draw functions: Change path opacity/style

## Styling Conventions

| Visual Element | Meaning |
|----------------|---------|
| Solid path, full opacity | WIRED |
| Dashed path, 0.3-0.5 opacity | PRE-STEP |
| Dashed path, 0.6 opacity, cyan | CONFIG-GATED |
| Dashed path, 0.4 opacity, yellow | STUB |
| Dashed path, red | FAILURE/REJECTION |
| Animated circle | Message/data packet |

## SVG Path Routing Rules

When creating or modifying paths in state machine or flow diagrams, **always use orthogonal (right-angle) routing**. Never draw diagonal lines that cross through other state boxes.

### Why

Diagonal lines from distant nodes cross through intermediate boxes, making the diagram unreadable. Orthogonal routing uses margin corridors and region gaps to keep paths clear of all boxes.

### Corridor-Based Routing

Use the `corridors` values from the Project Configuration. The routing pattern:

1. **Exit** from the appropriate side of the source node (bottom for downward, right for same-row, left for leftward)
2. **Jog** to the nearest clear corridor (left margin or right margin)
3. **Travel** vertically through the corridor to the target row
4. **Enter** from the appropriate side of the target node (top, left, or right)
5. **Stagger** entry points on multi-source targets (4-6px offset per source)

**WRONG** — diagonal crossing state boxes:
```
M 440,86 L 250,490   ← crosses through intermediate nodes
```

**RIGHT** — orthogonal via corridor:
```
M 440,86 L 440,118 L 55,118 L 55,496 L 195,496   ← clear of all boxes
```

For same-row or adjacent-row transitions, a simple `arrow()` helper is fine. For cross-region transitions (paths spanning multiple rows), use explicit orthogonal `<path>` elements.

### Routing Patterns by Path Type

| Path type | Color pattern | Route via | Entry stagger |
|-----------|-------------|-----------|--------------|
| Early failure paths | red (`#f85149`) | Left margin corridor | y-12, y-6, y+6 from target center |
| Late/compensation paths | cyan (`#00f2ff`) | Left margin corridor | y-6, y+6 from target center |
| Proposed/future paths | dashed yellow (`#d29922`) | Left or right margin depending on source position | y+12, y+18 from target center |

### Preventing Connection Line Overlap

When multiple paths converge on a single target node (e.g., a FAILED state receiving paths from 5+ sources):

1. **Use the margin corridor** — never route paths through the diagram interior where they cross other state boxes
2. **Stagger entry points** — offset each path's entry y-position by 4-6px so arrows don't stack on the same pixel
3. **Enter from different sides** — paths from the left use the left side of the target; paths from the right use the right side (if the right corridor is clear of other nodes)
4. **Avoid the REVERSED/adjacent box zone** — if a neighboring box sits beside the target, route entry paths on the side opposite the neighbor
5. **Horizontal jogs go in gaps** — place horizontal segments at y-values between row regions (use the corridor gap values), never through a state box

### Edge-to-Edge Path Routing (Component Flows)

For component topology diagrams (not sequence diagrams), connections must use **edge-to-edge routing**:

```javascript
// Calculate edge positions, not center points
const fromRight = from.x + (from.w || 120)/2;  // Right edge
const toLeft = to.x - (to.w || 120)/2;          // Left edge

// Connect edges, not centers
const d = `M ${fromRight} ${from.y} L ${toLeft} ${to.y}`;
```

**Why**: Center-based connections cause lines to strikethrough boxes.

### Symmetric Curved Paths for Parallel Connections

When multiple arrows run between the same two nodes, distribute them by face:

```javascript
// side: 'left' or 'right' - which face to use for start and end
// index: 0 or 1 - vertical position within that side
function symmetricCurvedPath(from, to, side, index, color, dashed, label) {
  const startX = side === 'left' ? from.x - from.w/2 : from.x + from.w/2;
  const endX = side === 'left' ? to.x - to.w/2 : to.x + to.w/2;
  const yOffset = index === 0 ? -15 : 15;

  // Quadratic bezier arcs outward
  const arcDirection = side === 'left' ? -1 : 1;
  const controlX = midX + (arcDirection * 40);

  const d = `M ${startX} ${startY} Q ${controlX} ${controlY} ${endX} ${endY}`;
}
```

**Distribution Rules:**
- 2 lines: 1 left-face, 1 right-face
- 3 lines: 2 left-face (stacked), 1 right-face  
- 4 lines: 2 left-face, 2 right-face

**Label placement**: Place at control point, offset from arc:
```javascript
labelX = controlX + (side === 'left' ? -8 : 8);
labelY = controlY - 5;
textAnchor = side === 'left' ? 'end' : 'start';
```

### Lane Offset System

Track parallel paths between same coordinates to prevent vertical overlap:

```javascript
const pathLanes = new Map();
function getLaneOffset(x1, x2) {
  const key = `${Math.min(x1,x2)}-${Math.max(x1,x2)}`;
  const count = pathLanes.get(key) || 0;
  pathLanes.set(key, count + 1);
  return (count - 1) * 8; // 8px vertical offset per path
}

// Reset between phases
function clearSvg() {
  // ... remove elements ...
  pathLanes.clear();
}
```

### Node Highlighting

All nodes used in a flow must be in the highlight map, or they'll appear dimmed:

```javascript
drawFns[N] = function() {
  const hi = { node_a: 1, node_b: 1, node_c: 1 }; // Active nodes
  drawAllNodes(hi);  // Missing nodes render at 0.35 opacity
  // Draw connections...
};
```

## How to Verify

1. Open the HTML file(s) in a browser (use a local server for external data files: `cd docs && python3 -m http.server`)
2. Click each nav button to verify all phases render correctly
3. Check animated packets flow along the correct paths
4. Verify metrics panel shows current test counts and endpoint lists
5. Cross-reference with the project's test runner output for test counts

## Common Pitfalls

1. **Line offsets drift** — after edits, use Grep for `id: N,` or `function drawXxxFlows` to find current positions
2. **SVG viewBox must accommodate all nodes** — increase viewBox height if adding nodes near the bottom edge
3. **AnimateMotion paths** — each `<mpath href>` must reference an existing `<path>` element id
4. **Version number** — increment when making significant updates (new phases, topology changes)
5. **Test counts must match reality** — verify against the project's test runner before updating
6. **External data files require HTTP** — `<script src>` needs a local server, not `file://`
7. **No diagonal paths across state boxes** — use corridor-based orthogonal routing for all cross-region paths. Diagonals that cross other boxes must be replaced with orthogonal routing before committing
8. **Check project caveats** — review the `caveats` list in the Project Configuration for architectural gotchas that affect how flows should be represented
9. **Lines strikethrough boxes** — use edge-to-edge coordinates (right face to left face), not center points
10. **Active boxes appear dimmed** — include ALL node IDs used in the flow's highlight map
11. **Label overlapping on parallel paths** — use symmetric curved paths or lane offset system
12. **Path ID collision** — ensure unique IDs when creating multiple paths dynamically