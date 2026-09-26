# Automation and MCP server

Mesh-to-CAD can be driven by other programs on the same computer, for example an AI
assistant through the [Model Context Protocol](https://modelcontextprotocol.io) (MCP).
Every change goes through the same paths as the user interface: it appears live in the
window and can be undone there.

## Enable it

The interface is off by default. Enable it in **Datei → Einstellungen → Automatisierung →
Steuerung durch KI-Assistenten erlauben (MCP)**, or start the app with the environment
variable `M2C_AUTOMATION=1`.

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
| `screenshot`                   | Screenshot of the window                                                                         |

Coordinates are part coordinates in millimetres, after the alignment.

## Protocol

`POST http://127.0.0.1:<port>/rpc` with `Authorization: Bearer <token>` and a JSON body
`{"method": ..., "params": ...}`. Methods: `ping`, `kernel.call` (`method`, `params`,
optional `lane`), `ui` (`action`: `state`, `listCommands`, `runCommand`, `selectFaces`) and
`screenshot`. Typed arrays in kernel parameters are written as
`{"$typed": "uint32", "values": [...]}`; long typed arrays in results are summarised.
