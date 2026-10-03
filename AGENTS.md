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
   `git worktree add ../m2c-<issue> -b feat/<issue>-<topic> dev`, then `npm ci` there;
   `M2C_PYTHON` may point to the main checkout's `.venv\Scripts\python.exe`.
3. Run your own app next to the others:
   `M2C_INSTANCE=<issue> M2C_WINDOW=offscreen M2C_AUTOMATION=1 npm run dev`; automation
   clients (the MCP server, scripts) take the same `M2C_INSTANCE`.
4. Pull request to `dev` (the integration branch; `main` takes releases) with `Closes #n`.
   CI starts by itself; merged when it is green.
5. Stay on your issue. Chats do not start other chats (no task suggestions) and do not open
   issues for things found on the way. Report such a finding to the coordinator chat in
   one message: what, where and how to reproduce it. The coordinator checks whether
   someone already owns it, then opens the issue or hands it on. Two chats once found the
   same bug at the same time, opened two issues, and a third chat redid a fix that was
   already in a pull request.

## Done means

1. `npm run check` is green.
2. The tool was used in the running app like a user would, every step checked by numbers
   and looked at in screenshots. `M2C_INSTANCE=<issue> npm run usertest` does that on a
   synthetic part (`tools/usertest/`, one test per tool; add yours); also try a real scan.
   What looks wrong is fixed before anyone else sees it.
3. Every built body was compared with the scan the way the user does:
   - **The heatmap, finished.** Prüfen → Abweichung, and wait until it has finished
     computing. A screenshot while it says "Wird berechnet" does not count.
   - **The largest deviation and where it is** (corner, edge, wall, top), not only RMS or
     the share within tolerance. Averages hid 1–2 mm bulges at the remote's corners once.
     Anything over the tolerance is fixed or explained in the pull request.
   - **Close-ups of every corner and edge.** Take them three ways: bodies only with
     colours off (Space, D), with the scan shown, and with the heatmap. Look for bulges,
     steps, gaps, floating parts and construction drawn over the body.
4. Committed with `Closes #n`, pushed. No co-author or "generated with" lines.

## Talking with the user

- Answer in German, short and plain. No long lists, no recaps of what was already said.
- When the user wants to talk ("wir müssen reden") or asks a question: start nothing new
  and answer first, until the question is settled. Work already running (CI, the app,
  other chats) keeps running; never cancel it for this.
- Decide what you can decide yourself from the job, the research and the code; ask only
  what only the user can answer.
- Show results working in the app before reporting them; the user should not be the one
  who finds the flaws.

## Never

- Touch the user's own app data or recovery sessions; automation runs in its own profile
  (`M2C_WINDOW=demo|offscreen M2C_AUTOMATION=1 npm run dev`).
- Take over the user's mouse and keyboard; drive the app through automation instead.
