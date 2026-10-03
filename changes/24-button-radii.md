### Added

- Formen erkennen measures the rounding of every shape's top edge from the scan and rounds each
  group of equal shapes with one fillet; the radius shows in the list (R 0,75) and a click
  switches it off.
- Inclined and domed tops (the arms of a direction pad) are built up to a plane or patch fitted
  to the scan instead of a flat top.
- `fillet.scanRadius` measures the radius of body edges from the scan, also on long edges that
  run around a whole outline; _Radius aus Scan_ in the fillet tool uses it.

### Fixed

- Construction that a later feature uses (planes, sketches, patches) is hidden in the 3D view,
  and the eye in the project tree hides bodies and features there.
