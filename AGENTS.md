# Working on Mesh-to-CAD (for agents and contributors)

## The job

A free, open-source program that does what QuickSurface does for reverse engineering, and
makes it easier: scan in, prepare and align; straight geometry first (planes, a sketch on
a section where a click fits circle, slot or arc, extrude or revolve); roundings and organic
regions added piece by piece with quad nets laid on the scan; fillets and chamfers with the
radius from the scan; trim and boolean into one body; the deviation visible live at every
step; STEP out. Every tool also works over the automation interface (MCP).

## Before building

- Read [docs/research/quicksurface.md](docs/research/quicksurface.md): how QuickSurface does
  the tool, with the tutorial and timestamp. Rebuild that behaviour, then improve on it.
  Do not invent a gesture the reference already solves.
- Work from a GitHub issue (milestones group them). No issue for it yet: open one first.
  Bugs get the `bug` label, larger work `enhancement`. Keep the list short and real.

## Building

- Rules of the code base: [CONTRIBUTING.md](CONTRIBUTING.md). In short: English code,
  comments, commits and docs; German only in `locales/`; small files with one job (aim for
  250 lines, never over 400); delete code a new approach replaces.
- Panels stay compact: controls with tooltips, numbers instead of sentences, what the
  pointer does goes to the status bar (`*.status.tsx`). No paragraphs of help text.
- Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), design:
  [docs/DESIGN.md](docs/DESIGN.md), automation: [docs/AUTOMATION.md](docs/AUTOMATION.md).

## Where things live

| Area                     | Folder (one unit each)                                                                         |
| ------------------------ | ---------------------------------------------------------------------------------------------- |
| Tools in the app         | `src/renderer/tools/<tool>/` with its `locales/`; found by the app, no central list            |
| Features in the history  | `src/renderer/features/<type>/` (view) and `kernel/m2c_kernel/features/types/<type>.py`        |
| Kernel commands          | `kernel/m2c_kernel/commands/<group>.py`                                                        |
| Algorithms               | `kernel/m2c_kernel/<recognition, surfacing, sketch, fitting, mesh, alignment, inspection, …>/` |
| Status bar, view overlay | `*.status.tsx`, `*.overlay.tsx` next to the tool that shows them                               |

**Shared contracts** change only in a small pull request of their own (CONTRIBUTING.md):
`src/renderer/viewport/api.ts`, `src/renderer/tools/framework/`, `src/shared/`,
`kernel/m2c_kernel/protocol/`, `kernel/m2c_kernel/document/`. `src/shared/protocol/generated/`
is written by `npm run codegen` only.

## Working in parallel

1. Take an issue: assign it to yourself and add the label `in progress`.
2. Work in a worktree on a branch of your own:
   `git worktree add ../m2c-<issue> -b feat/<issue>-<topic> main`, then `npm ci` there;
   `M2C_PYTHON` may point to the main checkout's `.venv\Scripts\python.exe`.
3. Run your own app next to the others:
   `M2C_INSTANCE=<issue> M2C_WINDOW=offscreen M2C_AUTOMATION=1 npm run dev`; automation
   clients (the MCP server, scripts) take the same `M2C_INSTANCE`.
4. Pull request to `main` with `Closes #n`; merged when CI is green.

## Done means

1. `npm run check` is green.
2. The tool was used in the running app like a user would (automation RPC, a real scan
   such as the remote control), every step checked by numbers and looked at in
   screenshots. What looks wrong is fixed before anyone else sees it.
3. Committed with `Closes #n`, pushed. No co-author or "generated with" lines.

## Never

- Touch the user's own app data or recovery sessions; automation runs in its own profile
  (`M2C_WINDOW=demo|offscreen M2C_AUTOMATION=1 npm run dev`).
- Take over the user's mouse and keyboard; drive the app through automation instead.
