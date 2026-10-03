### Added

- `npm run usertest -- remote` rebuilds the reference remote scan end to end and reports the
  deviation per region (walls, corners, top edge, top face, each button, underside), with
  screenshots and the change since the previous run.
- Automation: `automation.scanVertices`, the view and heatmap state in `state`, and
  Verrundung's picked edges and scan radius in `toolInfo`.
