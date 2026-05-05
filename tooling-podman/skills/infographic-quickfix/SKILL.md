---
name: infographic-quickfix
description: >
  Surgical edits to specific tabs/nodes/paths in interactive infographics.
  Targets a single tab to minimize context read. Use when the change is small
  and localized — test count updates, node repositioning, path routing fixes,
  metric/log edits, or status badge changes.
---

# Infographic Quick-Fix Skill

## Purpose

Make surgical edits to one specific element in an infographic. By scoping to a tab first, we read only ~30 lines instead of ~1600. This skill is project-agnostic — adapt the **Project Configuration** section for your project.

## When to Use

- A test count changed → update one number in one tab
- A node position needs adjusting → change x/y in node definitions
- A flow path needs re-routing → fix one `<path>` or arrow in one draw function
- A metric or log line needs updating → edit one entry in one tab's data
- An implementation status badge changed → swap `impl-wired`/`impl-stub`/`impl-not-built`
- A description needs a wording tweak → edit one `desc` field
- Connection lines overlap with diagram elements → apply orthogonal routing fix

**Do NOT use this skill for**: adding new phases, adding new draw functions, major restructuring. Use the full `infographic` skill instead.

## Project Configuration

Replace the values below with your project's specifics. This is the **only section** that needs updating when adapting this skill to a new project.

```yaml
# ── File locations ──────────────────────────────────────────────────
component_infographic: "docs/nexus-gateway-flows-infographic.html"
component_data: "docs/infographic-data/component-data.js"
sequence_infographic: "docs/nexus-sequence-flows-infographic.html"
sequence_data: "docs/infographic-data/sequence-data.js"

# ── Component Flows tab lookup ─────────────────────────────────────
# Tag → approximate data line (in component-data.js) and draw function line (in HTML).
# Offsets drift after edits — use Grep for `id: N,` or
# `function drawXxxFlows` to find current positions.
component_tabs:
  1:  { tag: "ARCHITECTURE",      data_line: "~40", draw_fn: "drawArchitectureFlows",       draw_line: "~232" }
  2:  { tag: "INTRA-GATEWAY",     data_line: "~66", draw_fn: "drawIntraFlows",              draw_line: "~251" }
  3:  { tag: "PROXY RESOLUTION",  data_line: "~93", draw_fn: "drawProxyFlows",              draw_line: "~279" }
  4:  { tag: "FX QUOTE",          data_line: "~119", draw_fn: "drawFxFlows",                 draw_line: "~305" }
  5:  { tag: "LEG 1 SETTLEMENT",   data_line: "~145", draw_fn: "drawLeg1Flows",               draw_line: "~332" }
  6:  { tag: "CROSS-BORDER",       data_line: "~174", draw_fn: "drawCrossBorderFlows",         draw_line: "~357" }
  7:  { tag: "pacs.002 STATUS",    data_line: "~200", draw_fn: "drawPacs002Flows",             draw_line: "~377" }
  8:  { tag: "camt.054 RECONCIL",  data_line: "~227", draw_fn: "drawCamt054Flows",               draw_line: "~400" }
  9:  { tag: "COMPENSATION",        data_line: "~255", draw_fn: "drawCompensationFlows",         draw_line: "~422" }
  10: { tag: "SANCTIONS",          data_line: "~286", draw_fn: "drawSanctionsFlows",            draw_line: "~452" }
  11: { tag: "VALIDATION",         data_line: "~324", draw_fn: "drawValidationFlows",           draw_line: "~489" }
  12: { tag: "COMPLETE FLOW",      data_line: "~352", draw_fn: "drawCompleteFlows",             draw_line: "~520" }
  13: { tag: "SETTLEMENT MODELS",  data_line: "~387", draw_fn: "drawSettlementModelFlows",      draw_line: "~552" }
  14: { tag: "IPS ↔ GATEWAY",      data_line: "~415", draw_fn: "drawIpsGatewayFlows",            draw_line: "~580" }
  15: { tag: "H4 ASYNC JMS",       data_line: "~445", draw_fn: "drawH4AsyncFlows",              draw_line: "~677" }
  16: { tag: "STATE MACHINE",       data_line: "~476", draw_fn: "drawStateMachineFlows",          draw_line: "~756" }
  17: { tag: "PROPOSED FLOW",       data_line: "~668", draw_fn: "drawProposedStateMachineFlows",    draw_line: "~1710" }

# ── Sequence Flows tab lookup ──────────────────────────────────────
sequence_tabs:
  1: { tag: "REFERENCE DATA",         data_line: "~22" }
  2: { tag: "PROXY RESOLUTION",       data_line: "~43" }
  3: { tag: "FX QUOTE",               data_line: "~69" }
  4: { tag: "PAYMENT SUBMISSION",     data_line: "~94" }
  5: { tag: "LEG 1 SETTLEMENT",        data_line: "~119" }
  6: { tag: "MESSAGE TRANSFORMATION", data_line: "~145" }
  7: { tag: "LEG 2 SETTLEMENT",        data_line: "~168" }
  8: { tag: "COMPLETION NOTIFICATION", data_line: "~194" }
  9: { tag: "ERROR HANDLING",          data_line: "~220" }

# ── Node definitions ────────────────────────────────────────────────
# Nodes are now in component-data.js (window.COMPONENT_NODES)
node_data_file: "docs/infographic-data/component-data.js"
node_objects: ["sgp", "mys", "shared"]  # keys within window.COMPONENT_NODES
node_lines: "~9-37"  # line range in component-data.js

# ── Header ──────────────────────────────────────────────────────────
header_tagLine_line: "~129"
header_test_count_line: "~131"

# ── Implementation status box ───────────────────────────────────────
status_box_line: "~636"

# ── SVG dimensions ──────────────────────────────────────────────────
component_viewBox: "0 0 900 780"
sequence_viewBox: "0 0 1000 700"

# ── State machine corridors (for orthogonal routing) ────────────────
corridors:
  left_margin: 55
  right_margin: 810
  entry_to_leg1: 118
  leg1_to_dest: 218
  dest_to_leg2: 358
  leg2_to_compensation: 458
  compensation_to_terminal: 558
```

## Step 1: Identify the Tab

Ask: **"Which tab/phase?"** Every edit belongs to exactly one tab. Specifying the tab determines which ~30-line section to read instead of the entire file.

Parse the request into a scoped target:

```
TARGET = {
  file: "component" | "sequence",
  tab:   1-17 (component) | 1-9 (sequence),   ← adjust range per project
  section: "data" | "rendering" | "nodes" | "header",
  field: "desc" | "metrics" | "logs" | "d" | "x" | "y" | "label" | "type" | "opacity" | "stroke" | "text"
}
```

Examples:
- "Update Phase 5 metrics" → `{file: "component", tab: 5, section: "data", field: "metrics"}`
- "Move a node down 20px" → `{file: "component", tab: n/a, section: "nodes", field: "y"}`
- "Fix cross-border path in tab 6" → `{file: "component", tab: 6, section: "rendering", field: "d"}`
- "Change E2E test count" → `{file: "component", tab: n/a, section: "header", field: "text"}`
- "Update sequence Phase 3 logs" → `{file: "sequence", tab: 3, section: "data", field: "logs"}`
- "Fix overlapping lines to FAILED state in tab 16" → `{file: "component", tab: 16, section: "rendering", field: "d"}`

## Step 2: Read Only the Tab

Use the **Tab Lookup** in the Project Configuration to find the line offset. Then `Read` with `offset` and `limit=40` to read just that tab's data block.

For rendering (draw function) changes, `Read` with `offset` and `limit=80` on the draw function.

**Never read the entire file.** Grep for the line number if the offsets drift.

## Step 3: Make the Edit

Use `Edit` with the minimum context needed — typically 3-10 lines that uniquely identify the target within the tab section.

## Step 4: Verify

- For data changes: re-read the edited tab section (same offset/limit) to confirm.
- For rendering changes: suggest opening the HTML file in a browser and clicking the relevant tab button.

## Targeting Patterns

### Update a Tab Metric

```
User: "Tab 5 E2E test count is now 162"
→ Look up tab 5 → data at line from config
→ Read 40 lines around that offset
→ Edit the specific metric line
```

### Move a Node

```
User: "Move a node down by 20px"
→ Nodes are global (not tab-scoped), read node_lines from config
→ Edit the x/y values
```

### Fix a Flow Path

```
User: "The cross-border path in tab 6 should curve more"
→ Look up tab 6 → draw function from config
→ Read 80 lines around the draw function
→ Edit the `d` attribute of the <path>
```

### Change Implementation Status

```
User: "Sanctions screening is now wired"
→ Status box from config
→ Read 15 lines around the offset
→ Change "STUB" to "WIRED" and update the color class
```

### Update Sequence Flow Data

```
User: "Sequence tab 3: FX quote lock changed from 15min to 10min"
→ Look up sequence tab 3 → data line from config
→ Read 27 lines around that offset
→ Edit the specific metric line
```

### Update Header Test Count

```
User: "E2E test count changed to 162"
→ Header test count line from config
→ Read 7 lines around that offset
→ Edit the count number
→ Also check if other tabs reference the count
```

## Orthogonal Routing Helper

When asked to make paths "cleaner" or "orthogonal" (right-angle routing instead of diagonal), or when connection lines overlap with diagram elements, use the **corridor system** from the Project Configuration.

### Corridor System

| Corridor | Position | Purpose |
|----------|----------|---------|
| Left margin | x = `corridors.left_margin` | Routes failure/compensation paths down |
| Right margin | x = `corridors.right_margin` | Routes proposed or right-side paths |
| Row gaps | y = `corridors.*` values | Horizontal jogs between rows of nodes |

### Routing Patterns by Path Type

| Path type | Color | Route via | Entry stagger |
|-----------|-------|-----------|--------------|
| Early failure → FAILED | `#f85149` (red) | Left margin corridor | y-12, y-6, y+6 from target center |
| Late failure → COMPENSATING | `#00f2ff` (cyan) | Left margin corridor | y-6, y+6 from target center |
| Proposed → target (C4, C5) | `#d29922` (dashed) | Left or right margin depending on source | y+12, y+18 from target center |

### Procedure for Fixing Overlapping Lines

1. Grep for the specific `<path>` elements in the target tab's draw function
2. Read the draw function using the tab lookup (limit 80 for standard tabs, limit 100+ for state machine tabs)
3. Identify diagonal segments: `L x2 y2` where both x and y differ from the previous point
4. Replace diagonals with orthogonal segments via the nearest corridor:
   - Exit source node → jog to corridor → travel vertically → enter target node
   - Stagger entry points by 4px on multi-source targets to avoid overlap
5. Choose the routing that avoids crossing other state boxes (check against the node position object, typically named `S`)

**WRONG** — diagonal crosses state boxes:
```
M 440,86 L 250,618
```

**RIGHT** — orthogonal via left margin corridor:
```
M 440,86 L 440,118 L 55,118 L 55,606 L 85,606
```

### Preventing Connection Line Overlap

When multiple paths converge on a single target node:

1. **Use the margin corridor** — never route paths through the diagram interior where they cross other state boxes
2. **Stagger entry points** — offset each path's entry y-position by 4-6px so arrows don't stack on the same pixel
3. **Enter from different sides** — left-side sources enter from the left of the target; right-side sources enter from the right (if the right corridor is clear of other nodes)
4. **Avoid adjacent box zones** — if a neighboring box sits beside the target, route entry paths on the side opposite the neighbor
5. **Horizontal jogs go in gaps** — place horizontal segments at y-values between row regions (use corridor gap values), never through a state box

## Constraints

1. **Always specify the tab** — this determines which ~30-line section to read instead of ~1600 lines.
2. **Read only the tab** — use the Tab Lookup offsets, then Read with limit 40 (data) or 80 (rendering). Never read the entire file.
3. **Preserve surrounding structure** — the `old_string` in Edit must be unique within the tab. If it isn't, expand context until it is.
4. **Don't restructure** — if the change requires adding/removing tabs or draw functions, hand off to the full `infographic` skill.
5. **Don't forget the header** — test count changes often need updates in multiple places: header line, relevant tab metrics, and status box.
6. **SVG coordinate system** — (0,0) is top-left. Increasing y moves down. Check `component_viewBox` / `sequence_viewBox` in config.
7. **Path d attribute format** — `M x y` (move to), `L x y` (line to), `Q cx cy x y` (quadratic curve), `C cx cy x y ex ey` (cubic curve). Always close paths for shapes.
8. **Offsets may drift** — if edits add/remove lines, use Grep to find `id: N,` or `function drawXxxFlows` to get the current offset instead of the config values.