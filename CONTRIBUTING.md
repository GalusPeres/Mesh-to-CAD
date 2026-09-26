# Contributing to Mesh-to-CAD

Thank you for helping. This guide covers the setup, the checks every change must pass and the
conventions of the code base. The architecture is described in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), the user interface in [docs/DESIGN.md](docs/DESIGN.md).

## Setup

Prerequisites: Windows 10 or 11 (x64), Node.js 24, Python 3.12 (64-bit), Git. All Python
dependencies install from prebuilt wheels; no compiler is needed.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r kernel\requirements-dev.txt
npm ci
npm run dev
```

`npm run dev` starts the Vite dev server, builds the main and preload scripts in watch mode and
launches Electron. The geometry process runs from `.venv`; set `M2C_PYTHON` to use another
interpreter.

## Checks

| Command                 | What it does                                                       |
| ----------------------- | ------------------------------------------------------------------ |
| `npm run check`         | Everything below except the build and the end-to-end tests         |
| `npm run lint`          | ESLint and Prettier                                                |
| `npm run typecheck`     | TypeScript for main, preload, renderer and tests                   |
| `npm test`              | Vitest unit tests                                                  |
| `npm run kernel:lint`   | Ruff (lint and format) and mypy for the Python kernel              |
| `npm run kernel:test`   | Kernel tests without the slow ones; add paths after `--`           |
| `npm run codegen:check` | Fails if the generated protocol types are out of date              |
| `npm run build`         | Production build into `dist/`                                      |
| `npx playwright test`   | End-to-end tests against the built app (run `npm run build` first) |

`npm run format` formats TypeScript, CSS, Markdown and Python. After changing a wire type in the
kernel, run `npm run codegen` and commit the generated files.

## Project structure

| Path                 | Contents                                                             |
| -------------------- | -------------------------------------------------------------------- |
| `src/main/`          | Electron main process: window, security, files, kernel process       |
| `src/preload/`       | The `window.m2c` bridge                                              |
| `src/renderer/`      | React user interface and three.js viewport                           |
| `src/shared/`        | Types shared by main and renderer, protocol framing, generated types |
| `kernel/m2c_kernel/` | Python geometry process                                              |
| `kernel/tests/`      | Kernel tests; `synthetic/` generates test scans with noise           |
| `tests/e2e/`         | Playwright tests of the whole application                            |
| `docs/`              | Architecture and design specifications                               |

## Adding things

Everything is discovered from its own files; there is no central list to edit.

- **A tool:** create `src/renderer/tools/<tool-id>/index.ts` exporting `tool: ToolDefinition`,
  plus `locales/de.json` and `locales/en.json` with `label` and `howTo`. See
  `tools/import-mesh/` for a working example.
- **A command or shortcut:** export `commands` from a file named `*.commands.ts`.
- **A protocol method:** add a function decorated with `@command` to
  `kernel/m2c_kernel/commands/<group>.py`, then run `npm run codegen`.
- **A feature type:** add a module to `kernel/m2c_kernel/features/types/` with
  `@feature_type(...)`, declare what it reads with `ReadSet`, run `npm run codegen`, and add
  `src/renderer/features/<type>/view.ts` with its locales.
- **Error, warning or progress codes:** add them to `kernel/m2c_kernel/codes/<domain>.py` and
  translate them in `src/renderer/i18n/locales/{de,en}/domains/<domain>.json`.

## Rules

- **Text:** every user-visible string lives in the locale files, in German and English. The kernel
  and the main process return codes, never text. Follow the tone and glossary of
  [DESIGN.md section 8](docs/DESIGN.md#8-writing).
- **Design:** use tokens and the components in `src/renderer/ui/`. Check UI changes against the
  [review checklist](docs/DESIGN.md#10-review-checklist) and attach screenshots of both themes.
- **Tests:** every change comes with tests. Kernel algorithms are tested against synthetic scans
  with known geometry (`kernel/tests/synthetic/`); no binary fixtures in git.
- **Contracts:** changes to shared contracts (protocol, document model, `viewport/api.ts`,
  stores, registries, shared kernel modules) go into their own small pull request with an
  updated `docs/ARCHITECTURE.md` and contract test.
- **Code:** English identifiers and comments; comments explain why, not what; no commented-out
  code; no TODO without an issue number. TypeScript without `any`; Python fully typed.

## Commits and pull requests

- Branch from `main` (`feat/<topic>`, `fix/<topic>`, `docs/<topic>`, `chore/<topic>`).
- Write [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`,
  `test:`, `refactor:`, `build:`, `ci:`, `chore:`).
- Add a changelog fragment `changes/<topic>.md` instead of editing `CHANGELOG.md` (see
  [changes/README.md](changes/README.md)).
- Keep `npm run check` green. Pull requests are squash-merged after review and a passing CI run.

## Reporting problems

Use the issue templates for bugs and feature requests. Report security problems privately as
described in [SECURITY.md](SECURITY.md).
