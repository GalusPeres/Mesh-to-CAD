# Mesh-to-CAD architecture

Specification for version 0.1. Audience: contributors and everyone implementing v0.1.
The UI design system is specified separately in [DESIGN.md](DESIGN.md).

Status: accepted, 2026-09-26, revised after the design review of the same day (section 8).
Changes to the contracts in this document (protocol, document model, registries, shared
modules) go through a pull request that updates this file first.

## Contents

1. [Product scope](#1-product-scope)
2. [System overview](#2-system-overview)
3. [Processes and protocol](#3-processes-and-protocol)
4. [Kernel](#4-kernel)
5. [Frontend](#5-frontend)
6. [Repository and conventions](#6-repository-and-conventions)
7. [Testing](#7-testing)
8. [Decisions](#8-decisions)

---

## 1. Product scope

Mesh-to-CAD turns triangle meshes from 3D scanners (STL, OBJ, PLY) into editable solid models
(B-Rep) and exports them as STEP. Version 0.1 runs on Windows 10/11 x64 and is aimed at hobbyists
with consumer scanners.

The central promise of v0.1: a **prismatic or rotational part** (bracket, flange, adapter, cover
plate, shaft, knob) can be rebuilt with dimensionally sensible values, and its dimensions and its
deviation from the scan are visible at every step. Moulded housings need draft angles and shells,
which are P1; freeform support exists but is secondary.

### 1.1 End-to-end workflow

1. **Import** an STL, OBJ or PLY file (_Datei → Scan importieren_, the empty state, or drag and
   drop). The import panel shows the bounding box in the chosen unit (mm, cm, m, in), the
   triangle count and the estimated scan noise, and proposes a project tolerance from the noise.
   Scans above 2,000,000 triangles are reduced during import.
2. **Prepare** the scan: repair (weld, remove degenerate and duplicate triangles, fix winding),
   remove small parts, fill small holes, reduce, smooth (display and export only), delete
   selected triangles. Rectangle and lasso selection (optionally through the part) remove
   turntables and fixtures.
3. **Align** the scan to a part coordinate system. _Automatisch_ puts the largest plane on XY,
   the largest plane perpendicular to it on XZ and the origin on the part; _An Flächen
   ausrichten_ builds the frame from fitted features, regions or the selection (plane-plane-plane,
   or axis plus plane for shafts and flanges). Flip and rotate in 90° steps. After aligning, the
   panel shows the remaining tilt ("Größte Ebene 0,02° zu XY").
4. **Select** triangles with the brush, smart select, lasso or rectangle. Selection modes stay
   usable while any tool panel is open. Save selections as regions, or run automatic segmentation.
5. **Fit shapes** (plane, cylinder, cone, sphere, torus, or automatic type) to a selection or
   region. The panel shows scan noise, RMS, maximum deviation and the share within tolerance; the
   scan is coloured pass/fail. Each parameter is either computed by the fit or fixed. Design
   intent snapping proposes exact values ("Radius 8,000 mm, gemessen 7,987 ± 0,012") in metric or
   inch steps.
6. **Reference geometry**: plane through a fitted axis at an angle, offset plane, mid-plane of two
   planes, axis from two planes. It serves as sketch plane, extrude limit and alignment input.
7. **Sketch** on a planar or rotational section: lines, arcs and circles are fitted automatically,
   with inferred constraints and snapped values. Minimal manual drawing covers what the scan
   lacks: _Ecke bilden_, a line between two points, a circle by centre and radius.
8. **Build solids**: extrude (distance prefilled from the scan extent) and revolve sketch profiles
   as a new body or combined with an existing one; bodies from fitted cylinders, cones, spheres and
   tori; split bodies with planes; combine bodies; fillets and chamfers, with the radius measurable
   from the scan.
9. **Freeform** (secondary): fit a B-spline patch to a region and split a body with it; loft a
   body through sections of the scan.
10. **History**: every feature appears in one project tree. Features can be edited, suppressed,
    renamed and deleted; downstream features rebuild. Undo and redo cover every document change and
    selection strokes.
11. **Inspect**: measure distances, diameters and angles between features; deviation colour map of
    the scan against the bodies, with legend and statistics.
12. **Export** STEP (AP214 or AP242, millimetres, verified by reading the file back) and STL from
    the _Prüfen_ stage. Save and open projects (`.m2c`).
13. The UI is German by default and switchable to English.

### 1.2 Capabilities and priority

P0 blocks the v0.1 release. P1 is planned for v0.1 but may move to v0.2 without blocking the
release. Tools that are not implemented are hidden in release builds (DESIGN.md 3.2).

| Area      | Capability                                                                                        | Priority |
| --------- | ------------------------------------------------------------------------------------------------- | -------- |
| Import    | STL (binary, ASCII), OBJ, PLY; unit choice; import report with noise and proposed tolerance       | P0       |
| Import    | Drag and drop onto the window; reduce on import above `MAX_WORKING_FACES`                         | P0       |
| Prepare   | Repair, remove small parts, fill small holes, reduce, delete selected triangles                   | P0       |
| Prepare   | Smoothing as a display and export setting                                                         | P0       |
| Prepare   | Crop box                                                                                          | P1       |
| Align     | Automatic (largest planes, then 3-2-1; PCA only as fallback), remaining tilt shown                | P0       |
| Align     | _An Flächen ausrichten_ from fit features, regions or selection; axis + plane variant; flip, 90°  | P0       |
| Select    | Brush, smart select, lasso, rectangle (through-selection option); usable inside every panel tool  | P0       |
| Select    | Grow/shrink ring, select all/clear/invert, hide/show/isolate                                      | P0       |
| Regions   | Save selection as region; merge, rename, delete, add/remove selection                             | P0       |
| Regions   | Automatic segmentation with sensitivity, type and RMS per region                                  | P0       |
| Fit       | Plane, cylinder, cone, sphere, torus, automatic; robust (RANSAC) option; fixed parameters         | P0       |
| Fit       | Pass/fail colouring, noise, RMS, max, share in tolerance, alternative types                       | P0       |
| Fit       | Design intent snapping (metric or inch steps) with measured value and per-snap removal            | P0       |
| Reference | Plane through axis (angle), offset plane, mid-plane, axis from two planes                         | P0       |
| Sketch    | Planar section on standard, fitted or reference plane; rotational section around a fitted axis    | P0       |
| Sketch    | Automatic line/arc/circle fit with constraints and value snapping; numeric editing; refit         | P0       |
| Sketch    | Fit one entity by painting over section points; close gap; _Ecke bilden_; line; circle by values  | P0       |
| Sketch    | Deviation check against the current section after upstream changes                                | P0       |
| Sketch    | Stacked sections; free manual line/arc drawing                                                    | P1       |
| Solids    | Extrude (distance prefilled from the scan, both sides, symmetric, up to plane), revolve           | P0       |
| Solids    | New body, add, cut, intersect; body from fitted primitive; split by plane; combine bodies         | P0       |
| Solids    | Fillet and chamfer (constant size), _Radius aus Scan_                                             | P0       |
| Solids    | Extrude up to the scan; taper angle on extrude; constant-thickness shell                          | P1       |
| Freeform  | B-spline height-field patch, split by patch, loft through sections                                | P1       |
| History   | Tree with edit, suppress, rename, delete (with dependents), rebuild, error states                 | P0       |
| History   | Undo/redo of document changes and selection strokes                                               | P0       |
| Inspect   | Measure between fitted features, reference geometry and bodies (panel values only)                | P0       |
| Inspect   | Deviation colour map (3 steps per side, colour-blind scheme), legend, statistics, value at cursor | P0       |
| Inspect   | Pinned value labels, CSV report, _Abgedeckt_ display mode                                         | P1       |
| Export    | STEP (AP214/AP242) with read-back validation; STL of bodies; pre-flight check                     | P0       |
| Export    | STL of the scan                                                                                   | P1       |
| Project   | Save, open, recent files, recovery after a crash                                                  | P0       |
| UI        | German and English, dark and light theme, inverted wheel option, shortcut help, _So geht's_, F1   | P0       |

### 1.3 Non-goals for v0.1

- Point clouds (PTX, E57), textures and vertex colours, multiple scans, scan-to-scan registration.
- N-point alignment, interactive gizmo alignment, symmetry-plane alignment.
- A dimension-driven sketch solver. Sketches are edited numerically per entity; constraints are
  inferred and kept by a least-squares refit, not by a general geometric constraint solver.
- Sketch trim, offset, mirror, pattern; feature pattern, mirror, draft, sweep, variable fillets;
  inserting features in the middle of the history; reordering features; rollback bar.
- Automatic surfacing (quad remeshing to NURBS), class-A surfaces, surface stitching beyond
  "split a body with a patch" and "loft".
- IGES, DXF, Parasolid export; STEP import; comparison against external CAD files; history
  transfer to other CAD systems.
- Inch display units (inch is an import unit and a snapping unit), assemblies.
- macOS and Linux builds, code signing, auto-update, plugins or scripting.
- Telemetry of any kind, now or later, and any network access at runtime.

### 1.4 Limits

All limits live in `kernel/m2c_kernel/limits.py` and are generated into
`src/shared/protocol/generated/limits.ts`. No other file hard-codes them. Value ranges of
parameters are declared on the wire types (`Annotated[int, Range(3, 64)]`) and generated as well.

| Constant               | Value      | Reason                                                              |
| ---------------------- | ---------- | ------------------------------------------------------------------- |
| `MAX_WORKING_FACES`    | 2,000,000  | Renderer memory for the non-indexed scan geometry (5.8)             |
| `MAX_IMPORT_FACES`     | 10,000,000 | Kernel memory while reducing during import; raised only with a test |
| `MAX_IMPORT_BYTES`     | 1 GiB      | File size accepted by `mesh.import`                                 |
| `MIN_FIT_FACES`        | 200        | Fewer triangles give unstable fits                                  |
| `MAX_REGIONS`          | 65,534     | Region labels are uint16, 0 = unassigned                            |
| `MAX_FEATURES`         | 500        | Rebuild time and tree usability                                     |
| `MAX_REVISIONS`        | 200        | Undo depth                                                          |
| `MAX_MESH_REVISIONS`   | 10         | Revisions that store their own scan copy (disk use, 4.3)            |
| `MAX_FRAME_BYTES`      | 256 MiB    | Protocol frame limit, and with it the largest IPC message           |
| `DEFAULT_TOLERANCE_MM` | 0.10       | Project tolerance until the import proposes one                     |
| `CANCEL_GRACE_MS`      | 3000       | Time a cancelled request may run on before a restart is offered     |

### 1.5 Quality targets

**Accuracy on synthetic scans** with known geometry: Gaussian noise σ = 0.03 mm along the normal
plus 0.1 % spikes of 0.15–0.3 mm (section 7.2). The research runs reached values well inside
these targets; the targets keep a margin for different tessellations.

| Operation                                 | Target                                                   |
| ----------------------------------------- | -------------------------------------------------------- |
| Plane fit, 40 × 40 mm patch               | normal < 0.01°, offset < 0.005 mm                        |
| Cylinder fit, 90° arc, R12.5              | axis < 0.01°, radius < 0.01 mm                           |
| Cone, torus, sphere fits                  | angle < 0.05°, radii and centre < 0.02 mm                |
| Automatic type choice                     | 10 of 10 test patches correct                            |
| RANSAC with 45 % clutter                  | axis < 0.05°, radius < 0.01 mm                           |
| Alignment from faces (3-2-1)              | rotation < 20″, origin < 0.01 mm                         |
| Automatic alignment of the test block     | axes within 0.05° of the design axes                     |
| Automatic segmentation, 16-face test part | 14–18 regions, mean IoU ≥ 0.92                           |
| Section sketch, test plate, σ = 0.02 mm   | exact topology, corner error < 0.03 mm, radii < 0.005 mm |
| Sketch value snapping, test plate         | all outline lengths, positions and radii exact           |
| Deviation (signed distance)               | < 0.001 mm difference to brute force                     |
| STEP round trip                           | volume relative error < 1e-9, same solid count           |

**Real-scan acceptance** (manual, before the release): 3–5 scans of hobby parts with a
permissive licence (bracket, flange, shaft, knob, cover). Each is rebuilt by following the
getting-started guide in under 30 minutes, and the exported STEP lies within ±0.05 mm of the
nominal dimensions. One of them is used for the README screenshots.

**Performance budgets** on a desktop with 8 cores, 16 GB RAM and an integrated GPU; 1,000,000
faces unless stated:

| Operation                                                | Budget                                         |
| -------------------------------------------------------- | ---------------------------------------------- |
| Import binary STL including repair, 2 M faces            | < 10 s, with progress                          |
| Scan interactive in the viewport after import            | < 3 s; UI thread never blocked > 100 ms        |
| Brush stroke sample (pick + attribute update)            | < 8 ms                                         |
| Smart select click                                       | < 1 s                                          |
| Fit preview, 100 k selected faces                        | < 300 ms                                       |
| Section and automatic sketch                             | < 300 ms                                       |
| Solid feature preview (geometry and status)              | < 500 ms                                       |
| Deviation summary of a solid preview                     | < 1 s after the geometry, in its own lane      |
| Rebuild of a 20-feature history after a parameter change | < 1 s                                          |
| Automatic segmentation                                   | < 20 s, with progress, cancellable             |
| Deviation map                                            | < 12 s, with progress, cancellable             |
| STEP export of a typical part                            | < 1 s                                          |
| Cancel of any job, including native calls                | UI free at once; kernel restart offered at 3 s |

---

## 2. System overview

```
┌────────────────────────────────── Electron application ──────────────────────────────────┐
│                                                                                           │
│  Renderer process (sandboxed)                    Main process (Node.js)                   │
│  React UI shell, tools, panels          IPC      window, security, m2c:// protocol        │
│  zustand stores                       ◄──────►   file dialogs (owns every path)           │
│  three.js viewport + Web Workers    (preload)    settings, recent files, recovery         │
│  KernelClient (typed)                            KernelHost: spawn, frame, route, cancel  │
│                                                        │                                  │
└────────────────────────────────────────────────────────┼──────────────────────────────────┘
                                         stdin / stdout  │  length-prefixed frames:
                                         stderr = log    │  JSON header + binary buffers
                                                         ▼
                              Python kernel process  (m2c_kernel, one per window)
                              protocol · session · document · rebuild engine
                              mesh · segmentation · fitting · alignment · sketch
                              cad (Open CASCADE via OCP) · freeform · inspection · export
                                                         │
                                                         ▼
                              session directory  %LOCALAPPDATA%\Mesh-to-CAD\sessions\<id>\
                              blobs (.npy), revisions (.json), head.json, lock file
```

Design rules that the rest of this document follows:

1. **The kernel owns geometry and the document.** The renderer holds a read-only mirror of the
   document and the display buffers, plus pure interaction state (selection, active tool, camera).
2. **Heavy data is binary and stays where it is used.** Meshes live in the kernel and are
   referenced by content hash. Triangle selections travel as `Uint32Array`, display geometry as
   typed arrays. Nothing large is ever encoded as JSON.
3. **The main process owns file paths.** The renderer never sends a path to the kernel. Methods
   that read or write files can only be called by the main process after a native dialog, and the
   kernel checks the caller as well.
4. **The kernel and the main process produce no user-visible text.** They return codes with
   parameters; the renderer translates them. This keeps German and English complete.
5. **Every document change is a revision.** Undo and redo move between revisions.
6. **Rebuilds are deterministic.** The same document gives the same bodies, statistics and display
   keys, in every run and after save and load.
7. **Extension through registries.** Tools, commands, feature types, protocol commands, codes and
   translations are discovered from their own files. There is no central switch over tools or
   feature types, so features can be built in parallel without touching shared files.

---

## 3. Processes and protocol

### 3.1 Main process (`src/main/`)

| Module                 | Responsibility                                                                   |
| ---------------------- | -------------------------------------------------------------------------------- |
| `index.ts`             | App lifecycle, single-instance lock, startup order, session directory cleanup    |
| `paths.ts`             | App data, logs, sessions and resource locations                                  |
| `window.ts`            | `BrowserWindow` creation, bounds persistence, title-bar colours                  |
| `security.ts`          | Web preferences, navigation and permission guards, CSP, dev URL check            |
| `appProtocol.ts`       | `m2c://app/` scheme serving `dist/renderer` with a path-traversal guard          |
| `ipc.ts`               | Channel registration; every handler checks the sender (below)                    |
| `kernel/KernelHost.ts` | Spawns the kernel, frames messages, routes responses and events, cancel, restart |
| `kernel/locate.ts`     | Resolves the kernel command for dev and packaged mode (3.4)                      |
| `files.ts`             | File actions: native dialog, then the matching main-only kernel method (3.5.8)   |
| `settings.ts`          | `%APPDATA%\Mesh-to-CAD\settings.json`, validated by `src/shared/settings.ts`     |
| `recent.ts`            | Recent projects and scans (at most 10, opaque ids for the renderer)              |
| `recovery.ts`          | Finds session directories left by a crashed instance; restore switches to one    |
| `logging.ts`           | `%LOCALAPPDATA%\Mesh-to-CAD\logs\main.log` and `kernel.log`, 5 × 5 MB rotation   |

**Window.** Frameless (`titleBarStyle: 'hidden'`) with native caption buttons through
`titleBarOverlay` (height 32), 1600 × 960 default, 1280 × 720 minimum, shown when ready. Web
preferences: `sandbox: true`, `contextIsolation: true`, `nodeIntegration: false`,
`webSecurity: true`, `spellcheck: false`, `devTools` only when not packaged; the preload is
`dist/preload/index.cjs`.

**Security** (all required):

- Pages load from the privileged scheme `m2c://app/`, never from `file://`. The handler resolves
  the request inside `dist/renderer` and answers 403 for anything outside.
- CSP (response header and meta tag): `default-src 'self'; script-src 'self'; style-src 'self'
'unsafe-inline'; img-src 'self' data: blob:; worker-src 'self' blob:; connect-src 'self';
object-src 'none'; base-uri 'none'; frame-ancestors 'none'`. Only in dev, `connect-src` and
  `script-src` additionally allow `http://127.0.0.1:5173` and `ws://127.0.0.1:5173`.
- `setWindowOpenHandler(() => ({ action: 'deny' }))`; `will-navigate`, `will-attach-webview` and
  `will-redirect` are prevented; all permission requests and checks are denied.
- Every `ipcMain.handle` and `ipcMain.on` is wrapped by `trusted(event)`: the sender must be the
  main window's `webContents`, the frame must be the main frame, and `protocol//host` of its URL
  must equal the app origin (`m2c://app`, or the dev server origin when not packaged).
  `URL.origin` is `"null"` for custom schemes and must not be used for this check.
- The dev renderer URL is accepted only when `!app.isPackaged` and it matches
  `^http://127\.0\.0\.1:\d+/?$`.
- Renderer requests for methods whose generated caller is not `renderer` are rejected in main
  with `kernel.notAllowed`; the kernel checks the `origin` header field again (3.5.3).

**IPC channels** (`src/shared/ipc.ts`). Renderer to main (`invoke` unless noted):

| Channel                           | Payload                                                                          | Result                                                      |
| --------------------------------- | -------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| `kernel:request`                  | `{ clientId, method, params, buffers: ArrayBuffer[], lane? }`                    | `RawResponse`                                               |
| `kernel:cancel` (send)            | `clientId`                                                                       | –                                                           |
| `kernel:restart`                  | –                                                                                | `KernelStatus`                                              |
| `kernel:getStatus`                | –                                                                                | `KernelStatus`                                              |
| `files:run`                       | `action: FileAction, params, dialog: { title, filterName, defaultName? }`        | `RawResponse` or `{ canceled: true }`                       |
| `files:dropped`                   | path resolved in the preload with `webUtils.getPathForFile`; main checks it      | `RawResponse`                                               |
| `files:openRecent`                | `recentId`                                                                       | `RawResponse`                                               |
| `files:reveal` (send)             | `token` of a file main wrote                                                     | –                                                           |
| `recent:list`                     | –                                                                                | `RecentFile[]`                                              |
| `recovery:list`                   | –                                                                                | `RecoveryCandidate[]` (sessions left by a crashed instance) |
| `recovery:resolve`                | `candidateId, 'restore' \| 'discard'`                                            | `KernelStatus`                                              |
| `settings:get` / `settings:set`   | – / `SettingsPatch`                                                              | `Settings`                                                  |
| `window:setTitleBarColors` (send) | `{ color, symbolColor }`, both `#RRGGBB`                                         | –                                                           |
| `window:setTitle` (send)          | title text                                                                       | –                                                           |
| `window:confirmClose` (send)      | –                                                                                | –                                                           |
| `app:info`                        | –                                                                                | versions and log folder for _Über_                          |
| `app:log` (send)                  | `{ level, message, stack? }`                                                     | –                                                           |
| `app:openHelp` (send)             | `language, topic` (tool id); main opens `resources/help/<language>/<topic>.html` | –                                                           |

`FileAction` is `openMesh`, `openExample`, `openProject`, `saveProject`, `saveProjectAs`,
`exportStep`, `exportStl`, `exportReport`. Main to renderer (`webContents.send`): `kernel:event`
(progress, `documentChanged`), `kernel:status` (`starting | ready | unresponsive | stopped`, exit
code, error), `window:beforeClose` (the renderer decides about unsaved changes and answers with
`window:confirmClose`).

Dialog titles and filter names come from the renderer, already translated, so the main process
contains no user-facing strings.

### 3.2 Preload bridge (`src/preload/index.ts`)

The preload is bundled into one CommonJS file (a sandboxed preload cannot `require` local files)
and exposes exactly one object, `window.m2c`, typed as `M2CBridge` in `src/shared/bridge.ts`:

| Group      | Members                                                                                                   |
| ---------- | --------------------------------------------------------------------------------------------------------- |
| `kernel`   | `request`, `cancel`, `restart`, `status`, `onEvent`, `onStatus`                                           |
| `files`    | `run(action, params, dialog)`, `dropped(file)`, `openRecent(id)`, `reveal`                                |
| `recent`   | `list()`                                                                                                  |
| `recovery` | `list()`, `resolve(candidateId, 'restore' \| 'discard')`                                                  |
| `settings` | `get()`, `set(patch)`                                                                                     |
| `window`   | `setTitleBarColors`, `setTitle`, `onBeforeClose`, `confirmClose`                                          |
| `app`      | `info()`, `log(entry)`, `openHelp(language, topic)`, `testMode` (true only with `M2C_E2E=1`, enables 7.6) |

### 3.3 Renderer

A single-page React application loaded from `m2c://app/index.html`. It talks to the kernel only
through `window.m2c.kernel` via the typed `KernelClient` (5.3). Section 5 describes it.

### 3.4 Kernel process

**Launch.** One kernel per window, started by `KernelHost` when the window is created.

| Mode     | Command                                                                                                                                            |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Dev      | `<repo>\.venv\Scripts\python.exe -X utf8 -u -m m2c_kernel --session-dir <dir>` with `cwd = <repo>\kernel`. `M2C_PYTHON` overrides the interpreter. |
| Packaged | `<resources>\kernel\m2c-kernel.exe --session-dir <dir>` (PyInstaller onedir, entry `kernel/entry.py`)                                              |

Spawn options: `stdio: ['pipe', 'pipe', 'pipe']`, `windowsHide: true`. Environment: the parent
environment without `PYTHONPATH`, `PYTHONHOME` and `ELECTRON_RUN_AS_NODE`, plus `PYTHONUTF8=1`,
`PYTHONIOENCODING=utf-8` and `M2C_LOG_LEVEL`. The dev launcher (`scripts/dev.mjs`) also deletes
`ELECTRON_RUN_AS_NODE` before it starts Electron; some shells set it, and Electron then runs as
plain Node.

**Startup sequence** (`m2c_kernel/main.py`).

1. Protect the protocol channel before anything can print. This also redirects the Windows
   standard output handle, so C and C++ code (OCCT) cannot corrupt the stream:

   ```python
   protocol_out = os.fdopen(os.dup(1), "wb", buffering=0)   # private copy of the real stdout
   os.dup2(2, 1)                                             # fd 1 (C and C++ stdout) -> stderr
   sys.stdout = os.fdopen(1, "w", buffering=1, closefd=False)
   ```

2. Configure logging to stderr. Main copies stderr lines into `kernel.log`.
3. Open or create the session directory and take `session.lock` (`msvcrt.locking`; pid and start
   time inside).
4. Send the `ready` event with protocol version, kernel version and Python version. The heavy
   imports (numpy, scipy, trimesh, OCP) then load on a warm-up thread. Methods marked `light`
   (`system.ping`, `system.shutdown`, `debug.crash`) run at once; every other request waits for
   the warm-up, in 50 ms slices so that it can still be cancelled.
5. Silence OCCT message printers after OCP is imported (`cad/occ_compat.quiet_occt`).

`KernelHost` waits up to 30 s for `ready` and compares the protocol version; a mismatch is
reported as `kernel.protocolMismatch`.

**Native calls and cancellation.** Open CASCADE and `fast_simplification` hold the Python GIL
for the whole call; measured on the development machine, a tessellation froze all other threads
for 54 s. During such a call the kernel cannot read a cancel message, send progress or answer a
ping. Therefore:

- `KernelHost.cancel` resolves the request at once with `kernel.cancelled` and sends `cancel` to
  the kernel. The renderer is free immediately.
- If the kernel has not finished the abandoned request after `CANCEL_GRACE_MS`, the host sets the
  status `unresponsive`; the status bar offers _Rechenprozess neu starten_, which kills the
  process and restarts it on the same session. A late response clears the state again.
- Before a long native call the kernel enters `with ctx.native(stage):`, which sends a progress
  event with `fraction: null`; the status bar shows the indeterminate style (DESIGN.md 5.7).
- Mesh decimation runs in a child process (`multiprocessing`, spawn) that is killed on cancel; the
  child moves fd 1 to stderr before anything prints. `kernel/entry.py` calls
  `multiprocessing.freeze_support()`.

**Crash and restart.** When the kernel exits unexpectedly, the host resolves all open requests
with `kernel.stopped` and publishes status `stopped` with the exit code. The status bar shows the
message and a restart button (DESIGN.md 5.7); there is no automatic restart loop. A restart
starts the kernel with the same session directory; the kernel loads the revision named in
`head.json` and emits `documentChanged` with cause `restore`, so no committed work is lost.

**Shutdown.** Main sends `system.shutdown`; the kernel finishes the current request, releases the
lock and exits with `os._exit` (a daemon thread blocked on stdin must not delay the exit). After
5 s main kills it. Only after the process has exited does main delete the session directory
(with retries), because Windows cannot delete files that another process still holds open.

### 3.5 Protocol

#### 3.5.1 Framing

Both directions use the same frame. All integers are little-endian.

| Offset | Size | Content                                                         |
| ------ | ---- | --------------------------------------------------------------- |
| 0      | 4    | magic `M2CF`                                                    |
| 4      | 4    | `uint32` header length H (UTF-8 JSON)                           |
| 8      | 4    | `uint32` binary length B (sum of all buffers including padding) |
| 12     | H    | JSON header                                                     |
| 12 + H | 0–7  | zero padding to an 8-byte boundary                              |
| …      | B    | buffers, each starting at an 8-byte-aligned offset              |

The header lists the byte length of each buffer in `buffers: number[]`; offsets follow from the
alignment rule. A frame larger than `MAX_FRAME_BYTES` is a protocol error. Readers never
concatenate strings: Node collects `Buffer` chunks and slices them; Python reads exact byte counts
from `sys.stdin.buffer`. If a reader does not find the magic at a frame start, it logs the stray
bytes and closes the connection; the host reports `kernel.stopped`. Shared test vectors
(`tests/fixtures/frame-vectors.json`, generated from Python) keep both implementations identical.

#### 3.5.2 Buffers and JSON values

Any value in `params` or `result` can reference a buffer:

```json
{ "$buf": 0, "dtype": "uint32", "shape": [12408] }
```

Allowed dtypes: `uint8`, `uint16`, `uint32`, `int32`, `float32`, `float64`. Python decodes to
read-only numpy views on the frame bytes (no copy); `KernelClient` decodes to typed arrays on the
received `ArrayBuffer`. Array fields are declared with the aliases `U8Array` … `F64Array` from
`protocol/wire.py`; a plain numpy array in an undeclared field is an error, so large data cannot
silently turn into JSON.

Non-finite numbers are encoded as `null` (statistics of an empty set, a missing uncertainty);
generated types declare such fields as `number | null`. Infinity is never sent.

#### 3.5.3 Messages

| Type           | Direction     | Header                                                                                                                                                   |
| -------------- | ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| request        | host → kernel | `{ "type": "request", "id": 17, "method": "fit.preview", "lane": "fit.preview:fit-primitive", "origin": "renderer", "params": {…}, "buffers": [49632] }` |
| response       | kernel → host | `{ "type": "response", "id": 17, "ok": true, "result": {…}, "buffers": […] }`                                                                            |
| error response | kernel → host | `{ "type": "response", "id": 17, "ok": false, "error": { "code": "fit.tooFewFaces", "params": { "count": 84, "min": 200 }, "details": "…" } }`           |
| cancel         | host → kernel | `{ "type": "cancel", "id": 17 }`                                                                                                                         |
| event          | kernel → host | `{ "type": "event", "event": "progress", "requestId": 17, "data": { "fraction": 0.42, "stage": "regions.growing" } }`                                    |

Events: `ready`, `progress`, `documentChanged` (4.8). Request ids are assigned by `KernelHost`;
it maps them to the renderer's `clientId`s. `origin` is set by `KernelHost` (`renderer` for
requests from IPC, `main` for its own), never by the renderer.

A committing request writes its `documentChanged` event before its response, so the renderer's
mirror is current when the response arrives.

Wire keys are camelCase. Python code is snake_case; `protocol/wire.py` converts dataclass field
names generically from the type hints. Dictionary keys (statistics names, region ids, fixed
parameters) are data and are never converted.

#### 3.5.4 Execution: lanes, exclusive methods, cancellation, progress

- A reader thread parses frames; one worker thread executes requests in arrival order.
- **Lanes.** Methods registered with `lane=True` accept a lane named `<method>` or
  `<method>:<suffix>` (the suffix is usually the tool id, for example `doc.preview:extrude`).
  Lanes are derived from method names, so two tools can never share one by accident. A new
  request in a lane removes queued requests of that lane (they get `kernel.superseded`) and
  cancels the running one. Tool previews always use a lane, so fast parameter changes never queue
  up work.
- **Exclusive methods** (`exclusive=True`: import with reduction, segmentation, deviation map,
  decimation) run alone. While one runs, lane requests are answered with `kernel.busy` instead of
  waiting behind it; `ToolHost` disables tools and undo and shows the job in the status bar.
- **Cancellation** is cooperative inside the kernel: long loops call `ctx.check_cancelled()`,
  which raises `Cancelled`. The host does not wait for it (3.4). The renderer treats
  `kernel.cancelled` and `kernel.superseded` as silent.
- **Progress:** `ctx.progress(fraction, stage)` sends `progress` events, throttled to 10 per
  second. `fraction` is `null` for indeterminate work. `stage` is a `ProgressStage` code (3.5.5).

#### 3.5.5 Errors, issues and progress codes

`KernelError(code, params, details)` is the only exception type that reaches the protocol with a
specific code. Any other exception becomes `kernel.internal` with the traceback in `details`.
`params` are values for the message (numbers stay numbers; the renderer formats them). `details`
is technical text for the _Details_ block and the log.

Codes live in `kernel/m2c_kernel/codes/<domain>.py`, one module per domain (`kernel`, `document`,
`mesh`, `regions`, `fit`, `reference`, `alignment`, `sketch`, `cad`, `freeform`, `inspection`,
`export`, `project`), each with up to three string enums:

| Enum            | Meaning                               | i18n namespace |
| --------------- | ------------------------------------- | -------------- |
| `ErrorCode`     | Why a request or a feature failed     | `errors`       |
| `IssueCode`     | Warnings attached to a feature result | `issues`       |
| `ProgressStage` | What a running job is doing           | `progress`     |

Codes are `<domain>.<camelCase>`. Codegen writes them to `generated/codes-<domain>.ts`, and a
vitest test checks that both languages translate every code. Each domain's translations live in
`src/renderer/i18n/locales/{de,en}/domains/<domain>.json`.

#### 3.5.6 Versioning

`PROTOCOL_VERSION = 1` in `protocol/__init__.py`, generated into TypeScript. Any incompatible
change to framing, message shapes or an existing method increments it. Kernel and app are always
shipped together, so there is no negotiation; a mismatch is an error.

#### 3.5.7 Method definition and generated types

Methods are defined in Python; TypeScript types are generated from them.

```python
# kernel/m2c_kernel/commands/fit.py
@dataclass(frozen=True)
class FitPreviewParams:
    faces: U32Array
    kind: PrimitiveKind | Literal["auto"] = "auto"
    robust: bool = False
    fixed: FitFixed = FitFixed()

@dataclass(frozen=True)
class FitPreviewResult:
    primitive: Primitive
    stats: FitStats
    alternatives: list[FitAlternative]
    deviation: VertexValues

@command("fit.preview", lane=True)
def fit_preview(ctx: JobContext, params: FitPreviewParams) -> FitPreviewResult:
    ...
```

`@command(method, lane=False, caller="renderer", exclusive=False, light=False)`; `caller` is
`renderer`, `main` (methods that take file paths) or `test` (enabled by `M2C_DEBUG_COMMANDS=1`).

`npm run codegen` (`python -m m2c_kernel.protocol.codegen`) writes one TypeScript file per Python
module that declares wire types, so each domain owns its generated files:

| Python module                                        | Generated file in `src/shared/protocol/generated/`        |
| ---------------------------------------------------- | --------------------------------------------------------- |
| `commands/<group>.py`                                | `<group>.ts` (params, results, method table of the group) |
| `features/types/<type>.py`                           | `feature-<type>.ts` (kebab-case)                          |
| `codes/<domain>.py`                                  | `codes-<domain>.ts`                                       |
| other modules (`document/model.py`, `snapping.py` …) | `<package>-<module>.ts` or `<module>.ts`                  |
| `limits.py`, `protocol/__init__.py`                  | `limits.ts`, `protocol.ts`                                |
| the registries                                       | `index.ts`: combines the per-group tables, feature types  |

Type mapping: `int`, `float` → `number`; `str` → `string`; `bool` → `boolean`; `Literal` → string
union; `X | None` → `X | null`; `list[X]` and `tuple[X, ...]` → `X[]`; fixed tuples → TS tuples;
`dict[str, X]` → `Record<string, X>`; dataclasses → interfaces; `U8Array`…`F64Array` → typed
arrays; `BlobRef` → branded string; PEP 695 `type` aliases → type aliases; empty dataclasses →
`Record<string, never>`.

Rules:

- Every union of dataclasses carries a required `type: Literal[...]` discriminator.
- Types used in both directions get an `…Input` variant where fields with defaults are optional;
  in results every field is required.
- Types whose wire form differs from the stored form declare both: a fit's `faces` is sent as a
  `U32Array` and stored as a `BlobRef` (`@feature_type(..., input=..., store=...)`).
- `Annotated[int, Range(3, 64)]` exports the range, so panels validate without copying limits.
- `--module <name>` regenerates one module's file; `npm run codegen:check` fails CI when
  generated files are out of date.

#### 3.5.8 Method catalogue (v0.1)

"Main" methods take a `path` and are callable only by the main process, through `files:run`.
Lane `yes` means the method accepts `<method>[:<suffix>]`.

| Method                                                                                                             | Lane | Exclusive     | Commits                | Caller   | Status  |
| ------------------------------------------------------------------------------------------------------------------ | ---- | ------------- | ---------------------- | -------- | ------- |
| `system.info`, `system.ping`                                                                                       | –    | –             | no                     | renderer | done    |
| `system.shutdown`                                                                                                  | –    | –             | no                     | main     | done    |
| `doc.get`, `doc.dependents`                                                                                        | –    | –             | no                     | renderer | done    |
| `doc.apply`                                                                                                        | –    | –             | yes                    | renderer | done    |
| `doc.preview`                                                                                                      | yes  | –             | no                     | renderer | done    |
| `doc.checkout`                                                                                                     | –    | –             | moves head             | renderer | done    |
| `scene.fetch`                                                                                                      | –    | –             | no                     | renderer | done    |
| `mesh.import`                                                                                                      | –    | when reducing | no (pending import)    | main     | minimal |
| `mesh.commitImport`, `mesh.discardImport`                                                                          | –    | when reducing | commit: yes            | renderer | minimal |
| `mesh.inspect`                                                                                                     | –    | –             | no                     | renderer | planned |
| `mesh.repair`, `mesh.removeSmallParts`, `mesh.fillHoles`, `mesh.decimate`, `mesh.deleteFaces`, `mesh.setSmoothing` | yes  | decimate      | yes unless `dryRun`    | renderer | planned |
| `regions.grow`                                                                                                     | yes  | –             | no                     | renderer | planned |
| `regions.segment`                                                                                                  | yes  | yes           | yes unless `dryRun`    | renderer | planned |
| `regions.create`, `regions.update`, `regions.merge`, `regions.delete`                                              | –    | –             | yes                    | renderer | planned |
| `fit.preview`                                                                                                      | yes  | –             | no                     | renderer | planned |
| `alignment.preview`                                                                                                | yes  | –             | no                     | renderer | planned |
| `freeform.preview`                                                                                                 | yes  | –             | no                     | renderer | planned |
| `sketch.section`, `sketch.autoFit`, `sketch.fitEntity`                                                             | yes  | –             | no                     | renderer | planned |
| `inspection.deviation`                                                                                             | yes  | yes           | no                     | renderer | planned |
| `inspection.previewDeviation`                                                                                      | yes  | –             | no                     | renderer | planned |
| `inspection.measure`                                                                                               | yes  | –             | no                     | renderer | planned |
| `inspection.report`                                                                                                | –    | –             | no                     | main     | P1      |
| `export.preflight`                                                                                                 | –    | –             | no                     | renderer | planned |
| `export.step`, `export.stl`                                                                                        | –    | –             | no                     | main     | planned |
| `project.new`                                                                                                      | –    | –             | yes (new session head) | renderer | planned |
| `project.save`, `project.load`                                                                                     | –    | –             | load: yes              | main     | planned |
| `debug.sleep`, `debug.progress`, `debug.crash`, `debug.stdoutNoise`, `debug.echoBuffers`, `debug.nativeBlock`      | some | –             | no                     | test     | done    |

Reference geometry and all solid features have no methods of their own; they are previewed with
`doc.preview` and committed with `doc.apply`.

Import is two-phase so that the path stays in main while the renderer chooses the unit:
`mesh.import` (main, after the dialog or a drop) loads the file into a pending import and returns
its report and a `pendingId`; the import panel then calls `mesh.commitImport({ pendingId, unit,
reduceTo })` or `mesh.discardImport({ pendingId })`. The commit sets the project tolerance to the
value proposed from the scan noise; the tolerance status item changes it later.

File actions in main (`files.ts`, one table): `openMesh → mesh.import`, `openExample →
mesh.import` (bundled example, no dialog), `openProject → project.load`, `saveProject` and
`saveProjectAs → project.save`, `exportStep → export.step`, `exportStl → export.stl`,
`exportReport → inspection.report`. Each action has fixed filters and remembers its last folder.

---

## 4. Kernel

### 4.1 Package layout

The kernel is a flat Python project in `kernel/` (no install step; tests use `pythonpath = ["."]`).
No module or subpackage shares a name with a standard-library module (hence `inspection`, not
`inspect`); ruff rule `A005` enforces this. Modules marked _(planned)_ do not exist yet.

```
kernel/
  pyproject.toml            ruff, mypy, pytest configuration
  requirements.txt          pinned runtime dependencies
  requirements-dev.txt      -r requirements.txt + pytest, ruff, mypy, pyinstaller
  entry.py                  PyInstaller entry (planned)
  m2c-kernel.spec           PyInstaller spec, checked in (planned)
  m2c_kernel/
    __init__.py             __version__ (must equal package.json version)
    __main__.py, main.py    python -m m2c_kernel: stdout protection, logging, server
    limits.py               all limits (1.4)
    geometry.py             vector helpers, Vec3, Matrix4
    snapping.py             design-intent value snapping shared by fits and sketches
    protocol/               frame, wire, errors, registry, server, codegen
    codes/                  one module of codes per domain (3.5.5)
    session/                session, blobs, revisions, jobs, lock, fs (atomic replace)
    document/               model, ops, rebuild, results, display, snapshot, project_file
    commands/               one module per method group (3.5.8)
    features/
      registry.py           @feature_type, ReadSet, Refs
      common.py             shared parameter types (operation, target body)
      types/                fit, reference, sketch, extrude, revolve, primitive_body, trim,
                            combine, fillet, freeform_patch, loft
    mesh/                   load, topology, normals, remap, repair; decimate, smoothing (planned)
    segmentation/           api; creases, grow, auto, colouring (planned)
    fitting/                api, primitives, fit; ransac, constrained, intent (planned)
    alignment/              api; planes, frame (planned)
    sketch/                 api; section, fit2d, constraints, to_occ (planned)
    cad/                    occ_compat, check, tessellate, deflection, solids; booleans, edges,
                            fillet, tags (planned)
    freeform/               api; heightfield, loft (planned)
    inspection/             api; reference, distance, stats, measure (planned)
    export/                 api; step, stl, report (planned)
  tests/
    synthetic/              meshes and noise shared by all tests
    contracts/              tests that pin shared APIs between modules
    protocol/  document/    skeleton tests
    <domain>/               added by the owning work package
```

Each domain package exposes its public functions in `api.py`; other packages import only from
there. Dependency direction (lower layers never import higher ones):

```
commands  →  document, features  →  sketch, cad, fitting, segmentation, freeform, inspection, export
          →  alignment, mesh, snapping, geometry  →  numpy, scipy, trimesh, OCP
protocol, codes and session are imported by commands and document only.
```

Algorithm modules take and return numpy arrays and small frozen dataclasses. No trimesh object and
no `TopoDS_Shape` crosses a module boundary except through `cad/` and `document/results.py`.

### 4.2 Conventions

- Units: millimetres everywhere in the kernel. Import scales once. Angles in the kernel are
  radians; on the wire, parameters named `*Deg` are degrees.
- Coordinates: the working mesh is stored in **scan coordinates**. The alignment is a 4×4 rigid
  transform `p_part = T · p_scan`, stored row-major (16 numbers). All features, sketches and bodies
  are in **part coordinates**. Z is up.
- Arrays: float64 in computations, float32 only for transport and storage relative to an origin
  offset. Face indices are int64 in computations and uint32 on the wire.
- Faces are counter-clockwise seen from outside; normals point out of the material.
- Signed distances: positive means the point lies outside the material (for the scan: excess
  material on the real part).
- Randomness: every random generator is created with `seeded_rng(key)` (`session/jobs.py`),
  seeded from the result key of the feature or the request parameters. Code never uses global
  random state.
- Primitive parameterisation (shared by fitting, segmentation, sketch and cad):

  | Kind     | Parameters                                          | Signed distance        |
  | -------- | --------------------------------------------------- | ---------------------- |
  | plane    | origin `o`, normal `n`                              | `(p − o)·n`            |
  | sphere   | centre `c`, radius `r`                              | `‖p − c‖ − r`          |
  | cylinder | axis point `o`, axis `a`, radius `r`                | `ρ − r`                |
  | cone     | apex `v`, axis `a` (apex → opening), half angle `α` | `ρ cos α − h sin α`    |
  | torus    | centre `c`, axis `a`, major `R`, minor `r`          | `√((ρ − R)² + h²) − r` |

### 4.3 Session, blobs, revisions, jobs

`Session` is the kernel's single top-level object:

- **BlobStore** (`session/blobs.py`): content-addressed arrays. `put(array) -> BlobRef` computes
  SHA-256 over dtype, shape and bytes and writes `blobs/<hash>.npy` once. `get(ref)` reads the
  file into memory (no memory mapping: Windows cannot delete a mapped file) and keeps recent
  arrays in an LRU cache. Meshes, region labels and face sets are blobs, so revisions share them.
- **RevisionStore** (`session/revisions.py`): document snapshots written atomically to
  `revisions/<n>.json`; the checked-out revision is recorded in `head.json`. `commit` appends a
  revision and drops revisions after the head (linear history). Revision numbers are never reused.
  At most `MAX_REVISIONS` revisions are kept, and at most `MAX_MESH_REVISIONS` of them may
  reference a scan that no later revision references; older ones are pruned. A checkout of a
  pruned revision fails with `document.revisionGone`, and the renderer trims its history.
- **Blob garbage collection** runs after pruning or truncation and deletes blobs that no kept
  revision references. File replacement and deletion go through `session/fs.py`, which retries
  (antivirus scanners hold files open for a moment).
- **JobContext** (`session/jobs.py`): passed to every command handler: `request_id`, `session`,
  `progress(fraction, stage)`, `check_cancelled()`, `native(stage)`. The same module provides
  `seeded_rng(key)`.

Commands that change the document build a new `Document` value and call
`session.commit(new_doc, label, job)`. `commit` runs the rebuild (4.6), persists the revision,
emits `documentChanged` and returns the snapshot. Nothing else mutates the document.

### 4.4 Document model

`document/model.py` defines immutable dataclasses; the JSON form below is what is persisted,
sent in `documentChanged` and generated into TypeScript.

```json
{
  "revision": 42,
  "nextId": 12,
  "scan": {
    "key": "scan:3fa9…",
    "source": { "fileName": "halterung_scan.stl", "sha256": "…", "importUnit": "mm" },
    "vertices": "blob:3fa9…",
    "faces": "blob:77c1…",
    "synthetic": "blob:91d0…",
    "vertexCount": 604122,
    "faceCount": 1204566,
    "origin": [412.5, -80.2, 15.0],
    "noise": 0.036,
    "displaySmoothing": 0,
    "operations": [{ "op": "repair", "counts": { "degenerate": 1001, "duplicate": 2000 } }]
  },
  "alignment": {
    "method": "faces",
    "params": { "primary": { "feature": "f3" }, "secondary": { "feature": "f4" }, "origin": null },
    "adjust": { "flipX": false, "flipZ": false, "rotateZ90": 0 },
    "matrix": [1, 0, 0, -12.1, 0, 1, 0, 3.4, 0, 0, 1, -8.0, 0, 0, 0, 1]
  },
  "regions": {
    "labels": "blob:…",
    "items": [
      {
        "id": "r1",
        "label": 1,
        "name": null,
        "kind": "plane",
        "rms": 0.021,
        "faceCount": 81234,
        "area": 8317.2,
        "colorIndex": 3
      }
    ]
  },
  "features": [
    {
      "id": "f3",
      "type": "fit",
      "name": null,
      "suppressed": false,
      "params": {
        "faces": "blob:…",
        "sourceRegion": "r7",
        "kind": "cylinder",
        "robust": false,
        "fixed": { "radius": 8.0 },
        "relation": { "type": "parallel", "to": "Z" },
        "snap": true,
        "rejectedSnaps": []
      }
    },
    {
      "id": "f5",
      "type": "extrude",
      "name": "Grundplatte",
      "suppressed": false,
      "params": {
        "sketch": "f4",
        "loops": "all",
        "direction": "normal",
        "extent": { "type": "distance", "forward": 12.0, "backward": 0.0 },
        "operation": "newBody",
        "targetBody": null
      }
    }
  ],
  "settings": {
    "tolerance": 0.1,
    "snapUnits": "metric",
    "noiseOverride": null,
    "deviationMaxDistance": 2.0
  }
}
```

Rules:

- Ids are assigned by the kernel from `nextId`: features and bodies `f<n>`, regions `r<n>`,
  sketch points `p<n>` and entities `e<n>` (unique within their sketch). A body's id is the id of
  the feature that created it.
- `name: null` means "default name". The renderer shows the translated type name with a per-type
  ordinal ("Zylinder 2"; regions "Bereich 7"). The kernel never creates display text.
- `scan.key` identifies the working mesh. It changes with every topology-changing operation and
  tags everything that stores face indices outside the kernel (selection, hidden mask, history).
- `scan.synthetic` marks triangles created by hole filling (uint8 per face). Fitting, segmentation
  and deviation statistics exclude them.
- Region labels are one uint16 per face (0 = unassigned); regions are therefore disjoint. Creating
  a region from a selection moves those faces out of other regions.
- Feature inputs that are triangle sets are stored as `BlobRef`s inside the feature. A fit keeps
  its triangles even if the source region changes later; the tool offers _Bereich neu übernehmen_.
- Topology-changing mesh operations return an exact new → old face index map where one exists
  (delete, degenerate and duplicate removal, small parts, hole filling: new faces map to −1).
  Face sets and region labels are carried through that map. Only decimation, which has no exact
  map, falls back to nearest face centroid. `mesh/remap.py` provides `remap_face_set`,
  `remap_labels` and `nearest_centroid_map`; the mesh commands apply them to every face set stored
  in feature parameters and to the region labels.
- Smoothing never changes the working mesh; it is `scan.displaySmoothing`, applied to display
  and scan export only. Fits and deviation always use the unsmoothed positions.
- The alignment is a slot, not a list entry; the tree shows it as the first history entry. Its
  `method` is `none`, `auto` or `faces`; `params` refer to fit or reference features, regions or
  stored face sets. It is evaluated during rebuild, then `adjust` is applied. `matrix` is the last
  evaluated result, kept for display.

### 4.5 Features

A feature type is a module in `features/types/` that registers itself:

```python
@dataclass(frozen=True)
class ExtrudeParams:
    sketch: str
    extent: ExtrudeExtent
    operation: Operation = "newBody"
    ...

@feature_type("extrude", params=ExtrudeParams)
class Extrude:
    @staticmethod
    def references(params: ExtrudeParams) -> Refs:          # upstream features and bodies
        return Refs(features=(params.sketch, *plane_refs(params.extent)),
                    bodies=target_bodies(params))

    @staticmethod
    def evaluate(ctx: EvalContext, params: ExtrudeParams) -> FeatureOutput:
        ...
```

`@feature_type(type_id, params=…, reads=ReadSet(...), input=…, store=…)`. `reads` declares what
the feature reads besides its references: `ReadSet(mesh=True, alignment=False,
settings=("tolerance",))`. A feature that reads nothing but its references (extrude, combine) is
not re-evaluated when the scan, the alignment or the tolerance changes.

`EvalContext` gives read access to the aligned mesh (`ctx.mesh`: vertices, faces, face normals,
synthetic mask, lazy jet normals, face graph, KD-tree), `ctx.face_set(ref)`,
`ctx.construction(feature_id)`, `ctx.sketch(feature_id)`, `ctx.body(body_id)`, `ctx.settings` and
`ctx.job` (progress, cancel) and the feature's result key for seeding. `FeatureOutput`
(`document/results.py`) contains:

```python
@dataclass(frozen=True)
class FeatureOutput:
    construction: Construction | None = None       # fitted primitive, axis, point or patch
    sketch: SketchResult | None = None             # plane frame, loops, profile faces
    bodies: BodyUpdate = BodyUpdate()              # changed and removed bodies
    display: tuple[DisplaySource, ...] = ()        # construction, sketch, patch geometry
    stats: Mapping[str, float | None] = {}         # keys are i18n keys
    issues: tuple[Issue, ...] = ()                 # warnings (code + params)
```

**Face tags.** Every `Body` carries `face_tags`, one string per B-Rep face in `TopExp` order,
naming the face by its origin: `f5:cap:start`, `f5:cap:end`, `f5:side:e3` (extrude of sketch
entity `e3`), `f7:surface` (primitive body), `f9:fillet:0`. Features that modify a body carry the
tags of unchanged and modified faces through the operation history (`Modified()`,
`Generated()`); `cad/tags.py` provides the helper. Bodies are tessellated for display centrally
after the rebuild; features only add display sources for non-body geometry.

**Feature catalogue (v0.1).** Parameters as they appear on the wire:

| Type            | Parameters                                                                                                                                                                                                                             | Output                                                                  |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `fit`           | `faces`, `sourceRegion`, `kind` (plane, cylinder, cone, sphere, torus), `robust`, `fixed` (any of `direction`, `point`, `radius`, `halfAngleDeg`, `majorRadius`, `minorRadius`, `offset`), `relation`, `snap`, `rejectedSnaps`         | construction primitive, extent from its triangles, stats, applied snaps |
| `reference`     | `definition`: `{offsetPlane, plane, distance}`, `{planeThroughAxis, axis, angleDeg}`, `{midPlane, a, b}`, `{axisFromPlanes, a, b}`                                                                                                     | construction plane or axis                                              |
| `sketch`        | `plane` (`XY`/`YZ`/`XZ`, a plane feature, perpendicular to an axis; `offset`, `xDirection`, `flip`), `section` (`planar` or `rotational` around an axis), `tolerance`, `points`, `entities`, `loops`, `constraints`, `snaps`, `source` | sketch (plane frame, loops, profile faces), display polylines, issues   |
| `extrude`       | `sketch`, `loops` (`all` or loop ids), `direction` (`normal`, `reversed`, `symmetric`), `extent` (`{distance, forward, backward}` or `{toPlane, feature, offset}`), `operation`, `targetBody`                                          | body update, face tags                                                  |
| `revolve`       | `sketch`, `loops`, `axis` (`{sketchLine, entity}`, `{featureAxis, feature}`, `{globalAxis, axis}`), `angleDeg`, `operation`, `targetBody`                                                                                              | body update, face tags                                                  |
| `primitiveBody` | `fit` (cylinder, cone, sphere or torus fit), `extent` (`{region, margin}` or `{manual, start, length}`), `operation`, `targetBody`                                                                                                     | body update, face tags                                                  |
| `trim`          | `targetBody`, `tool` (`{plane, feature}` or `{patch, feature}`), `keep` (`front`, `back`)                                                                                                                                              | body update                                                             |
| `combine`       | `targetBody`, `tools` (body ids), `operation` (`add`, `cut`, `intersect`), `keepTools`                                                                                                                                                 | body update                                                             |
| `fillet`        | `targetBody`, `edges` (`EdgeRef[]`), `mode` (`fillet`, `chamfer`), `size`                                                                                                                                                              | body update                                                             |
| `freeformPatch` | `faces`, `sourceRegion`, `spans` (`auto` or `[u, v]`), `smoothing`, `margin`                                                                                                                                                           | construction patch (B-spline face)                                      |
| `loft`          | `path` (`X`/`Y`/`Z` or an axis feature), `start`, `end`, `sectionCount` (3–64), `faces`, `operation`, `targetBody`                                                                                                                     | body update                                                             |

`operation` is `newBody`, `add`, `cut` or `intersect`; `targetBody` is required for all but
`newBody`. _Radius aus Scan_ in the fillet tool is a preview helper, not a stored parameter: it
fits a cylinder to the scan triangles along the picked edges and proposes the (snapped) radius.

**Sketch semantics.** The stored entities are authoritative. A rebuild builds profile faces from
them; it does not re-fit the section. If the plane moves (for example because its reference was
refitted or the alignment changed), the entities move with the plane. The rebuild then compares
the entities with the current section and adds the issue `sketch.deviatesFromScan` (with the
maximum distance) when they differ by more than the tolerance; the tool offers _Neu anpassen_.

### 4.6 Rebuild engine (`document/rebuild.py`)

```python
def rebuild(document: Document, environment: RebuildEnvironment, job: JobContext) -> RebuildResult:
    mesh = environment.meshes.aligned(document.scan, document.alignment)  # alignment slot first
    state = EvalState()
    for feature in document.features:
        if feature.suppressed:
            state.mark(feature, "suppressed"); continue
        spec = registry[feature.type]
        refs = spec.references(feature.params)
        if state.any_unusable(refs):                      # error, skipped or suppressed input
            state.mark(feature, "skipped"); continue
        key = result_key(feature, state.keys_of(refs), spec.reads, mesh, document.settings)
        cached = environment.results.get(key) or evaluate_checked(spec, feature, key, ...)
        state.apply(feature, cached, key)                 # bodies checked (below)
    return state.result()
```

- Features are evaluated in list order; references must point to earlier features
  (`document.forwardReference` otherwise, checked in `doc.apply`).
- A **result key** is a hash of the feature type, its canonical parameter JSON, the keys of every
  referenced result and body, and what the feature declares in `reads`: the scan key, the
  alignment matrix, the named settings. Unchanged features are cache hits, so a parameter change
  re-evaluates only that feature and its dependents, and a tolerance change re-evaluates fits and
  sketches but not extrusions.
- **Determinism.** Random generators are seeded from the result key; parallel OCCT operations use
  `SetRunParallel(False)` where the result depends on the order. Display payload keys derive from
  result keys and tessellation settings, never from hashing the arrays. A test checks that save,
  load and rebuild give identical volumes, face counts and display keys.
- Status per feature: `ok`, `warning`, `error`, `suppressed`, `skipped`. A failed feature leaves
  the bodies unchanged and carries its error code and parameters. Dependents are skipped;
  independent later features still evaluate. The renderer shows the last valid geometry greyed.
- Every body produced by a feature is checked with `cad.check_solid` (valid, one solid, volume
  > 0, maximum tolerance). An invalid body makes the feature fail with `cad.invalidResult`.
- Deleting a feature that others reference fails with `document.hasDependents` and lists them,
  unless `cascade: true`.
- **Edge references** (fillet, chamfer): an `EdgeRef` is the pair of face tags on both sides of
  the edge plus a point on the edge as a tie-breaker. During rebuild, the candidates are the edges
  between faces with those tags; if several remain (a tag split by a boolean), the one closest to
  the point wins. No candidate → `cad.edgeNotFound` with the reference index, and the user
  re-picks. Face and edge indices from `TopExp.MapShapes_s` are never persisted. The renderer
  builds an `EdgeRef` from a picked edge: the body edge payload's `faces` names the two B-Rep
  faces, and `status.bodies[].faceTags` gives their tags.

### 4.7 Preview and commit

All tools use the same two steps:

1. **Preview:** `doc.preview({ baseRevision, ops })` in the tool's lane evaluates the document
   with `ops` applied, without committing. It evaluates up to and including the affected feature
   (features after it are not shown while editing). The result contains the feature status,
   stats, issues, display items and the result key. For solid features the tool then calls
   `inspection.previewDeviation({ resultKey })` in a second lane; it computes the deviation
   summary of the changed body (scan vertices within the search distance, subsampled to 50 k
   points) from the cached result. Domain previews (`fit.preview`, `sketch.autoFit`,
   `regions.segment` with `dryRun`) work the same way.
2. **Commit:** `doc.apply({ baseRevision, ops })` with the same parameters. Preview results are
   cached by result key, so the commit reuses them and returns immediately.

`doc.apply` operations: `addFeature { feature }` (appended), `updateFeature { id, params }`,
`renameFeature { id, name }`, `deleteFeature { id, cascade }`, `setSuppressed { id, suppressed }`,
`setAlignment { alignment }`, `setSettings { patch }`. Several operations in one call form one
revision. If `baseRevision` is not the head, the call fails with `document.staleRevision`.

### 4.8 Display items and `documentChanged`

After each commit, checkout or restore the kernel emits `documentChanged` with a
`DocumentSnapshot` (`document/snapshot.py`):

```json
{
  "revision": 42,
  "cause": "commit",
  "label": "extrude",
  "document": { "…": "document JSON as in 4.4" },
  "status": {
    "features": {
      "f5": {
        "state": "error",
        "issues": [],
        "error": { "code": "cad.filletFailed", "params": {} }
      }
    },
    "bodies": [
      { "id": "f5", "owner": "f5", "valid": true, "solids": 1, "volume": 55435.2, "area": 16110.4 }
    ]
  },
  "scene": {
    "scan": {
      "key": "scan:ab12…:s0",
      "scanKey": "scan:ab12…",
      "origin": [412.5, -80.2, 15.0],
      "transform": ["16 numbers"],
      "faceCount": 1204566,
      "vertexCount": 604122
    },
    "regions": "regions:cd34…",
    "items": [
      { "key": "body:9f3e…:faces", "kind": "mesh", "style": "body", "owner": "f5", "bodyId": "f5" },
      {
        "key": "body:9f3e…:edges",
        "kind": "lines",
        "style": "bodyEdges",
        "owner": "f5",
        "bodyId": "f5"
      },
      { "key": "src:77aa…:0", "kind": "mesh", "style": "construction", "owner": "f3" }
    ]
  }
}
```

`cause` tells the renderer how to treat its history: `commit` adds an entry, `checkout` moves
within it, `restore` (kernel restart, project load) and `current` (`doc.get`) reset it.

The renderer fetches payloads it does not have with `scene.fetch({ keys })`. The kernel builds
payloads lazily from factories registered during the rebuild (`SceneStore`, bounded LRU).
Payload formats:

| Kind      | Buffers                                                                                                                                            |
| --------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `scan`    | `positions` f32 (n, 3) relative to `origin` in scan coordinates (smoothed when `displaySmoothing > 0`), `indices` u32 (m, 3), `normals` f32 (n, 3) |
| `regions` | `labels` u16 (m,), `colorIndex` u8 per label                                                                                                       |
| `mesh`    | `positions` f32 (n, 3), `indices` u32 (k, 3), `normals` f32 (n, 3), `faceIds` u32 (k,) (B-Rep face index for picking)                              |
| `lines`   | `segments` f32 (s, 2, 3), `ids` u32 (s,) (edge or entity index), for body edges `faces` u32 (s, 2) (faces on both sides)                           |
| `points`  | `positions` f32 (n, 3)                                                                                                                             |

Styles are semantic (`body`, `bodyEdges`, `previewBody`, `construction`, `constructionEdges`,
`patch`, `sketch`, `sketchPoints`, `section`, `sectionPoints`); DESIGN.md defines their look. The
viewport draws display items by style and knows nothing about feature types. Alignment changes do
not resend the scan: the renderer applies `scene.scan.transform`.

### 4.9 Where state lives

| State                                                              | Owner                                    | Persisted                       | Undo             |
| ------------------------------------------------------------------ | ---------------------------------------- | ------------------------------- | ---------------- |
| Working mesh, regions, alignment, features, settings               | Kernel document                          | project file, session directory | revisions        |
| Feature results, bodies (`TopoDS_Shape`), caches                   | Kernel session (derived)                 | no                              | derived          |
| Document mirror and feature status                                 | Renderer `documentStore` (read-only)     | no                              | –                |
| Display buffers                                                    | Renderer viewport, keyed by payload key  | no                              | derived          |
| Working selection (face mask), tagged with the scan key            | Renderer `selectionStore`                | no                              | renderer history |
| Selected and hovered objects (feature, body, region, edge)         | Renderer `objectSelectionStore`          | no                              | no               |
| Active stage, active tool, selection mode, tool drafts             | Renderer `toolStore`                     | stage per project               | draft only       |
| Camera, visibility, display mode, section plane, deviation display | Renderer `viewStore`                     | project `ui.json`               | no               |
| Language, theme, wheel direction, per-tool options                 | Main `settings.json` (`tools` namespace) | app data                        | no               |
| Recent files, window bounds                                        | Main                                     | app data                        | no               |

Undo/redo: the renderer keeps one linear history of entries `{ kind: 'document', from, to }` and
`{ kind: 'selection', id, scanKey }` (one per brush stroke or selection command). Undo of a
document entry calls `doc.checkout({ revision: from })`; redo calls it with `to`. A new commit
truncates the redo part. Selection entries whose `scanKey` differs from the current scan are
skipped as no-ops. `document.revisionGone` removes the entries that point to pruned revisions.
While a tool with a draft is open, `Ctrl+Z` undoes the last draft or selection change and never
a revision behind the open tool (DESIGN.md 5.1). The selection module registers a
`SelectionHistoryHandler` that keeps the face differences per entry; a tool with a draft history
registers a `DraftHistoryHandler` while it is open (`state/historyStore.ts`).

### 4.10 Project file (`.m2c`)

A ZIP container (deflate), written by `document/project_file.py`:

```
bracket.m2c
  manifest.json       { "format": "mesh-to-cad-project", "version": 1, "app": "0.1.0",
                        "created": "…", "blobs": { "<hash>": { "dtype": "float32", "shape": [n, 3] } } }
  document.json       the document (4.4); source of truth
  ui.json             renderer view state (camera, visibility, stage, deviation display)
  blobs/<hash>.npy    every blob referenced by document.json
  thumbnail.png       256 × 256 viewport capture (P1)
```

- Saving writes a temporary file in the target folder, then replaces the target through the
  retrying helper; the previous file is kept as `<name>.m2c.bak`.
- Loading reads the manifest first; an unknown format fails with `project.corrupt`, a newer
  version with `project.unsupportedVersion`. Migrations are functions
  `migrate_v1_to_v2(document) -> document` with stored fixture files per version.
- After loading, the kernel rebuilds; bodies are never stored, only derived.
- Vertices are stored as float32 relative to `scan.origin` (6e-5 mm resolution at 1 m).

### 4.11 Open CASCADE rules (`cad/`)

- All OCP imports go through `cad/occ_compat.py` (OCP 8 names: collections in `OCP.collections`,
  `TopoDS.Edge(...)` without `_s`, static class methods with `_s`). It also provides
  `quiet_occt()` and `occt_version()`.
- Long OCCT calls run inside `ctx.native(stage)` (3.4).
- Booleans: `SetFuzzyValue(1e-5)`, `SetNonDestructive(True)`, `SetToFillHistory(True)`, then
  `SimplifyResult`. If the result is invalid, run `ShapeFix_Shape`; if it is still invalid, use
  the unsimplified result and add the issue `cad.splitFacesKept`. An empty result of cut or
  intersect is an error (`cad.emptyResult`). Near-coincident planar faces are snapped before the
  boolean.
- `IsDone() == False` and `StdFail_NotDone` are both failures; fillets report
  `cad.filletFailed` with the faulty contour count.
- Sketch profiles close gaps in 2D (shared junction points), never with `ShapeFix_Wire`, which
  inflates vertex tolerances. `check_solid` warns above a vertex tolerance of 1e-4 mm.
- Re-meshing calls `BRepTools.Clean_s` first. Display tessellation: linear deflection 0.05 mm,
  angular 0.3 rad, vertices per B-Rep face (crisp edges), triangles of `TopAbs_REVERSED` faces
  flipped, edges from `PolygonOnTriangulation`. Deviation reference: deflection ≤ tolerance / 20
  (`cad/deflection.py`).
- STEP export uses XCAF (`STEPCAFControl_Writer`) so the product name is exact. It calls
  `STEPControl_Controller.Init_s()` first and checks the return value of every
  `Interface_Static.SetCVal_s` (`write.step.schema`, `write.step.unit = MM`). The file is written
  to a temporary file, read back, compared (valid, solid count, volume relative error ≤ 1e-6),
  and only then renamed over the target.

### 4.12 Algorithm choices

The research notes behind these choices were measured on synthetic parts with exact ground truth.

| Module             | Method                                                                                                                                                                                                                                                                                                                                                                                                         |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `mesh/load.py`     | Binary STL read with `np.fromfile` into float32; weld with int32 indices; OBJ parsed in chunks with a numpy fast path for plain triangles; trimesh for PLY and as the fallback                                                                                                                                                                                                                                 |
| `mesh/repair.py`   | Grid weld with packed int64 keys, degenerate and duplicate removal, component filter (≥ 1 % of the largest, ≥ 100 faces), winding fix by double-cover connected components, outward orientation by signed volume, hole filling by perimeter (centroid fan + relaxation, bow-tie loops skipped); exact index maps                                                                                               |
| `mesh/decimate.py` | `fast_simplification` with `agg = 5`, compaction; runs in a killable child process                                                                                                                                                                                                                                                                                                                             |
| `mesh/normals.py`  | Jet fits (local quadrics) on a voxel subsample, cell 0.5 mm, k = 24: normals, principal curvatures, residual; median residual = scan noise; proposed tolerance = first of 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1.0 mm at or above 2.5 × noise                                                                                                                                                      |
| `mesh/topology.py` | Edge topology from one argsort over half-edges; face graph with masked BFS                                                                                                                                                                                                                                                                                                                                     |
| `segmentation/`    | Crease zones from jet residual; fit-filter-connect region growing; automatic segmentation on a 200 k LOD cached per scan key, labels transferred by nearest centroid, boundary relaxation, residual and merge passes; greedy region colouring on the adjacency graph                                                                                                                                           |
| `fitting/`         | Closed-form initialisation (PCA, Kåsa, normals, Plücker axis of revolution), `least_squares(loss="soft_l1")` on ≤ 30 k points, statistics on all points; `fit_best` with a 15 % penalty per extra parameter; LO-RANSAC for the robust option; constrained refits; direction clustering and value snapping                                                                                                      |
| `snapping.py`      | Preferred values, then the coarsest metric or inch step inside 3 × the parameter uncertainty; common angles; a snap is kept only if the constrained refit raises the RMS by ≤ 5 %                                                                                                                                                                                                                              |
| `alignment/`       | Automatic: largest plane (area) → XY, largest plane within 10° of perpendicular → XZ, origin at the bounding-box minimum, then the 3-2-1 frame; PCA with third-moment sign rule as the fallback when no two planes exist; faces: 3-2-1 frame from plane/plane/plane or axis/plane                                                                                                                              |
| `sketch/`          | Planar or rotational section in an explicit frame; noise from raw section points, tolerance `max(6σ, 0.05 mm)`; dynamic-programming split into lines and arcs (BIC cost, prefix moments); hyper circle fit + Gauss-Newton; constraint inference; value snapping via `snapping.py` (lengths, positions from the origin, radii, angles, equal radii, bolt circles); joint penalty least squares; exact junctions |
| `cad/`             | Prism, revolve, primitive solids, half-space trim, fuzzy booleans, fillet and chamfer as in 4.11, face tags through operation history                                                                                                                                                                                                                                                                          |
| `freeform/`        | P-spline height field converted exactly to `Geom_BSplineSurface`; loft through normalised periodic sections with `BRepOffsetAPI_ThruSections`                                                                                                                                                                                                                                                                  |
| `inspection/`      | Seeded vertex-ring descent with per-face walkers and B-Rep edge seeds; pseudo-normal sign; per-face statistics and histogram; measurements between primitives in closed form                                                                                                                                                                                                                                   |

---

## 5. Frontend

### 5.1 Module layout (`src/renderer/`)

```
src/renderer/
  main.tsx                 entry: i18n, settings, KernelClient, <AppShell/>
  index.html, env.d.ts
  app/                     AppShell, TitleBar, MenuBar, StageTabs, ToolRow, StatusBar, Splitter,
                           shortcuts, command registry and keymap, dialog and overlay hosts
  app/empty-state/         viewport empty state (import, open, example, recent)
  app/status/              status bar items of the shell (triangles, kernel state)
  ui/                      UI primitives (DESIGN.md 4), one folder per component with a CSS module
  styles/                  tokens.css, base.css, design-rules test
  state/                   zustand stores (5.2)
  kernel/                  KernelClient, KernelFailure, documentSync, error descriptions
  viewport/                SceneController, CameraRig, PointerRouter, picking, handles, palette;
                           api.ts is the contract (5.8)
  tools/
    framework/             ToolDefinition, registry, ToolHost, ToolPanel, hooks, tool actions
    <tool-id>/             one folder per tool (5.6)
  features/<type>/         feature views: icon, type name, edit tool, summary, properties (5.7)
  selection/               selection store and commands, selection status item
  inspection/              tolerance status item, deviation legend and colour bands (planned)
  panels/                  ProjectTree, ObjectProperties
  project/                 file commands, recovery dialog, dirty tracking (planned)
  settings/                settings dialog; shortcut help and about dialog (planned)
  i18n/                    setup, format.ts, locales/<lang>/common.json, locales/<lang>/domains/*.json
  lib/                     small pure modules named by purpose (numberInput.ts, deviationBands.ts)
  testing/                 end-to-end test hooks (7.6)
```

There is no `utils.ts`. Components stay below 300 lines; a component that grows beyond that is
split by responsibility. `lib/deviationBands.ts` is the single implementation of the deviation
band table; the legend, the viewport colour texture and the statistics all use it.

### 5.2 State management

**Decision: zustand 5, vanilla stores.** Stores are plain modules that the non-React
`SceneController` can subscribe to; components subscribe to slices through selectors, so a
progress event does not re-render the tree; there is no provider nesting and almost no API to
learn. Redux adds ceremony without benefit here; React context re-renders every consumer.

| Store                  | Contents                                                                                 | Written by                    |
| ---------------------- | ---------------------------------------------------------------------------------------- | ----------------------------- |
| `documentStore`        | snapshot (revision, document, status, scene manifest)                                    | only `kernel/documentSync.ts` |
| `selectionStore`       | selection version, count, scan key, face mask reference                                  | selection tools and commands  |
| `objectSelectionStore` | selected and hovered object (`feature`, `body`, `region`, `edge`)                        | tree, viewport picking        |
| `toolStore`            | active stage, panel tool, activation data, edit target, selection mode, draft dirty flag | `ToolHost`, stage tabs        |
| `viewStore`            | display mode, projection, visibility (scan / bodies / both), section plane, deviation    | view commands, viewport       |
| `jobStore`             | kernel status, running requests with progress                                            | `KernelClient`                |
| `historyStore`         | undo/redo entries (4.9)                                                                  | `documentSync`, selection     |
| `settingsStore`        | preferences mirrored from main, including the validated `tools` namespace                | settings dialog, tools        |
| `messageStore`         | status-bar messages and the _Meldungen_ list                                             | anyone via `showMessage()`    |

Rules: stores hold serialisable data only. Large typed arrays (face masks, display buffers) live
in plain objects referenced by a version number. Each store module exports the store, a selector
hook and named action functions; components never call `setState` directly.

### 5.3 Kernel client and document sync

```ts
const job = kernel.call('fit.preview', { faces, kind: 'auto' }, { lane: 'fit.preview:fit-primitive' });
job.onProgress((fraction, stage) => …);
const result = await job.result;      // typed from the generated method tables
job.cancel();
```

`KernelClient` walks the parameters, replaces typed arrays with buffer references, collects the
`ArrayBuffer`s, and decodes the response back into typed arrays. It rejects with a `KernelFailure`
holding `code`, `params`, `details`. `documentSync.ts` subscribes to `documentChanged`, writes
`documentStore` and `historyStore`, and the viewport fetches the payloads it lacks.

Display payloads travel kernel → main → renderer as `ArrayBuffer`s in `ipcRenderer.invoke`
results, capped by `MAX_FRAME_BYTES` (section 8, item 19).

### 5.4 Commands, keymap, menus

Everything a user can trigger is an `AppCommand` (`app/commands/types.ts`):

```ts
export interface AppCommand {
  id: string; // 'selection.invert'
  labelKey: string; // i18n key
  icon?: LucideIcon;
  shortcut?: Shortcut; // { key: 'I', ctrl: true, shift: true, scope: 'viewport' }
  placements?: readonly Placement[]; // menu entries and context menus
  isEnabled?: (context: CommandContext) => boolean;
  run: (context: CommandContext, target?: ContextTarget) => void | Promise<void>;
}
```

`Placement` is `{ menu: 'file' | 'edit' | 'view' | 'help', group, order }` or
`{ context: 'tree:feature' | 'tree:region' | 'tree:body' | 'viewport:scan' | 'viewport:body' }`.
Menus, context menus, the keymap and the shortcut help (`Ctrl+/`) are generated from the command
registry. Shortcut scopes: `global`, `viewport` (viewport or tree focused, never in text fields),
`sketch` (sketch mode only); a key resolves in the order sketch, viewport, global. A unit test
fails on duplicate shortcuts within a scope. Every tool automatically gets an "activate tool"
command.

### 5.5 Tool framework (`tools/framework/`)

`ToolDefinition` (`tools/framework/types.ts`):

```ts
export interface ToolDefinition {
  id: string; // kebab-case, equals the folder name
  kind: 'panel' | 'selection' | 'action';
  status: 'ready' | 'planned'; // planned: disabled in development, hidden in release builds
  stages: readonly StageId[]; // prepare | align | model | inspect; [] for import
  group: ToolGroup; // tool-row group (DESIGN.md 3.2)
  icon: LucideIcon;
  primary?: boolean; // label shown next to the icon in the tool row
  shortcut?: Shortcut;
  availability?(context: ToolContext): Availability;
  Panel?: ComponentType<ToolPanelProps>; // panel tools
  run?(): void | Promise<void>; // action tools
  edits?: readonly FeatureTypeId[]; // double-click in the tree opens this tool
  confirmDiscard?: boolean; // ask before discarding a changed draft
}
```

- **Panel tools** (fit, extrude, …) open in the properties panel with header, sections and the
  OK/Abbrechen footer. Only one panel tool is open at a time.
- **Selection modes** (brush, smart select, lasso, rectangle) are independent of panel tools: a
  selection mode stays usable while a panel is open, and a panel that takes the selection as input
  re-runs its preview when the selection changes. Brush size and _Nur sichtbare_ sit in the tool
  row while a selection mode is active. When a fit is edited, its stored triangles become the
  working selection; the previous selection returns when the tool closes.
- **Action tools** run once (reset alignment, delete selected triangles).
- `ToolHost` owns the life cycle (DESIGN.md 5.1): `Enter` commits, `Shift+Enter` applies and
  keeps the tool, `Esc` aborts the current gesture first and cancels the tool second; `Esc` never
  commits. Opening another panel tool while the draft of a `confirmDiscard` tool has changed asks
  first (`DiscardDialog`).
- Hooks for panels (`tools/framework/hooks.ts`):
  - `usePreview(method, params, { enabled, lane })`: 150 ms debounce, lane per tool, stale results
    dropped, returns `{ status: 'idle' | 'computing' | 'ok' | 'error', result, error }`.
  - `useCommit(handler, { enabled })`: binds OK, `Enter` and the disabled state.
  - `useToolDraft(initial)` and `useToolOverlay()` (planned): draft parameters with draft-level
    undo; a scene overlay disposed on close.
- Pointer handling goes through `viewport.addInteraction(interaction)`. Handlers return `true` to
  consume an event (then no navigation happens). Interactions added later are asked first, so a
  panel tool's handle drag wins over the active selection mode.

### 5.6 Tool catalogue

Tool ids, stages and groups as registered in `src/renderer/tools/`. _Status_ is the state of the
skeleton.

| Tool id                   | Stages                 | Group     | Kind      | Key              | Priority | Status  |
| ------------------------- | ---------------------- | --------- | --------- | ---------------- | -------- | ------- |
| `import-mesh`             | – (Datei, empty state) | mesh      | panel     | `Ctrl+I`         | P0       | minimal |
| `mesh-info`               | prepare                | analysis  | panel     | –                | P0       | planned |
| `mesh-repair`             | prepare                | mesh      | panel     | –                | P0       | planned |
| `mesh-remove-small-parts` | prepare                | mesh      | panel     | –                | P0       | planned |
| `mesh-fill-holes`         | prepare                | mesh      | panel     | –                | P0       | planned |
| `mesh-decimate`           | prepare                | mesh      | panel     | –                | P0       | planned |
| `mesh-smooth`             | prepare                | mesh      | panel     | –                | P0       | planned |
| `mesh-delete-faces`       | prepare                | mesh      | action    | `Entf`           | P0       | planned |
| `select-brush`            | prepare, align, model  | selection | selection | `B`              | P0       | planned |
| `select-smart`            | prepare, align, model  | selection | selection | `W`              | P0       | planned |
| `select-lasso`            | prepare, align, model  | selection | selection | `L`              | P0       | planned |
| `select-rectangle`        | prepare, align, model  | selection | selection | –                | P0       | planned |
| `segment`                 | align, model           | regions   | panel     | –                | P0       | planned |
| `align-auto`              | align                  | align     | panel     | –                | P0       | planned |
| `align-faces`             | align                  | align     | panel     | –                | P0       | planned |
| `align-reset`             | align                  | align     | action    | –                | P0       | planned |
| `fit-primitive`           | model                  | fit       | panel     | `A`              | P0       | planned |
| `reference-geometry`      | model                  | reference | panel     | –                | P0       | planned |
| `section-sketch`          | model                  | sketch    | panel     | `S`              | P0       | planned |
| `extrude`                 | model                  | solid     | panel     | `E`              | P0       | planned |
| `revolve`                 | model                  | solid     | panel     | `R`              | P0       | planned |
| `primitive-body`          | model                  | solid     | panel     | –                | P0       | planned |
| `trim`                    | model                  | solid     | panel     | –                | P0       | planned |
| `combine`                 | model                  | solid     | panel     | –                | P0       | planned |
| `fillet`                  | model                  | solid     | panel     | –                | P0       | planned |
| `freeform-patch`          | model                  | freeform  | panel     | –                | P1       | planned |
| `loft`                    | model                  | freeform  | panel     | –                | P1       | planned |
| `measure`                 | inspect                | inspect   | panel     | `M`              | P0       | planned |
| `deviation`               | inspect                | inspect   | panel     | `D` toggles view | P0       | planned |
| `report`                  | inspect                | inspect   | action    | –                | P1       | planned |
| `export-step`             | inspect                | export    | panel     | `Ctrl+E`         | P0       | planned |
| `export-stl`              | inspect                | export    | panel     | –                | P0       | planned |

### 5.7 Extension registries

All registries are discovered with `import.meta.glob(..., { eager: true })` in the renderer and
`pkgutil.iter_modules` in the kernel. Adding a tool, command, feature type or translation never
requires editing a shared file. `src/renderer/registries.test.ts` validates them.

| Extension        | Location                                                        | Export                                                                                                       |
| ---------------- | --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Tool             | `src/renderer/tools/<tool-id>/index.ts`                         | `export const tool: ToolDefinition`                                                                          |
| Tool strings     | `src/renderer/tools/<tool-id>/locales/{de,en}.json`             | namespace `tools` under `camelCase(<tool-id>)`; `label`, `tooltip`, `howTo` (2–4 sentences)                  |
| Commands         | `src/renderer/**/*.commands.ts`                                 | `export const commands: readonly AppCommand[]`                                                               |
| Feature view     | `src/renderer/features/<type>/view.ts` + `locales/{de,en}.json` | `export const featureView: FeatureView` (icon, base name, edit tool, summary, `Properties`)                  |
| Status bar item  | `src/renderer/**/*.status.tsx`                                  | `export const statusItem: StatusItem`; orders: selection 10, faces 20, tolerance 30, deviation 40, kernel 50 |
| Dialog           | `src/renderer/**/*.dialog.tsx`                                  | `export const dialog: ComponentType` (mounted once, manages its own open state)                              |
| Viewport overlay | `src/renderer/**/*.overlay.tsx`                                 | `export const overlay: ViewportOverlay` (anchor, visibility, component)                                      |
| Kernel strings   | `src/renderer/i18n/locales/{de,en}/domains/<domain>.json`       | keys `errors`, `issues`, `progress`, merged into namespaces of those names                                   |
| Protocol command | `kernel/m2c_kernel/commands/<group>.py`                         | `@command(...)` functions                                                                                    |
| Feature type     | `kernel/m2c_kernel/features/types/<type>.py`                    | `@feature_type(...)` class                                                                                   |
| Codes            | `kernel/m2c_kernel/codes/<domain>.py`                           | `ErrorCode`, `IssueCode`, `ProgressStage` enums                                                              |
| Generated types  | `src/shared/protocol/generated/<module>.ts`                     | codegen output (3.5.7)                                                                                       |

PyInstaller does not see dynamic imports, so the spec collects `m2c_kernel` submodules explicitly.

### 5.8 Viewport (`src/renderer/viewport/`)

`SceneController` is a plain class with no React inside; `ViewportCanvas.tsx` mounts it and
registers it with `registerViewport`. Tools and panels use only the interface in
`viewport/api.ts` (`getViewport()` or `useViewport()`):

| Member                                                              | Purpose                                                                                                                                        |
| ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `scan`                                                              | `setSelection`, `updateSelection`, `setHover`, `setHidden`, `setFaceStates` (pass/fail), `setRegions`, `setDeviation`, `setOpacity`; `scanKey` |
| `camera`                                                            | `fitAll`, `fitBox`, `setStandardView`, `lookAlong`, `setProjection`, `setOrbitLocked`                                                          |
| `handles`                                                           | `arrow`, `arc`, `plane`, `point` handles with `onChange` / `onCommit`                                                                          |
| `pick`, `pickScanFacesInCircle`, `pickScanFacesInPolygon`           | scan face, body face, edge and item picking; brush and lasso picking                                                                           |
| `scanTopology`                                                      | face neighbours and centroids (grow/shrink ring, smart select seeds)                                                                           |
| `screenToRay`, `worldToScreen`                                      | mapping for sketch painting and labels                                                                                                         |
| `setPreviewItems(owner, items)`                                     | draws the display items of a `doc.preview` result                                                                                              |
| `highlight(target)`                                                 | hover and selection highlight of bodies, edges and construction items                                                                          |
| `addInteraction`, `createOverlay`, `invalidate`, `capture`, `stats` | pointer handling, tool overlays, render on demand, screenshots, diagnostics                                                                    |

**Scan rendering.** The scan is drawn as **non-indexed** geometry: face `i` owns vertices
`3i … 3i+2`. WebGL 2 has no `gl_PrimitiveID`, and per-face state must be per vertex; de-indexing
makes the per-face attributes exact and keeps `faceIndex` from raycasting identical to the
kernel's face index. Attributes: `position` f32 × 3, `normal` (planned: 4 × int16 normalised or
octahedral, which ANGLE/D3D11 reads natively), `aFlags` u8 (bit 0 selected, 1 hover, 2 hidden,
3–4 face state), `aRegion` u16 and `aDeviation` f32 (planned; CPU vertex colours in the
skeleton). One `onBeforeCompile` chunk on `MeshStandardMaterial` mixes base colour, region palette,
deviation colour map (1D `DataTexture`, uniforms tolerance, range, scheme), selection and hover
tints, and the back-face tint. Selection updates write `aFlags` for changed faces and call
`addUpdateRange`; nothing is rebuilt.

**Large scans** (planned): `renderer.compileAsync` at startup, chunked buffer uploads,
de-indexing, centroids, adjacency and the `MeshBVH` (`indirect: true`) in `workers/meshPrep.worker.ts`
(serialised back with `MeshBVH.serialize`). Visible-only brush picking reads a face-id render
target (`gl_VertexID / 3` is the face index on the non-indexed geometry) and uses the BVH only
for sub-pixel faces. The skeleton builds the BVH on the UI thread and approximates visible-only by
facing direction.

**Bodies and construction.** Display items (4.8) are drawn by style. Body meshes keep vertices per
B-Rep face and are drawn with a polygon offset in front of the scan, so a body lying within the
tolerance of the scan never z-fights with it. `faceIds` enable body-face picking; `bodyEdges` lines
are pickable within 5 px for the fillet tool. Construction surfaces use the construction style
with depth offset. `Space` cycles the visibility _Scan / Körper / beide_.

**Navigation.** `CameraRig` wraps `OrbitControls` with left button free for tools, middle drag
pan, right drag orbit, zoom to the cursor; orthographic by default (DESIGN.md 7.1). The orbit
pivot is the picked point under the cursor (planned). Render on demand: every change calls
`invalidate()`, which schedules one frame.

**View cube and axis triad** (planned) are drawn in scissored corners of the same WebGL context and
picked by raycasting their own scenes (6 faces, 12 edges, 8 corners). Labels are canvas textures
regenerated on language or theme change. Dragging on the view cube orbits (touchpads).

**Section plane** (planned). `viewStore.sectionPlane` drives clipping planes on scan and body
materials; the gizmo comes from the handle factory. The section outline of the scan is computed
in the renderer from the displayed triangles (no kernel call), so it can never compete with the
sketch tool's kernel requests. Hatched caps for bodies are P1.

**Theme.** The controller reads colour tokens with `getComputedStyle` once per theme change; no
colour literal appears in viewport code except the palette module, which is the single place for
region and deviation colours (DESIGN.md 6).

### 5.9 i18n and formatting

- i18next with react-i18next. Languages `de` (default and fallback) and `en`. Namespaces:
  `common`, `tools`, `features`, `commands`, `errors`, `issues`, `progress`.
- Keys are English camelCase paths (`tools:fitPrimitive.result.rms`). Codes are keys
  (`errors:fit.tooFewFaces`). Values use i18next interpolation with formatted parameters.
- Counts use i18next plural keys (`faces_one`, `faces_other`); lists use `Intl.ListFormat`
  through `format.list`.
- `i18n/format.ts` is the only place that formats numbers, lengths, angles, areas, volumes,
  counts, percentages, lists and dates, using `Intl` with the UI locale. Lengths show three
  decimals and the unit (`0,041 mm` / `0.041 mm`), angles two decimals and `°`.
- `lib/numberInput.ts` parses user input per locale: in German `,` is the decimal separator and
  `.` groups thousands in count fields; length fields reject ambiguous input such as `1.000`
  with an inline hint.
- The language switches at runtime without reload; the view cube labels follow.
- F1 opens the bundled local help page for the active tool (`window.m2c.app.openHelp`, pages in
  `resources/help/<lang>/`); the tool's
  `howTo` text is shown in the collapsible _So geht's_ panel section.

### 5.10 Styling

Plain CSS: `styles/tokens.css` defines every colour, size and font as custom properties per theme
(`:root[data-theme="dark"]`, `…="light"`); components use CSS modules next to the component. No
CSS framework, no CSS-in-JS. `styles/designRules.test.ts` enforces DESIGN.md mechanically: no
colour literals outside `tokens.css`, no gradients or `backdrop-filter`, no radius above 4 px, no
font size below 12 px, no hex colours in TypeScript outside `viewport/palette.ts`.

---

## 6. Repository and conventions

### 6.1 Layout

```
Mesh-to-CAD/
  .github/
    workflows/ci.yml            release.yml (planned)
    ISSUE_TEMPLATE/             bug_report.yml, feature_request.yml, config.yml
    pull_request_template.md  dependabot.yml
  changes/                      changelog fragments, merged into CHANGELOG.md at release
  docs/
    ARCHITECTURE.md, DESIGN.md
    user/                       getting-started.md, getting-started.de.md (planned)
    images/                     README screenshots (planned)
  kernel/                       Python kernel (4.1)
  src/
    main/  preload/  renderer/
    shared/                     bridge.ts, ipc.ts, settings.ts, theme.ts, testHooks.ts,
                                protocol/{frame.ts, codec.ts, wireTypes.ts, generated/}
  tests/
    e2e/                        Playwright specs (Electron)
    fixtures/                   frame test vectors, fake kernel for main-process tests
  scripts/                      dev.mjs, build.mjs, start.mjs, py.mjs, paths.mjs,
                                check-versions.mjs; build-kernel.mjs, kernel-smoke.mjs,
                                collect-licenses.py, generate-examples.py (planned)
  resources/                    icons, help pages; examples and licences generated, git-ignored
  package.json  package-lock.json  tsconfig*.json  vite.*.config.ts  vitest.config.ts
  playwright.config.ts  eslint.config.js  .prettierrc.json  .prettierignore
  .editorconfig  .gitignore  .gitattributes  .nvmrc  .python-version
  README.md  README.de.md  LICENSE  CONTRIBUTING.md  CODE_OF_CONDUCT.md  SECURITY.md
  CHANGELOG.md  THIRD_PARTY_NOTICES.md
```

`.gitignore`: `.work/`, `.venv/`, `node_modules/`, `dist/`, `release/`, `out/`, `test-results/`,
`playwright-report/`, `coverage/`, `*.log`, `__pycache__/`, `*.pyc`, `.pytest_cache/`,
`.mypy_cache/`, `.ruff_cache/`, `resources/examples/`, `resources/licenses/`, `*.m2c.bak`,
`.DS_Store`, `Thumbs.db`. `kernel/m2c-kernel.spec` is versioned (do not ignore `*.spec`).
`.work/` holds local research notes and planning files and is never committed.

`.gitattributes`: `* text=auto eol=lf`; `*.png *.ico *.stl *.ply *.m2c *.npy binary`;
`*.step -diff`.

`.editorconfig`: UTF-8, LF, final newline, trim trailing whitespace (not in `*.md`), 2 spaces for
TS/JS/JSON/CSS/YAML/MD, 4 spaces for Python.

### 6.2 GitHub files

| File                            | Content                                                                                                                                                                                                                                                                                                                     |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `README.md`                     | One-sentence description; status line; what it does (factual list); requirements; download; build from source; documentation links; licence; acknowledgements. Link to `README.de.md`. No badge wall, no emojis, no marketing adjectives. Screenshot of a real scan once available.                                         |
| `README.de.md`                  | Same structure in German.                                                                                                                                                                                                                                                                                                   |
| `LICENSE`                       | MIT, `Copyright (c) 2026 Mesh-to-CAD contributors`.                                                                                                                                                                                                                                                                         |
| `CONTRIBUTING.md`               | Prerequisites, setup, dev mode, checks, project structure, how to add a tool, command or feature type, i18n rule, tests, Conventional Commits, changelog fragments, PR checklist.                                                                                                                                           |
| `CODE_OF_CONDUCT.md`            | Contributor Covenant 2.1 by reference; reports through a private advisory or to the maintainers.                                                                                                                                                                                                                            |
| `SECURITY.md`                   | Supported versions; GitHub private vulnerability reporting; scope (file parsing, Electron hardening, the kernel process).                                                                                                                                                                                                   |
| `CHANGELOG.md`                  | Keep a Changelog 1.1, SemVer. Pull requests add a fragment `changes/<topic>.md` instead of editing the file, so parallel branches never conflict; the release merges the fragments.                                                                                                                                         |
| `THIRD_PARTY_NOTICES.md`        | Bundled components with licence: Electron/Chromium, React, three.js, three-mesh-bvh, zustand, i18next, Radix UI, lucide, Python, numpy, scipy, trimesh, networkx, fast-simplification, rtree/libspatialindex, cadquery-ocp/OCP, Open CASCADE (LGPL-2.1 with exception; DLLs stay replaceable), VTK, PyInstaller bootloader. |
| `.github/workflows/ci.yml`      | Push and PR on `windows-latest`: Node 24 and Python 3.12 with caches; venv; `pip install -r kernel/requirements-dev.txt`; `npm ci`; lint, typecheck, codegen check, kernel lint, kernel tests, vitest, build, e2e smoke. Weekly schedule adds the slow suite.                                                               |
| `.github/workflows/release.yml` | On tag `v*`: all checks, `npm run dist`, frozen-kernel tests (the gate), packaged smoke test, Microsoft Defender scan of the installer, upload with SHA-256 to a draft release.                                                                                                                                             |
| `ISSUE_TEMPLATE/*.yml`          | Bug report (version, Windows, steps, expected, actual, scan size, log excerpt), feature request (problem, workflow, alternatives); blank issues disabled.                                                                                                                                                                   |
| `pull_request_template.md`      | Summary, related issue, checklist: tests, `npm run check`, strings in de and en, screenshots for UI changes, changelog fragment.                                                                                                                                                                                            |
| `dependabot.yml`                | Weekly for npm, pip (`/kernel`) and GitHub Actions; grouped minor updates.                                                                                                                                                                                                                                                  |

### 6.3 Toolchain and pinned versions

Exact versions, all verified on the development machine (Windows 11, Node 24, npm 11, Python
3.12.10). Dependencies are pinned exactly (`--save-exact`, `==`); no dependency needs a C/C++
compiler (only prebuilt wheels).

| Python runtime      | Version                     | Python dev  | Version |
| ------------------- | --------------------------- | ----------- | ------- |
| numpy               | 2.5.3                       | pytest      | 9.1.1   |
| scipy               | 1.18.1                      | ruff        | 0.16.9  |
| trimesh             | 5.1.0                       | mypy        | 2.3.1   |
| networkx            | 3.7                         | pyinstaller | 6.22.3  |
| fast-simplification | 0.2.0                       |             |         |
| cadquery-ocp        | 8.0.1.0.0 (pulls vtk 9.6.2) |             |         |
| rtree               | 1.4.1                       |             |         |

| Node runtime                  | Version | Node dev                                                  | Version                         |
| ----------------------------- | ------- | --------------------------------------------------------- | ------------------------------- |
| react, react-dom              | 19.3.0  | electron                                                  | 44.4.5                          |
| three                         | 0.186.1 | electron-builder                                          | 26.15.3                         |
| three-mesh-bvh                | 0.9.15  | vite                                                      | 8.3.1                           |
| zustand                       | 5.0.15  | @vitejs/plugin-react                                      | 6.1.1                           |
| i18next                       | 26.4.2  | typescript                                                | 6.0.3                           |
| react-i18next                 | 17.0.15 | vitest                                                    | 5.0.2                           |
| lucide-react                  | 1.48.0  | @playwright/test                                          | 1.63.0                          |
| @radix-ui/react-dropdown-menu | 2.1.24  | eslint, @eslint/js                                        | 10.11.0, 10.0.1                 |
| @radix-ui/react-context-menu  | 2.3.7   | typescript-eslint                                         | 8.70.1                          |
| @radix-ui/react-tooltip       | 1.2.16  | eslint-plugin-react-hooks                                 | 7.1.1                           |
| @radix-ui/react-slider        | 1.4.7   | eslint-config-prettier, globals                           | 10.1.8, 17.12.0                 |
| @radix-ui/react-dialog        | 1.1.23  | prettier                                                  | 3.9.9                           |
|                               |         | happy-dom                                                 | 20.14.5                         |
|                               |         | @types/react, @types/react-dom, @types/three, @types/node | 19.3.0, 19.3.0, 0.186.0, 26.6.3 |

TypeScript is 6.0.3, not the native TypeScript 7: typescript-eslint 8.70 supports only
TypeScript below 6.1.

**npm scripts** (`scripts/py.mjs` runs the venv Python, `M2C_PYTHON` overrides it):

| Script                     | Runs                                                                                                           |
| -------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `dev`                      | `node scripts/dev.mjs`: Vite dev server on 127.0.0.1:5173, main/preload watch build, Electron restart          |
| `build`                    | Vite builds of renderer, main, preload into `dist/`                                                            |
| `start`                    | Electron on the built `dist/`                                                                                  |
| `typecheck`                | `tsc` for `tsconfig.node.json`, `tsconfig.web.json` and the tests (`tsconfig.json`)                            |
| `lint`                     | `eslint . && prettier --check .`                                                                               |
| `format`                   | `prettier --write .` and `ruff format kernel`                                                                  |
| `test`                     | `vitest run`                                                                                                   |
| `test:e2e`                 | `npm run build && playwright test`                                                                             |
| `kernel:test`              | `pytest -m "not slow"` in `kernel/`; extra arguments select paths (`npm run kernel:test -- kernel/tests/mesh`) |
| `kernel:test:all`          | the same without `-m "not slow"`                                                                               |
| `kernel:lint`              | `ruff check kernel && ruff format --check kernel && mypy` (in `kernel/`)                                       |
| `codegen`, `codegen:check` | `python -m m2c_kernel.protocol.codegen [--check]`                                                              |
| `check`                    | versions, lint, typecheck, test, kernel:lint, kernel:test, codegen:check                                       |
| `build:kernel`, `dist`     | PyInstaller onedir into `release/kernel/`; installer with electron-builder (the scripts they call are planned) |

**Configuration.**

- TypeScript: `strict`, `noUncheckedIndexedAccess`, `noImplicitOverride`, `verbatimModuleSyntax`,
  `moduleResolution: "Bundler"`, `target: "ES2023"`, `jsx: "react-jsx"`; path aliases
  `@renderer/*`, `@shared/*`. `package.json` has `"type": "module"`; main and preload are built
  to `dist/main/index.cjs` and `dist/preload/index.cjs`. Vite uses `base: './'`.
- ESLint (flat config): `@eslint/js` recommended, `typescript-eslint` `recommendedTypeChecked`,
  `react-hooks`, `eslint-config-prettier`. Project rules: `no-console` (use the logger),
  `max-lines` 400 (warn), `@typescript-eslint/no-explicit-any`, `consistent-type-imports`.
- Prettier: `printWidth 100`, `singleQuote`, `trailingComma "all"`, `semi`.
- Ruff: line length 100, target py312, rules `E F W I UP B SIM N RUF D A005`. Docstrings (Google
  convention, one-line docstrings allowed) are required only in `**/api.py` and `commands/*.py`;
  elsewhere a docstring is written when it says something the signature does not.
- mypy: `disallow_untyped_defs`, `disallow_incomplete_defs`, `no_implicit_optional`,
  `warn_unused_ignores`, `warn_return_any`, `strict_equality`; `ignore_missing_imports` only for
  `OCP.*`, `trimesh.*`, `fast_simplification.*`, `rtree.*`, `networkx.*`, `scipy.*`.

### 6.4 Code conventions

- **Language:** code, identifiers, comments, commit messages and developer docs in English. UI
  text only in locale files.
- **Naming, TypeScript:** components and classes `PascalCase` in `PascalCase.tsx`/`.ts`; other
  modules `camelCase.ts`; folders `kebab-case`; functions and variables `camelCase`; constants
  `UPPER_SNAKE_CASE` only for true constants; types without `I` prefix; named exports.
- **Naming, Python:** modules and functions `snake_case`, classes `PascalCase`, constants
  `UPPER_SNAKE_CASE`; private helpers with a leading underscore.
- **Wire names:** methods `group.camelCase`, codes `domain.camelCase`, feature types
  `camelCase`, i18n keys `camelCase` paths, `data-testid` `kebab-case`.
- **Comments** explain why, not what. No commented-out code, no banner comments, no decorative
  separators, no emojis, no TODOs without an issue number.
- **Errors:** kernel code raises `KernelError` with a code for every user-relevant failure.
  Renderer code never shows raw exception messages.
- **Types:** no `any`, no `# type: ignore` without a reason; Python public functions fully typed;
  numpy arrays typed with `npt.NDArray[np.float64]` and friends.
- **Files:** one responsibility per file; UI components below 300 lines, Python modules below
  600 lines.

### 6.5 Git workflow and versioning

- `main` is protected: pull requests only, CI must pass, squash merge.
- Branches `feat/<topic>`, `fix/<topic>`, `docs/<topic>`, `chore/<topic>`.
- Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `build:`, `ci:`, `chore:`).
- SemVer. The version lives in `package.json`; `kernel/m2c_kernel/__init__.py` must match
  (`scripts/check-versions.mjs` runs in CI). Tags `v0.1.0`.
- A change to a shared contract (protocol, document model, `viewport/api.ts`, stores, registries,
  shared kernel modules) lands in its own small pull request together with its contract test,
  before the feature work that needs it.

---

## 7. Testing

### 7.1 Layers

| Layer                  | Tool                                                   | Location                      | Runs in CI                                   |
| ---------------------- | ------------------------------------------------------ | ----------------------------- | -------------------------------------------- |
| Kernel algorithms      | pytest                                                 | `kernel/tests/<area>/`        | yes (`not slow`); slow weekly and on release |
| Kernel contracts       | pytest                                                 | `kernel/tests/contracts/`     | yes                                          |
| Protocol (Python side) | pytest, kernel as subprocess                           | `kernel/tests/protocol/`      | yes                                          |
| Frozen kernel          | pytest against the PyInstaller exe (`M2C_KERNEL_EXE`)  | `kernel/tests/frozen/`        | weekly and release (the packaging gate)      |
| Main process           | vitest (node) against `tests/fixtures/fake-kernel.mjs` | `src/main/**/*.test.ts`       | yes                                          |
| Renderer logic         | vitest (node; `happy-dom` only where a DOM is needed)  | next to the code, `*.test.ts` | yes                                          |
| Application            | Playwright `_electron`                                 | `tests/e2e/`                  | smoke yes; workflow as tools land            |
| Real scans             | manual acceptance (1.5)                                | checklist in the release PR   | no                                           |

### 7.2 Synthetic ground truth

`kernel/tests/synthetic/` generates every test input from code; no binary fixtures in git.

1. **Build** a part with known surfaces. `meshes.py` has analytic patches and simple solids
   (`primitive_patch`, `sphere_scan`, `box_scan`); `parts.py` builds OCCT parts: `block_part` (the
   16-face test block: 100 × 70 × 20 with R6 edge fillets, D30 boss with R3 torus fillet and 2 mm
   chamfer cone, D16 hole, R9 spherical dimple) and `plate_part` (100 × 60 × 10 plate with R8
   fillets, an 8 mm chamfer, an R10 notch and two D12 holes). An obround, a tube for lofts and a
   height field are added by the domains that need them.
2. **Tessellate** and subdivide to a target edge length; keep the B-Rep face id per triangle and
   the analytic surface per face (`SyntheticPart.labels`, `surfaces`, `distance_to_truth`).
3. **Add scanner-like noise** (`noise.py`): Gaussian displacement along the normal (σ 0.02–0.05),
   0.1–1 % spikes, and for repair tests holes, debris, duplicate and degenerate faces and a flipped
   patch. Apply a random rigid pose. Seeds are fixed.
4. **Reconstruct** with the code under test.
5. **Assert** against ground truth with the tolerances of 1.5: parameter errors, IoU per face,
   volumes, corner positions.

Size variants: `small` (≤ 200 k faces, default tests), `full` (≈ 2 M faces, `@pytest.mark.slow`).
The default kernel suite must finish in under 4 minutes. Markers: `slow`, `occt`, `frozen`.

### 7.3 Protocol tests

- Python: frame encode/decode round trip (random headers and buffers, alignment, truncated
  frames), wire conversion (camelCase, dictionary keys kept, discriminated unions, NaN → null,
  ranges), buffer decoding without copies, codegen output and `--check`.
- Subprocess (the tests start the kernel with `M2C_DEBUG_COMMANDS=1`): `ready`; `system.info`
  includes the OCCT version; unknown method, invalid parameters and a main-only method sent with
  `origin: renderer` give the right codes; `debug.stdoutNoise` (C-level writes) does not corrupt
  the stream; `debug.sleep` is cancelled within 500 ms; lane superseding; `kernel.busy` during an
  exclusive method; progress events in order; `debug.nativeBlock` holds the GIL and the host still
  resolves the cancel at once; `debug.crash` exits and a restart on the same session directory
  restores the checked-out revision.
- TypeScript: the same frame test vectors against `src/shared/protocol/frame.ts`; `KernelHost`
  against the fake kernel: routing, progress, cancel with grace period and `unresponsive`,
  crash, restart, `kernel.notAllowed` for main-only methods.

### 7.4 Frontend tests

vitest covers: stores and actions, selection history with scan keys, numeric input parsing
(`25,4/2`, `1 in`, `200.000` in count and length fields), `format.ts` in both locales (plurals,
lists), keymap conflicts, registry validation (unique ids, icons, de and en labels, valid stages
and groups), i18n parity (same keys in both languages; every generated code translated), tool
hooks (`usePreview` debounce and stale drops), viewport maths (camera fit, standard views,
handles, colour bands), and the design rules of 5.10.

### 7.5 Real-scan acceptance

The set of 1.5 is kept outside the repository unless its licence allows redistribution. The
release pull request records, per scan: time to rebuild, STEP deviation from the nominal
dimensions, and any step where the getting-started guide did not match the app.

### 7.6 End-to-end (Playwright + Electron)

- Launch with `_electron.launch({ args: ['dist/main/index.cjs'], env: { M2C_E2E: '1' } })`, or
  the packaged exe via `M2C_APP_BINARY`. In `M2C_E2E` mode main adds
  `--use-angle=swiftshader --enable-unsafe-swiftshader`, because CI runners have no GPU.
- Assert that the renderer is sandboxed (`app.getAppMetrics()`), and that `require`, `process`
  and `module` are undefined in the page.
- Native dialogs are stubbed in the main process with `electronApp.evaluate(({ dialog }) => …)`.
- Selectors use `data-testid` and ARIA roles only, never visible text or CSS classes. Test ids:
  `stage-<id>`, `tool-<tool-id>`, `panel-ok`, `panel-cancel`, `panel-apply`, `tree-node-<id>`,
  `status-kernel`, `status-selection`, `status-faces`, `status-tolerance`, `empty-import`,
  `menu-<menu>`, `menu-item-<command-id>`, `viewport-canvas`.
- Viewport input goes through test hooks that `src/renderer/testing/testHooks.ts` installs only in
  test mode (`window.__m2cTest`, typed in `src/shared/testHooks.ts`): `revision()`, `scene()`,
  `selectFaces(indices)`, `waitForIdle()`; the domains add `selectRegion(id)` and
  `pickEdgeNear(point)` through the same interface. They use only public APIs (stores, `viewport/api.ts`). Tests never click
  fractional canvas coordinates.
- Specs: `smoke.spec.ts` (launch, security, import, display, undo), `workflow.spec.ts` (import →
  align → segment → fit → sketch → extrude → fillet → deviation → STEP; extended as tools land),
  `project.spec.ts`, and `viewport-perf.spec.ts` (local only: CI has no GPU; results are recorded
  in the pull request). Screenshots and a JSON report go to `test-results/`.

---

## 8. Decisions

The architecture review of 2026-09-26 raised 25 points. Each was accepted, accepted in part or
rejected as recorded here; the sections named in each entry contain the result. The UX review is
answered in [DESIGN.md section 11](DESIGN.md#11-decisions).

1. **Native calls hold the GIL.** Accepted. The host resolves cancels at once and offers a
   restart after `CANCEL_GRACE_MS`; long native calls announce the indeterminate `kernel.native`
   stage; `debug.nativeBlock` tests this path; the segmentation LOD is cached per scan key;
   decimation runs in a killable child process (3.4, 3.5.4, 4.12).
2. **Files that several work packages must edit.** Accepted. Changelog fragments in `changes/`
   (6.2); one pure band module `lib/deviationBands.ts` used by legend, viewport and statistics
   (5.1); `D` belongs to the deviation tool, the display-mode menu only lists the mode; face masks
   belong to the selection package; generated files are split per module and `index.ts` only
   combines per-group tables (3.5.7).
3. **Shared state and extension points.** Accepted. `objectSelectionStore`, `FeatureView.Properties`
   and a validated `tools` namespace in settings exist in the skeleton (5.2, 5.7).
4. **Incomplete viewport contract.** Accepted. `viewport/api.ts` has `setPreviewItems`,
   `highlight`, `screenToRay`, `worldToScreen`, `setOpacity`, `setOrbitLocked`, activation data
   for tools, and all four handle types; the skeleton implements every member (5.8).
5. **IPC and main-process gaps.** Accepted. `recovery:list`, `recovery:resolve`, `recent:list` and `openExample`
   exist; the renderer-callable method list is generated from `@command(caller=...)`; the kernel
   checks the `origin` header field (3.1, 3.5.3).
6. **No home for codes.** Accepted. One `codes/<domain>.py` per domain with `ErrorCode`,
   `IssueCode` and `ProgressStage`, generated to `codes-<domain>.ts` (3.5.5).
7. **Fillet edge references.** Accepted. Face tags on every body, carried through operation
   history; `EdgeRef` is a face-tag pair plus a tie-break point (4.5, 4.6).
8. **Oversized work packages.** Accepted in part. The skeleton covers the former T0 completely.
   Alignment and freeform are separated from fitting; loft moves to the freeform package. Solid
   features stay one package because extrude, revolve, primitives, split, combine and fillet share
   the face-tag and boolean code; splitting them would create more seams than it removes. The
   package plan itself is a local planning file (item 25).
9. **One worker blocks everything.** Accepted. `exclusive` methods and `kernel.busy`; tools and
   undo are disabled while an exclusive job runs (3.5.4).
10. **Cache keys do not say what a feature reads.** Accepted. `ReadSet` on every feature type;
    result keys include only what is declared (4.5, 4.6).
11. **Non-deterministic rebuilds.** Accepted. RNGs seeded from result keys, display keys derived
    from result keys, save-load-rebuild identity test (4.2, 4.6).
12. **Stale selections after mesh operations.** Accepted. Selection state and history entries carry
    the scan key; stale entries are cleared or skipped (4.4, 4.9).
13. **Hole-fill triangles pulled into fits.** Accepted. Exact index maps where possible, nearest
    centroid only for decimation, `scan.synthetic` excluded from fitting, segmentation and
    statistics (4.4).
14. **Protocol details.** Accepted. Lanes derived from method names (the separate `scene.section`
    method is removed; the viewport computes the section view itself), `documentChanged` before the
    response, NaN encoded as `null` (3.5.2–3.5.4, 5.8).
15. **Wire types and codegen rules.** Accepted. Required discriminators, dictionary keys kept,
    input and stored variants, exported ranges (3.5.7).
16. **Memory-mapped blobs on Windows.** Accepted. No memory mapping, retrying replace and delete,
    main deletes the session only after the kernel exited (3.4, 4.3).
17. **Session growth and undo into pruned revisions.** Accepted. `MAX_MESH_REVISIONS`,
    `document.revisionGone`, persisted `head.json` (1.4, 4.3, 4.9).
18. **Solid preview budget.** Accepted. Geometry preview first, `inspection.previewDeviation` in
    its own lane, keyed by the preview's result key (4.7).
19. **Large display data over `ipcRenderer.invoke`.** Rejected for v0.1, with the frame cap
    accepted. A 2 M-face scan payload is about 50 MB, well inside the 256 MiB cap, and structured
    cloning of `ArrayBuffer`s is a copy, not a serialisation. Streaming through `m2c://scene/<key>`
    would add a second transport with its own lifetime rules. The viewport performance test
    measures the path; if it misses the 3 s budget, the switch is contained in `KernelClient` and
    main.
20. **Renderer techniques for 2 M faces.** Accepted: `compileAsync`, chunked uploads, native
    normal formats, face-id render target for visible-only picking (5.8).
21. **No GPU in CI.** Accepted. SwiftShader switches in `M2C_E2E` mode; the performance spec is
    local only; the frozen-kernel smoke runs weekly and on release (7.1, 7.6).
22. **Optimistic import limits.** Accepted. `MAX_IMPORT_FACES` = 10 M, float32 STL reader, int32
    weld, chunked OBJ parsing (1.4, 4.12).
23. **Big-bang integration.** Accepted. Contract changes land first in their own pull requests,
    each package merges as soon as it is green, the viewport package early, and the workflow spec
    grows with each merge (6.5, 7.6).
24. **Packaging risks.** Accepted. Frozen-kernel tests are the packaging gate and size limits are
    targets until measured; the release workflow scans the installer with Microsoft Defender;
    `freeze_support()` and fd protection in child processes (3.4, 6.2). The embeddable-Python
    alternative is kept as the fallback if PyInstaller false positives persist.
25. **GitHub hygiene.** Accepted. The implementation plan lives in the untracked `.work/plan.md`;
    docstrings are enforced only in `api.py` and command modules, one-line docstrings allowed
    (6.3).
