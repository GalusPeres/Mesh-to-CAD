# Automation and MCP server

Mesh-to-CAD can be driven by other programs on the same computer, for example an AI
assistant through the [Model Context Protocol](https://modelcontextprotocol.io) (MCP).
Every change goes through the same paths as the user interface: it appears live in the
window and can be undone there.

## Enable it

The interface is off by default. Enable it in **Datei → Einstellungen → Automatisierung →
Steuerung durch KI-Assistenten erlauben (MCP)**, or start the app with the environment
variable `M2C_AUTOMATION=1`.

For automated checks while someone keeps using the PC, a development build can run off
screen: `M2C_AUTOMATION=1 M2C_WINDOW=offscreen npm run dev` opens the window outside the
visible screen, without focus or taskbar button, and with a profile of its own
(`%APPDATA%\Mesh-to-CAD-automation`), so it never touches the user's settings, recent files
or unsaved work. Screenshots still show the window as usual. `M2C_WINDOW=demo` shows the
same profile in a normal window, without taking the focus.

Several apps can run side by side (one per agent, each from its own git worktree):
`M2C_INSTANCE=<name>` gives the automation window the profile
`Mesh-to-CAD-automation-<name>` and the dev server a free port. Start the MCP server or any
other automation client with the same `M2C_INSTANCE`, and it talks to that app only.

Clients in the repository share `tools/automation/client.mjs` (finding the app, requests).
The user tests in `tools/usertest/` drive such an app like a user on a synthetic part and
save screenshots to `test-results/usertest/<name>/`: `M2C_INSTANCE=<name> npm run usertest`
(or `-- net` for one test). They refuse to run without `M2C_INSTANCE`, because each run
starts a new project in that app.

The app then listens on `127.0.0.1` with a random port and a random token and writes both
to `%APPDATA%\Mesh-to-CAD\automation.json`. The file is removed when the app closes or the
setting is turned off. Requests without the token, and requests from web pages (with an
`Origin` header), are rejected.

## Connect an MCP client

The server is `tools/mcp/server.mjs` (Node.js 24, stdio transport). This repository contains
a `.mcp.json`, so Claude Code picks it up when started in the repository folder. For other
clients:

```json
{
  "mcpServers": {
    "mesh-to-cad": {
      "command": "node",
      "args": ["C:/path/to/Mesh-to-CAD/tools/mcp/server.mjs"]
    }
  }
}
```

Use forward slashes in the paths of such a configuration; some clients pass the arguments
through a shell that removes backslashes.

The server looks for `automation.json` in `%APPDATA%Mesh-to-CAD` and in the per-package
AppData copies of MSIX-packaged apps (the Claude desktop app is one), and uses the newest file
whose process is still running. `M2C_AUTOMATION_INFO` points the server to a different `automation.json` (the end-to-end
test uses this).

## Tools

| Tool                           | Purpose                                                                                          |
| ------------------------------ | ------------------------------------------------------------------------------------------------ |
| `app_status`                   | Scan, alignment, feature history with status and statistics, bodies, open tool, selection        |
| `import_scan`                  | Load an STL, OBJ or PLY file (reduced to 1,000,000 triangles when larger than the limit)         |
| `align_auto`                   | Automatic alignment, with flip and quarter-turn adjustments                                      |
| `scan_bounds`                  | Bounding box of the aligned scan                                                                 |
| `select_region`                | Select the triangles in a box, optionally only those facing a direction, and show them           |
| `fit_shape`                    | Fit a plane, cylinder, cone, sphere or torus to the triangles in a box and add it to the history |
| `auto_surface`                 | Turn the scan into a solid of B-spline surfaces                                                  |
| `export_step`                  | Write bodies to a STEP file                                                                      |
| `apply_ops`                    | Apply document operations as one undoable step                                                   |
| `kernel_call`                  | Call any kernel method (see `kernel/m2c_kernel/commands`)                                        |
| `list_commands`, `run_command` | Run app commands: views, undo, tools                                                             |
| `recognize_shapes`             | Flat faces and the raised shapes, pockets and holes on them, outlines of lines and arcs          |
| `build_shapes`                 | Build recognised shapes as plane, sketches and extrusions, joined to or cut from a body          |
| `click`                        | Click a control by its `data-testid` or a button by its label or aria-label                      |
| `press_key`                    | Press a key: Escape, Enter, tool shortcuts                                                       |
| `screenshot`                   | Screenshot of the window                                                                         |

Coordinates are part coordinates in millimetres, after the alignment.

The `toolInfo` UI action returns what the open tool lets the user grab, with screen positions.
In sketch mode: `outlines` (a point inside each closed section outline, where a click fits its
shape), `joints` (points where two entities meet, with those entities; a Ctrl click rounds them),
`entities`, `shapes` with their sizes, and `state.job` while a gesture is being fitted.

## Protocol

`POST http://127.0.0.1:<port>/rpc` with `Authorization: Bearer <token>` and a JSON body
`{"method": ..., "params": ...}`. Methods: `ping`, `kernel.call` (`method`, `params`,
optional `lane`), `ui` (`action`: `state`, `listCommands`, `runCommand`, `selectFaces`, `click`,
`key`) and
`screenshot`. Typed arrays in kernel parameters are written as
`{"$typed": "uint32", "values": [...]}`; long typed arrays in results are summarised.
