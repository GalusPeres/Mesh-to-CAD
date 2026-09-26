### Added

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
