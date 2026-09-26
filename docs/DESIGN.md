# Mesh-to-CAD design system

UI specification for version 0.1. Audience: everyone who builds or reviews UI.
Architecture and module boundaries are in [ARCHITECTURE.md](ARCHITECTURE.md).

Status: accepted, 2026-09-26, revised after the UX review of the same day (section 11).

## Contents

1. [Principles](#1-principles)
2. [Foundations](#2-foundations)
3. [Layout](#3-layout)
4. [Components](#4-components)
5. [Interaction patterns](#5-interaction-patterns)
6. [Viewport](#6-viewport)
7. [Mouse and keyboard](#7-mouse-and-keyboard)
8. [Writing](#8-writing)
9. [Accessibility](#9-accessibility)
10. [Review checklist](#10-review-checklist)
11. [Decisions](#11-decisions)

---

## 1. Principles

Mesh-to-CAD is an engineering tool. It should look like one: calm, dense where density helps,
and honest about numbers.

1. **The model is the content.** Chrome is neutral grey and takes at most 72 px at the top. Colour
   is reserved for the viewport, for state and for the single accent.
2. **One accent, used sparingly.** `#2B6BD0` marks the primary action, the active tab, focus and
   checked controls. Nothing else in the UI chrome is blue.
3. **Numbers first.** Every tool shows what it computed (scan noise, RMS, maximum, share in
   tolerance) with units, in tabular figures. Pass/fail against the project tolerance is always
   visible, and every snapped value shows the measurement it replaced.
4. **One way to do a thing.** A command appears in at most two places: the tool row and one menu
   or context menu (the empty state may repeat the start actions). One primary button per panel.
5. **Plain language.** Short, factual, sentence case. No slogans, no exclamation marks, no emojis,
   no illustrations.
6. **Predictable over clever.** Every tool follows the same life cycle (5.1). Automation always
   leaves an edit path. Nothing the user entered is thrown away without asking.

---

## 2. Foundations

All values are defined once in `src/renderer/styles/tokens.css` as custom properties per theme
(`:root[data-theme="dark"]` and `:root[data-theme="light"]`). Components use tokens only.

### 2.1 Colour

The theme is _System_ (default, follows Windows), _Dunkel_ or _Hell_. Contrast ratios are WCAG 2.x
against `--bg-panel`.

| Token                  | Dark                | Light               | Use / contrast                                                                     |
| ---------------------- | ------------------- | ------------------- | ---------------------------------------------------------------------------------- |
| `--bg-app`             | `#1C1D20`           | `#E9EAEC`           | Title bar, tool row, status bar                                                    |
| `--bg-panel`           | `#232428`           | `#F5F5F6`           | Side panels                                                                        |
| `--bg-raised`          | `#2A2B30`           | `#FFFFFF`           | Menus, popovers, dialogs, legend, panel headers                                    |
| `--bg-input`           | `#1A1B1E`           | `#FFFFFF`           | Text and number fields                                                             |
| `--bg-hover`           | `#303238`           | `#E4E5E8`           | Hover on rows and buttons                                                          |
| `--bg-pressed`         | `#383A40`           | `#D9DADE`           | Pressed buttons, active toggles                                                    |
| `--bg-selected`        | `#25395A`           | `#D5DFF0`           | Selected tree row, active tool. Text on it 9.2 / 12.6                              |
| `--bg-selected-subtle` | `#242F43`           | `#E5EAF3`           | Selected but not focused                                                           |
| `--border`             | `#393B41`           | `#D0D2D6`           | Default 1 px borders, dividers                                                     |
| `--border-subtle`      | `#2E3035`           | `#E1E2E5`           | Separators inside panels                                                           |
| `--border-strong`      | `#4B4E55`           | `#B3B6BC`           | Input borders, splitter hover                                                      |
| `--text`               | `#E4E5E7`           | `#1C1D20`           | Primary text. 12.3 / 15.5                                                          |
| `--text-secondary`     | `#A3A6AD`           | `#555960`           | Labels, hints, units. 6.4 / 6.5                                                    |
| `--text-disabled`      | `#787B82`           | `#8E9197`           | Disabled only                                                                      |
| `--accent`             | `#2B6BD0`           | `#2B6BD0`           | Primary button, active tab underline, focus ring, checked controls. White text 5.1 |
| `--accent-hover`       | `#2560C0`           | `#2560C0`           | Primary button hover                                                               |
| `--accent-pressed`     | `#235AB5`           | `#235AB5`           | Primary button pressed                                                             |
| `--accent-text`        | `#7FAEF5`           | `#1F5FC2`           | Links, active tool icon and label, selected segment. 6.9 / 5.6                     |
| `--on-accent`          | `#FFFFFF`           | `#FFFFFF`           | Text and icons on the accent                                                       |
| `--success`            | `#4FB87A`           | `#237A48`           | "gültig", "in Toleranz". 6.3 / 4.9                                                 |
| `--warning`            | `#D9A441`           | `#8A5E0A`           | Warnings. 6.9 / 5.2                                                                |
| `--error`              | `#E5645A`           | `#C23A30`           | Errors. 4.7 / 4.9                                                                  |
| `--viewport-bg`        | `#2A2C30`           | `#D6D9DD`           | Flat viewport background                                                           |
| `--overlay-scrim`      | `rgb(0 0 0 / 0.40)` | `rgb(0 0 0 / 0.25)` | Behind modal dialogs                                                               |

Rules:

- Semantic colours (`--success`, `--warning`, `--error`) colour text and icons only, never large
  areas. An error message is an icon plus normal text, not a red box.
- Viewport colours (section 6) are fixed values in `viewport/palette.ts`; they are chosen for the
  3D scene and do not change with the UI theme except where noted.
- When the theme changes, the renderer updates the `titleBarOverlay` colours (`--bg-app`,
  `--text`) through `window.m2c.window.setTitleBarColors`.

### 2.2 Typography

Font stack: `"Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif`. No web fonts.
Numbers use `font-variant-numeric: tabular-nums` in fields, tables, the legend and the status bar.

| Role                                                        | Size / line height | Weight               |
| ----------------------------------------------------------- | ------------------ | -------------------- |
| Body, labels, tree rows, inputs, buttons, menus, status bar | 12 / 16 px         | 400                  |
| Panel section header                                        | 12 / 16 px         | 600                  |
| Panel header (tool name), dialog body                       | 13 / 18 px         | 600 header, 400 body |
| Dialog title, empty-state title                             | 14 / 20 px         | 600                  |
| View cube face labels (only exception below 12 px)          | 11 px              | 600                  |

Sentence case everywhere. No all-caps labels, no letter-spacing adjustments, no weights above 600,
no italics for emphasis.

### 2.3 Spacing and size

Spacing scale in px: **2, 4, 6, 8, 12, 16, 24, 32**. No other values.

| Element                                | Size                       |
| -------------------------------------- | -------------------------- |
| Title bar                              | 32 px                      |
| Tool row                               | 40 px, buttons 28 px       |
| Status bar                             | 24 px                      |
| Inputs, buttons, tree rows, menu items | 24 px high                 |
| Panel header / footer                  | 32 px / 40 px              |
| Panel padding                          | 12 px                      |
| Gap between property rows / sections   | 4 px / 8 px                |
| Left panel (Projekt)                   | 260 px default, 200–420 px |
| Right panel (Eigenschaften)            | 300 px default, 260–440 px |
| Minimum window                         | 1280 × 720                 |

### 2.4 Shape, borders, elevation

- Borders are always 1 px.
- Radius 4 px on buttons, inputs, menus, popovers, tooltips, dialogs and the legend. Radius 0 on
  docked panels, the title bar, the tool row and the status bar. Nothing larger than 4 px, no pills,
  no circles except slider thumbs and radio buttons.
- Shadows only on floating surfaces (menus, popovers, tooltips, dialogs):
  `0 2px 8px rgb(0 0 0 / 0.24)` dark, `/ 0.12` light. No blur effects, no glows, no inner shadows.
- Splitters: a 1 px `--border` line with a 5 px hit area; `--border-strong` on hover.

### 2.5 Motion

- No animation on panels, hover, selection or layout.
- Menus and tooltips fade in over 100 ms.
- Camera transitions to standard views take 250 ms (ease-out).
- `prefers-reduced-motion: reduce` makes all of the above instant.
- No spinners. Running work shows a progress bar and, above 10 s, the elapsed time.

### 2.6 Icons

`lucide-react`, 16 px, default 2 px stroke, colour `currentColor`. Icon-only buttons always have a
tooltip and an `aria-label`. Custom icons follow the lucide grid (24 × 24 viewBox, 2 px stroke,
round caps and joins, no fill) and live in `src/renderer/ui/icons/`.

| Function                            | Icon                                                     |
| ----------------------------------- | -------------------------------------------------------- |
| Import, open, save, export          | `file-input`, `folder-open`, `save`, `file-output`       |
| Undo, redo                          | `undo-2`, `redo-2`                                       |
| Brush, smart select, lasso, box     | `paintbrush`, `wand`, `lasso`, `square-dashed`           |
| Grow, shrink selection              | `expand`, `shrink`                                       |
| Segmentation, regions               | `shapes`                                                 |
| Plane, sphere                       | custom: parallelogram; circle with equator ellipse       |
| Cylinder, cone, torus               | `cylinder`, `cone`, `torus`                              |
| Reference geometry                  | custom: plane with axis                                  |
| Section, sketch, line/arc           | `slice`, `pen-tool`, `spline`                            |
| Extrude, revolve                    | `arrow-up-from-dot`, `rotate-cw-square`                  |
| Unite, subtract, intersect          | `squares-unite`, `squares-subtract`, `squares-intersect` |
| Fillet, split body                  | custom: rounded corner; `scissors`                       |
| Deviation, measure                  | `gauge`, `ruler`                                         |
| Align                               | `axis-3d`                                                |
| Computed / fixed value              | `lock-open`, `lock`                                      |
| Visibility, fit view, fit selection | `eye`, `eye-off`, `maximize-2`, `focus`                  |
| States                              | `check`, `triangle-alert`, `circle-alert`, `info`        |
| Tree                                | `chevron-right`, `chevron-down`                          |

Never use `sparkles`, `wand-sparkles`, `bot`, `brain` or any "AI" symbol.

---

## 3. Layout

### 3.1 Window regions

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ ▣ Datei Bearbeiten Ansicht Hilfe │ Vorbereiten  Ausrichten  Modellieren  Prüfen    │ ─ ☐ ✕ │ 32
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ ↶ ↷ │ Pinsel Flächenauswahl Lasso ▭ │ Segmentieren │ Form einpassen │ Skizze │ Extrusion … ‖ ⌂ ▾ ◫ ▾ │ 40
├───────────────┬──────────────────────────────────────────────────────────────┬───────────────┤
│ Projekt       │                                                  ┌────────┐  │ Form einpassen│
│ ▾ Scan        │                                                  │ Würfel │  │             ? │
│ ▸ Bereiche 12 │                                                  └────────┘  ├───────────────┤
│ ▸ Körper 1    │                                                  ┌──┐        │ Eingabe       │
│ ▸ Ursprung    │                    Ansichtsfenster (Z oben)      │  │Legende │ Parameter     │
│ ▾ Verlauf     │                                                  │  │        │ Ergebnis      │
│   Ausrichtung │                                                  └──┘        │ So geht's     │
│   Zylinder 1  │  ┌Achsen┐                                                    ├───────────────┤
│   Skizze 1    │  └──────┘                                                    │ OK  Abbrechen │
├───────────────┴──────────────────────────────────────────────────────────────┴───────────────┤
│ Linke Maustaste: hinzufügen · Strg: entfernen │ 12.408 ausgewählt │ 1.204.566 Dreiecke │ Toleranz ±0,100 mm │ 24
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

The top chrome is exactly 72 px. There are no floating toolbars and no toasts.

### 3.2 Title bar, stage tabs, tool row

**Title bar (32 px, `--bg-app`).** Frameless window; the Windows caption buttons stay native
(`titleBarOverlay`). From the left: 16 px app icon, the menus _Datei, Bearbeiten, Ansicht, Hilfe_
(our own menus with shortcut hints), a 1 px divider, the four stage tabs. The rest is drag area.
The document name appears in the window title (taskbar) and as the tree root, not in the bar.

**Stage tabs.** _Vorbereiten · Ausrichten · Modellieren · Prüfen_. Text only, 12 px,
`--text-secondary`; hover `--text`; the active tab is `--text` with a 2 px `--accent` underline.
Stages filter the tool row. They are not a wizard: the tree, viewport, selection and active
document stay as they are when switching, and there are no step numbers or completion badges. The
last stage is remembered per project. Importing a scan is not a stage: it lives in _Datei_ and the
empty state. Exporting is the primary action of _Prüfen_.

**Tool row (40 px, `--bg-app`).** Undo and redo at the far left, then the tool groups of the
active stage separated by 1 px dividers, then the view group at the far right in every stage.
Tools marked primary show icon and label; the others are icon-only with a tooltip (name and
shortcut). When space runs out, the rightmost groups collapse into a _Mehr_ menu; the view group
never collapses. While a selection mode is active, its options (brush size, _Nur sichtbare_,
_Durch das Teil_) appear right after the selection group.

| Stage (DE / EN)       | Groups and tools, left to right                                                                                                                                                                                                            |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Vorbereiten / Prepare | selection: Pinsel, Flächenauswahl, Lasso, Rechteck · mesh: **Reparieren**, Kleine Teile entfernen, Löcher füllen, Reduzieren, Glätten, Auswahl löschen · analysis: Scaninformationen                                                       |
| Ausrichten / Align    | selection · regions: Segmentieren · align: **Automatisch ausrichten**, **An Flächen ausrichten**, Ausrichtung zurücksetzen                                                                                                                 |
| Modellieren / Model   | selection · regions: **Segmentieren** · fit: **Form einpassen** · reference: Hilfsgeometrie · sketch: **Skizze** · solid: **Extrusion**, **Drehung**, Grundkörper, Körper teilen, Kombinieren, Verrundung · freeform: Freiformfläche, Loft |
| Prüfen / Inspect      | inspect: **Messen**, **Abweichung**, Bericht · export: **STEP exportieren …**, STL exportieren …                                                                                                                                           |
| every stage (right)   | view: Alles zeigen, Standardansichten ▾, Orthografisch/Perspektive, Sichtbarkeit (Scan / Körper / beide), Schnittebene, Darstellung ▾                                                                                                      |

Bold = primary (icon + label). Tool buttons: 28 px high, 4 px radius, transparent at rest,
`--bg-hover` on hover, `--bg-pressed` while pressed, `--bg-selected` with `--accent-text` icon and
label while the tool is active. Disabled tools show `--text-disabled` and a tooltip with the
reason. Tools that are not implemented yet are shown disabled with "Noch nicht verfügbar" in
development builds and are hidden in release builds.

In sketch mode the tool row shows only the sketch tools (7.2); finishing the sketch is a button in
the panel footer, not in the tool row.

### 3.3 Project panel (left)

Title "Projekt" in a 32 px header. One tree that is object list and history at once (5.5).
`Ctrl+B` hides the panel.

### 3.4 Properties panel (right)

`Ctrl+Alt+B` hides the panel. Three states:

1. **A panel tool is open:** header (32 px: tool icon, tool name 13 px semibold, help button
   `F1`), collapsible sections _Eingabe_, _Parameter_, _Optionen_, _Ergebnis_ and _So geht's_
   (2–4 sentences, collapsed after the first use of the tool), footer (40 px, sticky, 1 px top
   border) with **OK** (primary) and **Abbrechen** right-aligned in Windows order and, for tools
   where repeating makes sense, _Anwenden_ left-aligned.
2. **An object is selected:** its properties (feature summary and status, body volume and validity,
   region type and RMS). Values of fitted shapes are editable here; editing creates a feature
   edit.
3. **Neither:** the empty state (5.8).

### 3.5 Status bar (24 px, `--bg-app`)

Left: the context hint for the active tool and held modifiers (7.3), or the last message for 6 s.
Right, in fixed order, separated by 1 px dividers: selection count, triangle count, tolerance,
deviation summary (when shown), and the job area.

- **Tolerance** ("Toleranz ±0,100 mm") is a button. It opens a small popover with the value, the
  scan noise and "Vorschlag aus Scanrauschen: ±0,100 mm". This is the only place where the project
  tolerance changes; settings hold no default tolerance.
- **Job area:** nothing while idle; "Berechnung läuft …" with a progress bar and a cancel button
  while a job runs (5.7); "Rechenprozess beendet" with _Neu starten_ after a crash.

Clicking the message area opens the _Meldungen_ list.

### 3.6 Viewport overlays

Only these, anchored to corners, never overlapping each other:

- View cube, top right, 88 px, 8 px from the edges.
- Deviation legend, right edge below the view cube (only while the deviation display is on).
- Axis triad, bottom left, 48 px.
- Sketch mode: a single line of text top left, "Skizze 1 · Ebene XY + 5,000 mm", `--text-secondary`.

Messages never cover the viewport; they go to the status bar.

---

## 4. Components

All components live in `src/renderer/ui/`, one folder per component with a CSS module. They are
the only place where tokens turn into pixels. Menus, context menus, tooltips, sliders and dialogs
use Radix primitives (unstyled) for keyboard and ARIA behaviour.

| Component             | Specification                                                                                                                                                                                                                                                                                                                                                                                                               |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Button`              | 24 px, padding 0 12 px, radius 4, 12 px text. Variants: **primary** (`--accent` fill, `--on-accent` text; one per panel or dialog), **secondary** (transparent, 1 px `--border-strong`, `--text`), **ghost** (no border, `--text`; for inline actions like _Ordner öffnen_). Hover and pressed from tokens. Disabled: `--text-disabled` text; a disabled primary button uses the `--bg-pressed` fill instead of the accent. |
| `IconButton`          | 24 × 24, 16 px icon, transparent, hover `--bg-hover`. Tooltip and `aria-label` required. Toggle variant uses `--bg-pressed` when on.                                                                                                                                                                                                                                                                                        |
| `ToolButton`          | 28 px tool-row button (3.2). Shows label only when primary.                                                                                                                                                                                                                                                                                                                                                                 |
| `StageTab`            | 3.2. `role="tab"` inside `role="tablist"`; arrow keys move between tabs.                                                                                                                                                                                                                                                                                                                                                    |
| `Menu`, `ContextMenu` | `--bg-raised`, 1 px `--border`, radius 4, shadow, 4 px padding, min width 200 px. Items 24 px: 16 px icon slot (empty if no icon), label, shortcut right-aligned in `--text-secondary`. Separators 1 px `--border-subtle` with 4 px margin. Submenus with `chevron-right`. Disabled items stay visible.                                                                                                                     |
| `Tooltip`             | 500 ms delay, `--bg-raised`, 1 px `--border`, radius 4, 12 px, max width 280 px. Content: name, then shortcut in `--text-secondary`; optionally one sentence.                                                                                                                                                                                                                                                               |
| `TextField`           | 24 px, `--bg-input`, 1 px `--border-strong`, radius 4, padding 0 6 px. Focus: 2 px accent outline inside. Invalid: `--error` border and a 12 px message below.                                                                                                                                                                                                                                                              |
| `NumberField`         | `TextField` with right-aligned tabular numbers and the unit as a suffix inside the field in `--text-secondary`. Accepts simple expressions (`25,4/2`) and a unit suffix (`1 in`). Separators follow the UI language (below). Formats on blur with 3 decimals for mm, 2 for degrees, none for counts. Arrow up/down step, `Shift` × 10. The mouse wheel never changes a value.                                               |
| `FitValueField`       | `NumberField` with a 20 px toggle on its left: `lock-open` = _Berechnet_ (value computed by the fit, shown in `--text-secondary`), `lock` = _Fest_ (value fixed, shown in `--text`). Typing a value switches to _Fest_. Tooltip explains the state.                                                                                                                                                                         |
| `Select`              | Native `<select>` styled like `TextField` with a chevron; the popup is the platform list.                                                                                                                                                                                                                                                                                                                                   |
| `Checkbox`            | 14 px box, radius 2, 1 px `--border-strong`; checked: `--accent` fill with a white check. Label 12 px to the right, the whole row clickable. Checkbox rows use the full panel width, not the label column.                                                                                                                                                                                                                  |
| `RadioGroup`          | 14 px circles; used only for 2–3 mutually exclusive options that need descriptions.                                                                                                                                                                                                                                                                                                                                         |
| `SegmentedControl`    | 24 px, 1 px `--border-strong`, radius 4, segments separated by 1 px. Selected segment `--bg-selected` with `--accent-text`. Used for operation (_Neuer Körper, Vereinigen, Abziehen, Schnittmenge_) and direction.                                                                                                                                                                                                          |
| `Slider`              | Track 2 px `--border-strong`, filled part `--accent`, thumb 12 px circle `--bg-raised` with 1 px `--accent` border. Always paired with a `NumberField` showing the exact value.                                                                                                                                                                                                                                             |
| `Tree`                | 5.5. `role="tree"`, rows 24 px, indent 16 px, chevron, 16 px type icon, label, secondary text in `--text-secondary`, trailing status icon and eye toggle (visible on hover, always visible when hidden). Selected row `--bg-selected`, unfocused selection `--bg-selected-subtle`.                                                                                                                                          |
| `PanelSection`        | Header 24 px: chevron, title 12 px semibold. Content padding 0 12 px 8 px. Collapsed state is remembered per tool (settings `tools` namespace).                                                                                                                                                                                                                                                                             |
| `PropertyRow`         | Label column 45 % in `--text-secondary`, control column 55 %. Labels wrap to a second line instead of ending in an ellipsis. Read-only values right-aligned, tabular.                                                                                                                                                                                                                                                       |
| `ResultList`          | Key/value rows for results (scan noise, RMS, max, share in tolerance, count). Values tabular with unit. The verdict row carries a 12 px `check` or `triangle-alert` icon in `--success`/`--warning`.                                                                                                                                                                                                                        |
| `SnapList`            | One row per applied snap: what snapped, the design value, the measurement in `--text-secondary` ("Radius 8,000 mm · gemessen 7,987 ± 0,012"), and an `x` icon button that removes the snap and re-runs the fit.                                                                                                                                                                                                             |
| `InlineMessage`       | 16 px severity icon (`info`, `triangle-alert`, `circle-alert`) in the semantic colour, then text in `--text`. Optional _Details_ disclosure with technical text in 12 px monospace (`Cascadia Mono`, `Consolas`).                                                                                                                                                                                                           |
| `ProgressBar`         | 80 px × 4 px in the status bar, `--border` track, `--accent` fill, radius 0. **Determinate** when the job reports a fraction; **indeterminate** (a full bar at 45 % opacity, not animated) while the kernel runs a native step that cannot report progress. Beyond 10 s the elapsed time appears next to it.                                                                                                                |
| `Dialog`              | Width 400 px (or 560 px for lists). `--bg-raised`, 1 px `--border`, radius 4, shadow, scrim `--overlay-scrim` without blur. Title 14 px semibold, body 13 px, footer right-aligned: primary, then _Abbrechen_. `Esc` cancels; focus is trapped.                                                                                                                                                                             |
| `Kbd`                 | Shortcut text in `--text-secondary`, no box, `Strg+Umschalt+I` / `Ctrl+Shift+I` by locale.                                                                                                                                                                                                                                                                                                                                  |

**Number input rules.** In German, `,` is the decimal separator. In count fields ("Reduzieren
auf"), `.` groups thousands, so `200.000` is two hundred thousand. In length and angle fields, `.`
is also accepted as a decimal point, except when the input is ambiguous (`1.000`, `12.500`): the
field then shows "Mehrdeutig: Dezimalstellen mit Komma eingeben (z. B. 1,25)." and keeps the
old value. English
uses `.` for decimals and `,` for grouping.

Every interactive component shows a focus ring on `:focus-visible` only:
`outline: 2px solid var(--accent); outline-offset: -2px`.

---

## 5. Interaction patterns

### 5.1 Tool life cycle

1. **Activate** with the tool row, a shortcut, or a double-click on a feature in the tree (edit).
   One panel tool at a time. If the open tool's draft has changed and the tool asks before
   discarding (sketch, fillet edge picks, alignment inputs), switching shows "Änderungen an
   Skizze 1 verwerfen?" with _Verwerfen_ and _Weiter bearbeiten_. Other tools close without
   asking.
2. **Input.** _Eingabe_ lists required inputs with their state: "Auswahl: 12.408 Dreiecke" or
   "Auswahl fehlt – mindestens 200 Dreiecke". Selection modes (brush, smart select, lasso,
   rectangle) stay usable while the panel is open; the preview re-runs when the selection changes.
   OK stays disabled until inputs are valid.
3. **Preview.** The kernel recomputes 150 ms after the last change. While computing, the previous
   preview is drawn at 50 % opacity and _Ergebnis_ shows "Wird berechnet …". Newer requests
   replace older ones.
4. **Commit** with OK or `Enter`: the feature is added and the tool closes. _Anwenden_ or
   `Shift+Enter` commits and keeps the tool open with the same parameters.
5. **Cancel.** The first `Esc` aborts a gesture in progress (open lasso, drag); the second `Esc`
   cancels the tool. `Esc` never commits anything, in any tool or mode.
6. **Undo inside a tool.** While a tool is open, `Ctrl+Z` undoes the last change to its draft or
   to the selection. It never reaches past the open tool into committed history; after the tool
   closes, `Ctrl+Z` undoes revisions again.
7. **Edit.** The tool opens with the stored parameters and "Bearbeiten: Extrusion 2" in the
   header. A fit's stored triangles become the working selection while it is edited; the previous
   selection returns when the tool closes. On OK, dependent features rebuild. Failures show in the
   tree and in the feature's properties (5.6).

Selection modes have no OK; they stay active until another selection mode is chosen or `Esc` is
pressed with no gesture in progress.

### 5.2 Parameters and numeric input

- Parameters are `PropertyRow`s: label, then control. Units always visible in the field.
- Fitted values use `FitValueField` (_Berechnet_ / _Fest_). Fixing a value re-runs the fit with
  that constraint. Values never jump silently: a fixed value changes only when the user edits it.
- Direction parameters offer _Parallel zu X / Y / Z_ and _Senkrecht zu …_ next to the field.
- Snapping results appear as a `SnapList` under _Ergebnis_, in fits and in sketches: "Achse
  parallel zu Z", "Radius 8,000 mm · gemessen 7,987 ± 0,012", "Abstand zum Ursprung 40,000 mm",
  "Gleiche Radien (3)", "Lochkreis ⌀ 60,000 mm, 4 × 90°". Each row can be removed.
- Snap steps follow the project setting _Fangwerte: metrisch / Zoll_ (in the tolerance popover,
  3.5). Inch steps are 1/4 … 1/64 in; values are still shown in millimetres.
- Default values that the scan can answer are pre-filled from it: the extrude distance from the
  scan extent along the direction, the fillet radius with _Radius aus Scan_.

### 5.3 Live results and pass/fail

Every fitting and modelling tool shows the same result block:

```
Ergebnis
  Scanrauschen       0,036 mm
  RMS                0,021 mm
  Maximum            0,094 mm
  In Toleranz         98,7 %   ✓
  Dreiecke           12.408
```

- **One verdict rule:** the result passes when at least 95 % of the used triangles lie within the
  project tolerance. Pass: `check` in `--success`. Otherwise `triangle-alert` in `--warning` and
  the matching line: "Nur 82,4 % der Dreiecke liegen in der Toleranz ±0,100 mm. Auswahl prüfen
  oder anderen Typ wählen." RMS and maximum are information, not the verdict.
- The scan noise is shown in every result block, so the user can see when the tolerance is
  tighter than the scanner allows.
- The scan triangles used by the tool are coloured pass/fail in the viewport (6.3).
- For automatic type choice the alternatives are listed with their RMS; clicking one selects it.

### 5.4 Selection feedback

- The working selection survives tool changes; its count is always in the status bar.
- After a fit is committed, its triangles are removed from the working selection, so the next fit
  starts clean. _Einstellungen → Auswahl nach dem Einpassen leeren_ turns this off.
- Brush and smart select show their effect before the click: brush as a cursor ring, smart select
  as a hover preview (6.3).
- Visible-only selection (_Nur sichtbare_) is on by default and remembered. Lasso and rectangle
  offer _Durch das Teil_ for cleanup.

### 5.5 Project tree

```
halterung                        project root (file name)
  Scan  halterung_scan.stl       1.204.566 Dreiecke
    Repariert
    Reduziert auf 1.000.000
  Bereiche (12)                  collapsed by default
    Ebenen (7)
      Bereich 1                  plane icon · "Ebene, RMS 0,021 mm"
    Zylinder (3)
      Bereich 4
  Körper (1)
    Körper 1
  Ursprung
    XY  YZ  XZ  Achsen
  Verlauf
    Ausrichtung
    Zylinder 1
    Ebene 1 (Hilfsgeometrie)
    Skizze 1                     triangle-alert: "Skizze weicht vom Scan ab"
    Extrusion 1
    Verrundung 1                 circle-alert when it failed
```

- Groups without content are hidden (_Körper_ until the first body exists).
- Default names are the translated type plus a per-type number ("Zylinder 2"). Regions are named
  "Bereich 7"; their type is the icon and the secondary text, never part of the name, so a region
  and a fit never share a name. Renamed items keep their name in every language.
- _Bereiche_ is collapsed by default and grouped by type; a filter _Nur nicht verwendete_ hides
  regions already used by a feature.
- Context menu: _Bearbeiten, Umbenennen (F2), Ausblenden/Einblenden (H), Isolieren, Unterdrücken,
  Löschen (Entf)_, plus entries contributed by commands (region actions).
- Deleting an item with dependents asks: "Skizze 1 wird von Extrusion 1 und Verrundung 1
  verwendet. Alle drei löschen?" with _Löschen_ and _Abbrechen_.
- Suppressed features show their label in `--text-disabled`. Skipped features (an input failed)
  show `--text-disabled` and the reason in their properties.
- A sketch whose entities no longer match the current section (for example after a new alignment)
  shows a warning: "Skizze weicht vom Scan ab (max. 0,800 mm)" with _Neu anpassen_ in its
  properties.
- Hovering a row highlights the object in the viewport and vice versa (hover tint). Selection is
  synchronised both ways.

### 5.6 Messages and errors

Pattern: **what failed: why. What to do.** The last part is optional. Technical details (codes,
traceback, file paths) go into the _Details_ disclosure and the log, never into the main line.

| Where                             | What                                                                                                               |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Properties panel, inline          | Everything about the active tool                                                                                   |
| Tree icon + feature properties    | Failed or warning features                                                                                         |
| Status bar, 6 s, then _Meldungen_ | Confirmations: saved, exported, restored                                                                           |
| Modal dialog                      | Only decisions that can lose data: unsaved changes, discard a changed tool draft, delete with dependents, recovery |

### 5.7 Long operations and the computing process

- Every job that takes longer than 400 ms shows a progress bar and a cancel button in the status
  bar; the viewport stays interactive. Above 10 s the elapsed time appears next to the bar.
- While the kernel runs a step that cannot report progress, the bar is indeterminate.
- Cancelling frees the UI at once. If the computing process has not stopped after 3 s, the status
  bar shows "Rechenprozess reagiert nicht" with _Neu starten_.
- Long jobs (segmentation, deviation map, reduction) run alone; while one runs, tools and undo are
  disabled and their tooltips say why.
- Nothing is shown while the computing process is idle. States that need attention: "Rechenprozess
  startet …", "Rechenprozess beendet" (in `--error`, with _Neu starten_). After a restart the
  project is exactly as it was at the last completed step, and the status bar says so.

### 5.8 Empty states

Text only, left-aligned, no illustrations.

| Place                        | Content                                                                                                                                                                                                                                                                                                                          |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Viewport, no project         | 360 px column at the left third of the viewport: title "Kein Scan geladen" (14 px semibold); line "STL-, OBJ- oder PLY-Datei importieren oder hierher ziehen."; buttons **Scan importieren …**, _Projekt öffnen …_, _Beispiel öffnen_; list "Zuletzt verwendet" (at most 5 rows: file name, folder in `--text-secondary`, date). |
| Properties, nothing selected | "Keine Auswahl" / "Objekt im Projektbaum oder im Ansichtsfenster auswählen."                                                                                                                                                                                                                                                     |
| Fit tool without input       | "Dreiecke mit Pinsel oder Flächenauswahl markieren (mindestens 200)."                                                                                                                                                                                                                                                            |
| Deviation without body       | Tool disabled; tooltip "Kein Körper zum Vergleichen vorhanden."                                                                                                                                                                                                                                                                  |

### 5.9 Dialogs and confirmations

Modal dialogs are rare (5.6). Buttons name the action ("Speichern", "Nicht speichern",
"Verwerfen", "Abbrechen"), never "Ja/Nein". The destructive button is secondary, not red.

### 5.10 Help

- Each tool has a _So geht's_ section (3.4) with 2–4 sentences from its locale file: what to
  select, what the tool computes, what to check before OK.
- `F1` opens the local help page of the active tool in the default browser; the pages ship with
  the app, so help works offline.
- The getting-started guide walks through the bundled example bracket from import to STEP.

---

## 6. Viewport

Colours in this section are defined in `src/renderer/viewport/palette.ts`, the only file besides
`tokens.css` that contains colour literals; values written as `--token` come from `tokens.css`.

### 6.1 Scene

- Z up, right-handed, millimetres. Orthographic by default, perspective with `P`.
- Flat background `--viewport-bg`; no gradient, no grid by default. The optional ground grid
  (_Ansicht → Raster_) uses steps of 1, 2 or 5 × 10ⁿ.
- Lighting: `HemisphereLight` (sky `#FFFFFF`, ground `#50545C`, intensity 0.9) and a headlight
  (`DirectionalLight` 1.4, attached to the camera, offset up and left). No shadows, no
  environment maps, no tone-mapping effects.

### 6.2 Scan material and display modes

- Scan: `MeshStandardMaterial`, colour `#B8BCC2`, roughness 0.55, metalness 0, both sides.
  **Back faces `#8A6F6A`** (muted brown-red) to reveal holes, open borders and flipped triangles.
- Display modes (_Ansicht → Darstellung_): _Schattiert_; _Schattiert + Kanten_ (triangle edges in
  `--text` at 12 % alpha, only below 500,000 triangles); _Flach_ (facets); _Röntgen_ (`X`, scan at
  30 % opacity, no depth write); _Bereiche_ (region colours); _Abweichung_ (colour map, toggled
  with `D`); _Abgedeckt_ (P1: triangles within tolerance of any body or construction surface
  tinted, so unmodelled areas stand out).
- Visibility (`Space` cycles): _Scan und Körper_, _nur Scan_, _nur Körper_.

### 6.3 Selection, hover, pass/fail

| State                                                  | Look                                                               |
| ------------------------------------------------------ | ------------------------------------------------------------------ |
| Selected triangles                                     | Base colour mixed 55 % with `#3F87EE`                              |
| Hover pre-highlight (smart select preview, tree hover) | Same colour at 25 %                                                |
| Hidden triangles                                       | Not drawn                                                          |
| Pass (in tolerance)                                    | `#4DAF63` mixed 70 %                                               |
| Fail (outside tolerance)                               | `#D24B35` mixed 70 %                                               |
| Fail beyond 3 × tolerance                              | `#7A1F14` mixed 70 %                                               |
| Brush cursor                                           | Two concentric 1 px rings, light (`#FFFFFF`) over dark (`#1C1D20`) |

### 6.4 Region palette

Ten muted colours (OKLCH lightness 0.66–0.80, chroma ≤ 0.10). Hues 225°–290° are excluded so no
region looks like the selection blue.

| #   | Colour    | #   | Colour    |
| --- | --------- | --- | --------- |
| 1   | `#C87979` | 6   | `#669E9A` |
| 2   | `#DE9871` | 7   | `#6CCDEA` |
| 3   | `#A59145` | 8   | `#9786C9` |
| 4   | `#CDC072` | 9   | `#C398D6` |
| 5   | `#68BF9B` | 10  | `#F2A3C1` |

- The kernel assigns palette indices so that adjacent regions differ (largest region first, each
  region takes the colour farthest from its coloured neighbours). A region keeps its colour when
  it survives a re-segmentation.
- Region borders: 1 px lines `#1C1D20` at 60 % in both themes, so neighbours stay distinguishable
  without relying on colour.
- Unassigned triangles keep the scan colour. Colour never encodes the region type; the type is the
  tree icon.

### 6.5 Bodies, construction, sketches, handles

| Display style                      | Look                                                                                                                       |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `body`                             | `#C4A57A` (warm sand), roughness 0.45, metalness 0; polygon offset in front of the scan, so no z-fighting                  |
| `bodyEdges`                        | 1 px lines `#2A2723` (dark theme) / `#3A3630` (light theme)                                                                |
| `previewBody`                      | Body colour; previous preview at 50 % while computing                                                                      |
| `construction`                     | Amber `#D39B2A` fill at 20 % opacity, drawn with depth offset                                                              |
| `constructionEdges`                | Amber `#D39B2A` at 100 %, 1 px                                                                                             |
| `patch`                            | Amber `#D39B2A` at 35 % with 1 px iso-lines every 10 % of the parameter range                                              |
| `sketch`                           | 2 px lines in `--text`; selected entity `--accent-text`; pass/fail `#4DAF63` / `#D24B35`                                   |
| `sketchPoints`, `sectionPoints`    | 3 px dots, `#4DAF63` while choosing the section, `--text-secondary` in sketch mode                                         |
| `section`                          | 1.5 px line `#4DAF63`                                                                                                      |
| Origin planes and axes             | X `#D2524A`, Y `#4E9F55`, Z `#3C78D8`; planes as outlines only                                                             |
| Handles (arrow, arc, plane, point) | Axis colour for axis-bound handles, otherwise `--text`; active handle `#3F87EE`; 1 px outline in `--bg-app` for legibility |
| Section plane gizmo                | 1 px `--accent` rectangle, normal arrow, two rotation arcs; hatched body caps (P1) in the body colour at 45°               |

Sketch mode: the camera turns normal to the sketch plane (250 ms), orbit is locked (`Alt` + right
drag unlocks temporarily), the scan is ghosted to 15 % opacity, section points are drawn as dots,
and the tool row shows only the sketch tools. The panel footer holds **Skizze beenden** (primary)
and _Abbrechen_.

### 6.6 Deviation colour map and legend

Sign convention: d is the signed distance from a scan point to the nearest body surface.
**Positive: the scan point lies outside the body** (excess material on the real part); negative:
inside (missing material). The legend tooltip and the user docs state this.

The map is discrete with 3 steps per side plus the tolerance band. There are two schemes and no
other variants.

| Band                             | Standard      | Colour-blind safe (_Farbfehlsichtigkeit_) |
| -------------------------------- | ------------- | ----------------------------------------- |
| below −max (out of range)        | `#1E2F66`     | `#08306B`                                 |
| −max … −⅔ max                    | `#2E56B8`     | `#2166AC`                                 |
| −⅔ max … −⅓ max                  | `#3C8DDB`     | `#4393C3`                                 |
| −⅓ max … −tol                    | `#5CC3D6`     | `#92C5DE`                                 |
| **−tol … +tol**                  | **`#4DAF63`** | **`#E3E3E3`**                             |
| +tol … +⅓ max                    | `#E6CF4F`     | `#F4A582`                                 |
| +⅓ max … +⅔ max                  | `#EC9A3A`     | `#D6604D`                                 |
| +⅔ max … +max                    | `#D24B35`     | `#B2182B`                                 |
| above +max (out of range)        | `#7A1F14`     | `#67001F`                                 |
| no data (beyond search distance) | `#8C9096`     | `#8C9096`                                 |

Neighbouring standard bands are at least 0.12 apart in OKLab. The standard map is not safe for
protanopia (two bands come within 0.04), hence the second scheme (ColorBrewer RdBu based, ≥ 0.10
between bands under deutan and protan simulation). _Skalenbereich automatisch_ uses the 99th
percentile of |d| rounded to 1, 2 or 5 × 10ⁿ. The band maths lives in one module
(`lib/deviationBands.ts`) used by the legend, the viewport and the statistics.

**Legend** (right edge below the view cube; `--bg-raised`, 1 px `--border`, radius 4, solid):

```
Abweichung [mm]
 ┌──┐ +0,50
 │██│ +0,33
 │██│ +0,17
 │██│ +0,10  ┐
 │██│        │ Toleranz ±0,10
 │██│ −0,10  ┘
 │██│ −0,17
 │██│ −0,33
 └──┘ −0,50
 ██ außerhalb   ██ keine Daten
 Mittel  +0,003   σ 0,046
 RMS      0,046   97,7 % in Toleranz
 Max +0,372 / −0,280
```

- Bar 12 × 240 px, positive at the top; tick labels at every band boundary, 12 px tabular, sign
  always shown. The tolerance band is marked with a 1 px bracket.
- The legend can collapse to the bar only. The value under the cursor appears as a small label
  next to the cursor (`--bg-raised`, 12 px).
- Implementation: per-vertex deviation values and a 1D colour texture with nearest filtering;
  tolerance, range and scheme are uniforms, so changing them never rebuilds geometry.

### 6.7 View cube and axis triad

- View cube 88 px: faces _Vorne, Hinten, Links, Rechts, Oben, Unten_ (EN _Front, Back, Left, Right,
  Top, Bottom_), 11 px semibold. Faces `--bg-raised`, edges `--border-strong`, hover `--bg-hover`.
  Faces, edges and corners are clickable (26 views); dragging on the cube orbits the view, which
  helps on touchpads. A home button above goes to the isometric view; two small arrows below rotate
  the view by 90° in the screen plane.
- Axis triad 48 px bottom left in the axis colours with X/Y/Z labels at 12 px.

---

## 7. Mouse and keyboard

### 7.1 Mouse

The left button is reserved for selecting and painting, so navigation uses the right and middle
buttons (as in established scan-to-CAD tools). There is one mapping; _Einstellungen → Navigation_
offers only the inverted wheel direction.

| Action       | Mouse                                  |
| ------------ | -------------------------------------- |
| Orbit        | Right drag; drag on the view cube      |
| Pan          | Middle drag, `Shift` + right drag      |
| Zoom         | Wheel (to cursor), `Ctrl` + right drag |
| Fit all      | Middle double-click                    |
| Context menu | Right click without drag (< 4 px)      |

The orbit pivot is the scan point under the cursor at mouse-down, falling back to the bounding-box
centre.

### 7.2 Keyboard

Single-letter shortcuts work only while the viewport or the tree has focus, never in text fields.
All bindings come from the command registry; menus, tooltips and the shortcut help (`Ctrl+/`) are
generated from it.

| Area        | Keys                                         | Action                                                          |
| ----------- | -------------------------------------------- | --------------------------------------------------------------- |
| File        | `Ctrl+N`, `Ctrl+O`, `Ctrl+S`, `Ctrl+Shift+S` | New, open, save, save as                                        |
|             | `Ctrl+I`, `Ctrl+E`                           | Import scan, export STEP                                        |
| Edit        | `Ctrl+Z`, `Ctrl+Y` / `Ctrl+Shift+Z`          | Undo, redo (inside a tool: its draft, 5.1)                      |
|             | `Entf`, `F2`                                 | Delete, rename (tree); delete triangles (viewport, Vorbereiten) |
| Tool        | `Enter`, `Shift+Enter`, `Esc`                | OK, apply, cancel (`Esc` never commits)                         |
|             | `F1`                                         | Help for the active tool                                        |
| View        | `F`, `Shift+F`                               | Fit all, fit selection                                          |
|             | `1`–`6`, `0`                                 | Front, back, left, right, top, bottom; isometric                |
|             | `P`, `X`, `Space`                            | Projection, x-ray, visibility scan / bodies / both              |
| Panels      | `Ctrl+B`, `Ctrl+Alt+B`                       | Project panel, properties panel                                 |
| Selection   | `B`, `W`, `L`                                | Brush, smart select, lasso                                      |
|             | `Ctrl+A`, `Ctrl+D`, `Ctrl+Shift+I`           | Select all visible, clear, invert                               |
|             | `G`, `Shift+G`                               | Grow, shrink by one ring                                        |
|             | `H`, `Shift+H`, `I`                          | Hide selection, show all, isolate                               |
|             | `[`, `]`, `Ctrl` + wheel                     | Brush size or smart-select tolerance                            |
|             | `Ctrl+R`                                     | Save selection as region                                        |
| Modelling   | `A`, `S`, `E`, `R`                           | Fit shape, sketch, extrude, revolve                             |
| Inspect     | `M`, `D`                                     | Measure, deviation display                                      |
| Sketch mode | `K`, `L`, `C`                                | Form corner (_Ecke bilden_), line between points, circle        |
|             | `Shift` + drag, hold `Alt`                   | Fit through points, suspend snapping                            |
| Settings    | `Ctrl+,`, `Ctrl+/`                           | Settings, shortcut help                                         |

### 7.3 Status bar hints

The left part of the status bar always says what the mouse and modifiers do right now and changes
while a modifier is held. Examples:

- Brush: "Linke Maustaste: hinzufügen · Strg: entfernen · [ ]: Pinselgröße · Rechte Maustaste:
  drehen"
- Smart select: "Klicken: Fläche hinzufügen · Strg+Klicken: entfernen · Strg+Mausrad: Toleranz"
- Sketch mode: "Umschalt+Ziehen: Element anpassen · Alt: Fangen aus · Esc: Werkzeug abbrechen"

---

## 8. Writing

### 8.1 Tone

- Factual, short, sentence case. Commands are verbs ("Scan importieren …", with an ellipsis when a
  dialog follows); panels and objects are nouns.
- No exclamation marks, no "Oops", no apologies, no emojis, no rhetorical questions.
- No marketing words: _leistungsstark, magisch, nahtlos, intelligent, KI-gestützt, mühelos_;
  in English _powerful, magic, seamless, smart, AI-powered, effortless_.
- German avoids addressing the user: neutral forms ("Datei auswählen"), _Sie_ only where
  unavoidable, never _du_.
- Explain the state, not the software: "Profil offen: 2 Lücken" rather than "Das Programm konnte
  das Profil nicht schließen".
- No developer words in the UI: "Rechenprozess", not "Kernel"; "Scan", not "Netz" or "Mesh".

### 8.2 Numbers, units, plurals, lists

- Locale formatting through `format.ts`: `1.204.566 Dreiecke`, `0,041 mm` (de);
  `1,204,566 triangles`, `0.041 mm` (en).
- Lengths 3 decimals, angles 2 decimals with `°`, percentages 1 decimal, areas in mm², volumes in
  mm³. The unit is always shown. Signed values always carry their sign in the deviation context.
- Every string with a count uses i18next plural keys (`_one`, `_other`), never "Dreieck(e)".
- Lists in sentences use `Intl.ListFormat` ("Extrusion 1, Extrusion 2 und Verrundung 1").

### 8.3 Error messages

| Situation               | German                                                                                                      | English                                                                                                         |
| ----------------------- | ----------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Invalid STL             | Import fehlgeschlagen: Die Datei ist kein gültiges STL (Dreiecksanzahl im Kopf passt nicht zur Dateigröße). | Import failed: the file is not a valid STL (the triangle count in the header does not match the file size).     |
| Suspicious size         | Der Scan ist 0,12 × 0,08 × 0,03 groß. Einheit wählen: mm, cm, m, Zoll.                                      | The scan measures 0.12 × 0.08 × 0.03. Choose the unit: mm, cm, m, in.                                           |
| Too few triangles       | Zylinder nicht einpassbar: Auswahl zu klein (84 Dreiecke, mindestens 200).                                  | Cannot fit a cylinder: selection too small (84 triangles, at least 200).                                        |
| Poor fit                | Nur 82,4 % der Dreiecke liegen in der Toleranz ±0,100 mm. Auswahl prüfen oder anderen Typ wählen.           | Only 82.4 % of the triangles are within the tolerance of ±0.100 mm. Check the selection or choose another type. |
| Open profile            | Extrusion nicht möglich: Profil ist offen (2 Lücken). Lücken sind markiert.                                 | Cannot extrude: the profile is open (2 gaps). The gaps are marked.                                              |
| Sketch off the scan     | Skizze weicht vom Scan ab (max. 0,800 mm). Neu anpassen oder Ebene prüfen.                                  | Sketch deviates from the scan (max. 0.800 mm). Refit or check the plane.                                        |
| Fillet too large        | Verrundung fehlgeschlagen: Radius 12,000 mm ist zu groß für die gewählten Kanten.                           | Fillet failed: radius 12.000 mm is too large for the selected edges.                                            |
| Combine without overlap | Abziehen fehlgeschlagen: Die Körper überschneiden sich nicht.                                               | Subtract failed: the bodies do not intersect.                                                                   |
| Export blocked          | Export gesperrt: Körper 2 ist nicht geschlossen (Ursache: Extrusion 3).                                     | Export blocked: Body 2 is not closed (caused by Extrude 3).                                                     |
| Process stopped         | Rechenprozess beendet. Das Projekt ist unverändert.                                                         | Computing process stopped. The project is unchanged.                                                            |
| Saved                   | Gespeichert: halterung.m2c                                                                                  | Saved: halterung.m2c                                                                                            |
| Exported                | STEP gespeichert: halterung.step (2 Körper, 184 KB)                                                         | STEP saved: halterung.step (2 bodies, 184 KB)                                                                   |

### 8.4 Glossary

i18n keys stay English. Use these terms consistently; do not introduce synonyms. German terms
follow common CAD usage (Inventor, Fusion 360, SolidWorks in German).

| Key                                      | Deutsch                                                               | English                                  |
| ---------------------------------------- | --------------------------------------------------------------------- | ---------------------------------------- |
| scan                                     | Scan (never "Netz")                                                   | Scan                                     |
| triangle                                 | Dreieck                                                               | Triangle                                 |
| region                                   | Bereich                                                               | Region                                   |
| selection                                | Auswahl                                                               | Selection                                |
| brush / smartSelect / lasso / rectangle  | Pinsel / Flächenauswahl / Lasso / Rechteck                            | Brush / Smart select / Lasso / Rectangle |
| segment                                  | Segmentieren                                                          | Segment                                  |
| fitPrimitive                             | Form einpassen                                                        | Fit shape                                |
| primitive (noun)                         | Grundkörper                                                           | Primitive                                |
| plane / cylinder / cone / sphere / torus | Ebene / Zylinder / Kegel / Kugel / Torus                              | Plane / Cylinder / Cone / Sphere / Torus |
| referenceGeometry                        | Hilfsgeometrie                                                        | Reference geometry                       |
| alignAuto / alignFaces                   | Automatisch ausrichten / An Flächen ausrichten (3-2-1 in the tooltip) | Align automatically / Align to faces     |
| section / sketch                         | Schnitt / Skizze                                                      | Section / Sketch                         |
| extrude / revolve                        | Extrusion / Drehung                                                   | Extrude / Revolve                        |
| newBody / add / cut / intersect          | Neuer Körper / Vereinigen / Abziehen / Schnittmenge                   | New body / Unite / Subtract / Intersect  |
| combine / split                          | Kombinieren / Körper teilen                                           | Combine / Split body                     |
| fillet / chamfer                         | Verrundung / Fase                                                     | Fillet / Chamfer                         |
| body / history / origin                  | Körper / Verlauf / Ursprung                                           | Body / History / Origin                  |
| deviation / tolerance / scanNoise        | Abweichung / Toleranz / Scanrauschen                                  | Deviation / Tolerance / Scan noise       |
| measure                                  | Messen                                                                | Measure                                  |
| repair / reduce / fillHoles / smooth     | Reparieren / Reduzieren / Löcher füllen / Glätten                     | Repair / Reduce / Fill holes / Smooth    |
| computed / fixed                         | Berechnet / Fest                                                      | Computed / Fixed                         |
| snapUnits                                | Fangwerte: metrisch / Zoll                                            | Snap values: metric / inch               |
| computingProcess                         | Rechenprozess                                                         | Computing process                        |
| suppress                                 | Unterdrücken                                                          | Suppress                                 |
| ok / cancel / apply                      | OK / Abbrechen / Anwenden                                             | OK / Cancel / Apply                      |

---

## 9. Accessibility

- Every control is reachable with the keyboard. The tool row uses a roving tab index per group;
  the tree is a proper `role="tree"` with arrow-key navigation; menus and dialogs follow the Radix
  keyboard models.
- Focus is always visible (`:focus-visible` ring) and never trapped outside dialogs.
- Text contrast ≥ 4.5 : 1 for all text except disabled text (2.1).
- Colour is never the only carrier of meaning: pass/fail results carry icons, region borders are
  drawn, the deviation legend has numbers, and a colour-blind-safe scheme exists.
- Icon-only buttons have `aria-label`s from the same i18n keys as their tooltips.
- The UI works at 100 %, 125 % and 150 % Windows scaling; all sizes are CSS px.

---

## 10. Review checklist

Every UI pull request is checked against this list. It exists to keep the product looking like a
tool built by engineers, not like a generated demo. `styles/designRules.test.ts` checks the
mechanical items.

- [ ] Exactly one accent colour; every other colour comes from the grey ramp, the semantic states
      or the viewport palette.
- [ ] No gradients, `backdrop-filter`, glows, decorative animation, illustrations, emojis or
      sparkle icons.
- [ ] No slogans, taglines, badges ("100 % lokal"), welcome hero sections or repeated step numbers.
- [ ] Minimum text size 12 px (11 px only on the view cube); sentence case; no letter-spaced
      capitals.
- [ ] Radius ≤ 4 px, borders 1 px, docked panels square and without shadows.
- [ ] One primary button per panel; each command in at most two places.
- [ ] Top chrome 72 px; nothing covers the view cube, axis triad or legend.
- [ ] Every string comes from i18n in German and English; numbers are locale-formatted with units;
      counts use plural keys.
- [ ] Every error states what failed and why; technical details are behind _Details_.
- [ ] No hex colours outside `tokens.css` and `viewport/palette.ts`.
- [ ] Both themes checked; screenshots attached to the pull request, including every changed panel
      in German at 1280 × 720 (no truncated labels).

**Screenshots for README and releases:** a real scan from the acceptance set (ARCHITECTURE.md
1.5) or a user-contributed scan with permission, a tool panel open, and the deviation map
visible; one dark, one light; 1600 × 960 window at 100 % scaling; no mock-ups, no device frames,
no annotations drawn over the UI.

**App icon:** a simple geometric mark in the accent colour and one neutral grey on a transparent
background, readable at 16 px; no gradients, no 3D effects, no text.

---

## 11. Decisions

The UX review of 2026-09-26 raised 25 points, ordered by severity. Each was accepted, accepted in
part or rejected as recorded here. Engineering decisions are in
[ARCHITECTURE.md section 8](ARCHITECTURE.md#8-decisions).

1. **Selection tools unusable inside panel tools.** Accepted. Selection modes are independent of
   panel tools, their options sit in the tool row, previews re-run on selection changes, and an
   edited fit loads its triangles as the selection (3.2, 5.1).
2. **Sketches never snap values.** Accepted. Sketch entities snap like fits: radii, lengths,
   positions from the origin, common angles, equal radii, bolt circles; each snap is listed and
   removable (5.2).
3. **PCA alignment is 2° off.** Accepted. _Automatisch ausrichten_ uses the largest planes and
   falls back to PCA only without two planes; _An Flächen ausrichten_ also takes axis + plane; the
   remaining tilt is shown after aligning (ARCHITECTURE.md 1.1, 4.12).
4. **Only synthetic acceptance tests.** Accepted. A manual real-scan acceptance set with time and
   accuracy targets; one of its scans provides the README screenshots (ARCHITECTURE.md 1.5, 10).
5. **Shafts and knobs cannot be revolved reliably.** Accepted. Reference geometry is P0 (plane
   through an axis, offset plane, mid-plane, axis from two planes); rotational sections are P0
   (ARCHITECTURE.md 1.2).
6. **No manual drawing.** Accepted as the proposed minimum: _Ecke bilden_, line between two
   points, circle by centre and radius (7.2). Free drawing stays P1.
7. **Measuring is P1.** Accepted. _Messen_ is P0 in _Prüfen_ (panel values only); the extrude
   distance is pre-filled from the scan extent (5.2).
8. **Cleanup tools are P1.** Accepted. Lasso and rectangle are P0 with _Durch das Teil_; the crop
   box stays P1 (5.4).
9. **Two verdict rules, hidden noise, unclear tolerance.** Accepted. One rule (≥ 95 % in
   tolerance) with matching text; scan noise in every result block; the import proposes the
   tolerance from the noise; the status item is the only place to change it (3.5, 5.3).
10. **Body and scan z-fighting.** Accepted. Bodies are drawn with a polygon offset; `Space` cycles
    _Scan und Körper / nur Scan / nur Körper_ (6.2, 6.5).
11. **Contradictory sketch exit.** Accepted. `Esc` never commits; the sketch panel footer holds
    _Skizze beenden_ and _Abbrechen_; the tool row holds only sketch tools (5.1, 6.5, 7.3).
12. **Tool switches discard work; `Ctrl+Z` in tools undefined.** Accepted. Tools with valuable
    drafts ask before discarding; `Ctrl+Z` inside a tool undoes the draft or selection only (5.1).
13. **Sketches silently drift from the scan.** Accepted. The rebuild compares each sketch with its
    current section and flags deviations in the tree and properties (5.5, 8.3).
14. **Alignment slots and the fit tool in _Ausrichten_.** Accepted. The alignment inputs take fit
    features, reference geometry and regions by clicking in the viewport or tree; _Form
    einpassen_ is no longer in the _Ausrichten_ stage (3.2).
15. **Snaps without measured values; inch parts.** Accepted. Snap rows show the measurement with
    its uncertainty; _Fangwerte: metrisch / Zoll_ is a project setting (5.2).
16. **Selection survives commits; no coverage view.** Accepted in part. Clearing the used
    triangles after a fit is the default and can be turned off (5.4); the _Abgedeckt_ display mode
    is P1 because it needs the deviation machinery against every body (6.2).
17. **Import and export stages.** Accepted. Four stages; import lives in _Datei_ and the empty
    state, export in _Prüfen_; unimplemented tools are hidden in release builds (3.2).
18. **Non-standard German terms.** Accepted with one change: _Form einpassen_, _Berechnet / Fest_,
    _Grundkörper_, _Drehung_, _Kombinieren_, _An Flächen ausrichten_ as proposed; the trim tool is
    called _Körper teilen_ rather than _Körper kappen_, because it keeps one side of a split and
    "teilen" is the term users know from Fusion 360 (8.4).
19. **Inconsistent wording.** Accepted. "Scan" everywhere, "Rechenprozess" instead of "Kernel",
    nothing shown when idle, plural keys and `Intl.ListFormat` required (5.7, 8.1, 8.2).
20. **Colliding default names; flat region lists.** Accepted. Regions are "Bereich N" with the type
    as icon and secondary text; _Bereiche_ is collapsed, grouped by type, with a filter for unused
    regions (5.5).
21. **Truncated German labels.** Accepted. Labels wrap to two lines, checkbox rows use the full
    width, and the review checklist requires German screenshots at 1280 × 720 (4, 10).
22. **"200.000" read as 200.** Accepted. Count fields read `.` as a thousands separator in
    German; length fields reject ambiguous input with a hint (4).
23. **No in-app help.** Accepted. _So geht's_ section per tool, `F1` opens bundled local pages,
    and the getting-started guide follows the bundled example from import to STEP (3.4, 5.10).
24. **Housings without draft and shell.** Accepted. "Housing" is removed from the v0.1 promise;
    taper angle on extrude and constant-thickness shell are P1 (ARCHITECTURE.md 1, 1.2).
25. **Scope to trade.** Accepted. One mouse mapping plus inverted wheel, orbit by dragging the view
    cube (7.1, 6.7); only the 3-step map and the colour-blind scheme (6.6); the saved effort goes
    to _Radius aus Scan_ in the fillet tool (5.2).
