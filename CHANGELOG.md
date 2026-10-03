# Changelog

All notable changes to this project are documented in this file. The format is based on
[Keep a Changelog 1.1](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/). Pull requests add fragments to [changes/](changes/),
which are merged here when a version is released.

## [Unreleased]

### Added

- Project skeleton: Electron main process with a hardened renderer, preload bridge and kernel
  process management; Python geometry kernel with a binary protocol, command registry, document
  model, revisions and rebuild engine; generated TypeScript protocol types.
- Application shell with stages, tool row, project tree, properties panel, status bar, German and
  English user interface, dark and light theme.
- Scan import (STL, OBJ, PLY) with unit choice, display in the 3D viewport, standard views and
  undo.
- Architecture and design specifications, continuous integration and contribution guidelines.
- Scans are imported from binary and ASCII STL, OBJ and PLY. The import panel shows the
  dimensions in the chosen unit, the triangle count, the scan noise and the proposed project
  tolerance; scans above 2,000,000 triangles are reduced during import.
- Every import repairs the scan (triangles without area, duplicates, inconsistent orientation,
  inside-out parts) and removes loose small parts.
- Preparation tools in _Vorbereiten_: _Reparieren_ with selectable steps, _Kleine Teile
  entfernen_, _Löcher füllen_, _Reduzieren_, _Glätten_ (display only), _Auswahl löschen_ (Entf)
  and _Scaninformationen_. Each shows what it would change before OK, marks the affected
  triangles in the viewport and can be undone. Fits and regions are carried over to the changed
  scan.
- Projects are saved as `.m2c` files (the previous file is kept as `.m2c.bak`) and opened again
  with the same document, view and stage. New, open, save and save as are in _Datei_ with
  Strg+N, Strg+O, Strg+S and Strg+Umschalt+S.
- The window title shows the project name and marks unsaved changes; closing, _Neues Projekt_
  and _Projekt öffnen_ ask before unsaved changes are lost.
- After a crash, the last state of the project is offered for restore at the next start.
- The recent files list keeps the last ten scans and projects.
- The viewport shows scans with 2 million faces smoothly: a worker prepares the geometry,
  adjacency and bounding volume hierarchy, and the view is drawn only when something changes.
- Display modes Schattiert, Schattiert + Kanten, Flach, Röntgen (X), Bereiche and Abweichung;
  Space switches between scan and bodies, only the scan and only the bodies.
- Navigation: orbit with the right mouse button around the point under the cursor, pan with the
  middle mouse button or Shift + right, zoom to the cursor with the wheel or Ctrl + right, fit
  all with F or a middle double-click, fit the selection with Shift + F, standard views 1-6 and
  0, projection with P.
- View cube with 26 clickable zones, home and 90° rotate buttons, and an axis triad.
- Section plane with a gizmo and a section outline; arrow, arc, plane and point handles.
- Bodies and construction geometry are drawn in front of the scan without z-fighting.
- Selection modes _Pinsel_ (B), _Flächenauswahl_ (W), _Lasso_ (L) and _Rechteck_ work while any
  panel tool is open. The brush shows a ring cursor whose size changes with `[` `]` or Strg+Mausrad;
  Strg removes. Smart select previews the surface under the resting cursor (shape or smooth mode,
  tolerance with Strg+Mausrad). Lasso and rectangle offer _Durch das Teil_; brush and smart select
  work on visible triangles only unless _Nur sichtbare_ is turned off. The options are remembered.
- Every stroke and selection command is one undo step: select all visible (Strg+A), clear (Strg+D),
  invert (Strg+Umschalt+I), grow and shrink by one ring (G, Umschalt+G), hide (H), show all
  (Umschalt+H) and isolate (I). Selections are kept per scan version.
- _Auswahl als Bereich speichern_ (Strg+R) creates a named region; regions can be selected, extended
  or reduced by the selection, merged, renamed and deleted from the Bearbeiten menu. Regions stay
  disjoint and neighbouring regions never share a colour.
- _Segmentieren_ splits the scan, or only the selection, into regions of single shapes with a
  sensitivity slider and a minimum size. The preview colours the regions and lists type, RMS and
  triangle count, with progress and cancel.
- _Form einpassen_ fits a plane, sphere, cylinder, cone or torus to the selected triangles, or
  chooses the type automatically and lists the other types with their RMS. The result shows scan
  noise, RMS, maximum, the share within tolerance with its verdict and the triangles used; the
  triangles are coloured pass/fail and the fitted shape is drawn as construction geometry.
- Every fitted value is _Berechnet_ or _Fest_; the direction can be parallel or perpendicular to
  X, Y, Z or another fit. The _Robust_ option ignores other surfaces in the selection (LO-RANSAC).
- Design-intent snapping proposes exact directions and values (metric or inch steps) inside the
  measurement uncertainty and keeps them only if the RMS rises by at most 5 %; each snap shows the
  measured value and can be removed.
- Fits appear in the project tree with a summary ("⌀ 16,000 mm, parallel zu Z"); their values can
  be fixed, released and their snaps removed in the properties. Editing a fit makes its triangles
  the working selection; the previous selection returns afterwards.
- _Hilfsgeometrie_ builds offset planes, planes through an axis at an angle, mid-planes of two
  parallel planes and axes from two planes, with inputs picked in the tree or the viewport and
  arrow and arc handles for distance and angle.
- _Automatisch ausrichten_ puts the largest plane of the scan on XY (material above it), the
  largest plane perpendicular to it on XZ and the origin at the corner of the scan, snapped onto
  the planes that lie there. Without two planes the principal axes of the surface are used, with
  a sign rule that gives the same pose for every scan pose. The panel draws the new coordinate
  system over the scan and shows the remaining tilt ("Größte Ebene 0,00° zu XY").
- _An Flächen ausrichten_ builds a 3-2-1 frame from fitted planes and axes, reference geometry,
  regions or the working selection, picked in the project tree or the viewport: three planes, an
  axis and an end face for shafts, or a plane and two hole axes for flanges. Each input shows the
  fitted type and RMS; parallel inputs and frames without an origin are reported.
- Both alignments can be turned over, reversed in X and rotated in 90° steps, are undoable and
  open again from the _Ausrichtung_ entry of the history. _Ausrichtung zurücksetzen_ returns to
  scan coordinates. A new alignment re-evaluates only the features that read the scan.
- _Freiformfläche_ fits a B-spline patch (P-spline height field, exact conversion to an Open
  CASCADE surface) to the selection or a region, with automatic or manual span count, smoothing
  and a margin beyond the triangles; the result block shows noise, RMS, maximum and the share
  within tolerance, and the triangles are coloured pass/fail. Regions curved by more than 150°
  are rejected with a message.
- _Loft_ builds a body through planar sections of the scan along X, Y, Z, a fitted axis or a plane
  normal, with start and end handles, 3 to 64 sections and the usual body operations. Its faces
  are tagged, so fillets and booleans can refer to them.
- _Skizze_ cuts the scan with a standard plane, a plane from the history or a plane perpendicular
  to an axis (with offset, separate cut position and reversed normal), or folds all points into a
  rotational profile about an axis. The section preview updates live while the plane moves.
- OK fits lines, arcs and circles to the section, infers horizontal, vertical, parallel,
  perpendicular, tangent, concentric and equal-radius constraints and snaps lengths, positions,
  radii, angles and bolt circles to design values inside the measurement uncertainty. Each snap
  and constraint lists the measured value and can be removed.
- Sketch mode looks along the plane with the scan dimmed. Entities can be edited numerically
  (end points, length, angle, centre, radius) with a constrained refit, deleted, fitted through
  painted points (Shift+drag), and completed with _Ecke bilden_ (K), a line between two points (L),
  a circle by centre and radius (C) and _Lücke mit Linie schließen_. Ctrl+Z undoes sketch edits
  inside the tool; Esc discards, _Skizze beenden_ adds the sketch to the history.
- Sketches build closed profiles with holes for extrude and revolve, report open profiles with
  their gap positions and are flagged in the project tree when they no longer match the scan
  after the alignment changes; _Neu anpassen_ refits them.
- Extrusion of sketch profiles: distance in one or both directions, symmetric, or up to a
  plane; the distance is pre-filled from the scan and can be dragged at an arrow handle.
- Drehung (revolve) about a sketch line, a fitted or reference axis, or X/Y/Z, with any angle.
- Grundkörper: solid cylinders, cones, spheres and tori from fits, with the length taken from
  the scan triangles on the fitted surface plus a margin, or entered manually.
- Körper teilen: split a body with an origin plane, a plane feature or a freeform patch and keep
  one side.
- Kombinieren: unite, subtract or intersect bodies, optionally keeping the tool bodies.
- Verrundung and Fase on picked edges, with _Radius aus Scan_ proposing the snapped radius.
- Every solid tool shows how far the previewed body lies from the scan (RMS, maximum, share in
  tolerance) before OK.
- New bodies can be united with, subtracted from or intersected with an existing body in every
  solid tool.
- Every body face carries a name from the feature that created it, so fillets and chamfers keep
  their edges when earlier steps change (for example a new extrusion height).
- Near-coincident planar faces are aligned before body operations, which keeps results valid and
  free of split faces.
- _Auto-Flächen_ turns an organic scan (or the selected triangles) into editable CAD without
  fitting shapes by hand: a control cage is fitted to the scan as a Catmull-Clark limit surface,
  every cage quad becomes a bicubic B-spline surface, and the surfaces are joined along shared
  edges into a valid closed body when the scan is closed. The panel offers _Detail_ (Grob,
  Mittel, Fein: about 1,200, 3,000 or 7,500 surfaces) and _Glättung_, shows progress with
  cancel, and reports the surface count, RMS, 95 % and maximum deviation from the scan and
  whether the result is a valid body. The body appears in the project tree, can be filleted,
  combined, checked with the deviation map and exported to STEP. An open scan gives an open
  surface with a note to fill the holes first.
- Measured on the Stanford Armadillo (346,000 triangles, 229 mm): Grob 4 s, RMS 0.81 mm; Mittel
  10 s, RMS 0.28 mm; Fein 21 s, RMS 0.12 mm, each a valid closed body of B-spline faces only.
- _Abweichung_ colours the scan by its signed distance to the bodies (positive: excess material)
  with three steps per side around the tolerance band, a colour-blind safe scheme, an automatic or
  manual scale range and a maximum search distance. The legend at the right edge shows the band
  limits, the tolerance bracket and mean, σ, RMS, extremes and the share within tolerance; the
  value under the cursor appears next to it, and `D` switches the colours on and off. The status
  bar shows the share within tolerance while the colours are on.
- The deviation is exact to better than 0.001 mm against brute force, its signs agree with the
  solid classifier, and a million scan points take about 6 s, cancellable with progress.
- _Messen_ shows distances, angles and diameters between fitted shapes, reference geometry, origin
  planes and axes, and body faces picked in the viewport or the tree. Values of fitted shapes carry
  their measurement uncertainty from the scan ("20,001 mm ± 0,002").
- The tolerance in the status bar opens a popover with the value, the scan noise, the proposal
  from the noise and _Fangwerte: metrisch / Zoll_; it is the only place to change them.
- _STEP exportieren …_ (`Ctrl+E`) writes AP214 or AP242 in millimetres, one product per body named
  after the project, reads the file back and compares validity, solid count and volume before it
  replaces an existing file. _STL exportieren …_ writes a watertight binary STL with a chosen
  accuracy. Both check the bodies first and name the feature that caused a problem; umlauts in
  folder and product names work.
- The project tree shows _Scan_ with its operations, _Bereiche_ (grouped by type, with the filter
  _Nur nicht verwendete_), _Körper_, _Ursprung_ and _Verlauf_ (alignment first, then the features)
  with icons, numbered names, summaries and warning, error, skipped and suppressed states.
- Tree rows can be renamed (F2), hidden and shown (H), isolated, suppressed and deleted; deleting
  lists the dependent features first. Every edit is one undo step. Double-click or Enter opens the
  feature's tool for editing. Hover and selection follow the viewport and the other way round.
- _Eigenschaften_ shows the selected object's summary, status and issues, body volume, area and
  validity, region type, RMS and triangle count, and scan information.
- Settings dialog (language, theme, inverted mouse wheel, clear selection after fit), shortcut help
  (Ctrl+/) generated from the commands, and an about dialog with versions, licences and the log
  folder.
- Start screen with _Scan importieren …_, _Projekt öffnen …_, _Beispiel öffnen_ and recent files;
  three example scans (bracket, flange, knob) are included.
- Offline help (F1) opens the page of the active tool in German or English; a getting-started guide
  walks through the example bracket from import to STEP.
- Windows installer (per user, installation folder selectable) that works offline: the geometry
  kernel is included as a frozen executable, with licence texts in `licenses/`.

### Fixed

- The application window no longer stays blank at startup: two store selectors returned a new
  empty array on every render (React error 185).
- Closing the window now waits for the answer to the unsaved-changes question; the smoothing
  setting of _Glätten_ is visible in the viewport; a dropped `.m2c` file asks before unsaved
  work is replaced; _Ordner öffnen_ appears after an export.
- Project tree rows no longer scroll sideways; long summaries are shortened with an ellipsis.
