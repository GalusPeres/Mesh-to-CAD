# Roadmap: scan to editable CAD, as easy as possible

Goal: anyone can turn a 3D scan of a part into a clean CAD model that opens normally in
any CAD program. The program reads the part the way a designer does: flat faces,
cylinders, rounded edges with a radius, buttons, bosses, pockets and holes with real
dimensions, and freeform surfaces only where the part really is organic. Every step
can also be driven by an AI assistant over the automation interface (MCP), so it can
align, recognise, build, check the deviation and refine on its own.

Reference product: QuickSurface (hybrid modelling: primitives, sketches and freeform
nets, trimmed against each other). Mesh-to-CAD aims to be easier to use and open
source.

## Principles

- Recognise, don't just approximate. A net over a prismatic part is not a CAD model.
- Every result is an editable feature in the history (sketch, extrude, fillet, fit,
  freeform net), never a dead mesh of patches.
- One obvious action per step, a live preview, labels in the viewport, undo, and
  defaults that are right for typical scans.
- Design intent is part of recognition: equal sizes, concentric, parallel and
  perpendicular faces, symmetry, patterns and round values.
- Checked on several parts (remote control, bracket, flange, knob, organic handle,
  bunny), from several views, with numbers, before a step counts as done.
- Every capability is also an MCP tool with machine-readable results.

## 1. Freeform nets (organic regions)

Done: one-click net on the scan or a selection (Instant Meshes), fit to the scan,
live heatmap, drag points with snapping, lay points on a plane, export as few large
B-spline faces (motorcycle-graph layout, exact shared edges, about 1 degree kinks at
irregular points), outlines of the CAD faces while editing.

Next:
- Calmer nets: remesh coarse and subdivide (fewer irregular points: 43 → 12 on the
  remote, 110 → 25 CAD faces), as a density setting.
- Sharp edges (creases) on edge loops; crease ends as layout corners.
- Net tools: split a loop, extrude border edges, delete and fill faces, smoothing
  brush, snap all to the scan, symmetry plane, align a chain to a line.
- Zebra stripes for continuity checks.

## 2. Shape recognition ("Formen erkennen")

- Base faces: dominant planes (later cylinders) found robustly, ignoring details.
- Reliefs on a base face: raised and sunk features (buttons, bosses, ribs, pockets,
  holes), nested (a pad inside a recess), each with:
  - outline: circle, slot, rounded rectangle, ring segment (annular sector), or a
    free profile of lines and arcs;
  - height or depth, flat or domed top, edge rounding.
- Blends: fillet strips between two faces with their radius; chamfers.
- Freeform: regions no primitive explains.
- Design intent: equal sizes grouped, concentric and patterned features (a direction
  pad: ring segments around a centre button), rows and columns aligned, values
  rounded.
- Panel: grouped list with dimensions, labels in the viewport, hover to highlight,
  untick what should not be built.

## 3. Build features from the recognition

- One sketch per base face with all outlines, one extrude per height group
  (add for bosses, cut for pockets), fillets with the measured radius.
- Base body: outline extrude between the base faces, or a freeform net body, then
  the reliefs added and cut.
- Everything as ordinary, editable history features.

## 4. Hybrid modelling

- Trim freeform faces with planes and primitives, offset to reference faces, extend
  surfaces, booleans between nets and solids.

## 5. AI over MCP

- Tools for recognition, building, nets per region, deviation per feature with the
  worst spots, screenshots from any view with the heatmap, and the click action.
- Off-screen mode with its own profile for checks while the PC is in use (done).

## 6. Ease of use

- First-run guidance, shortcuts in tooltips, progress with cancel everywhere, no
  long blocking work on large scans (reduce first), consistent German and English.
