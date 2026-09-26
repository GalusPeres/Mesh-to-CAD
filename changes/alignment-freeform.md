### Added

- _Automatisch ausrichten_ puts the largest plane of the scan on XY (material above it), the
  largest plane perpendicular to it on XZ and the origin at the corner of the scan, snapped onto
  the planes that lie there. Without two planes the principal axes of the surface are used, with
  a sign rule that gives the same pose for every scan pose. The panel draws the new coordinate
  system over the scan and shows the remaining tilt ("Größte Ebene 0,00° zu XY").
- _An Flächen ausrichten_ builds a 3-2-1 frame from fitted planes and axes, reference geometry,
  regions or the working selection, picked in the project tree or the viewport: three planes, an
  axis and an end face for shafts, or a plane and two hole axes for flanges. Each input shows the
  fitted type and RMS; parallel inputs and frames without an origin are reported.
- Both alignments can be turned over, reversed in X and rotated in 90° steps, are undoable and
  open again from the _Ausrichtung_ entry of the history. _Ausrichtung zurücksetzen_ returns to
  scan coordinates. A new alignment re-evaluates only the features that read the scan.
- _Freiformfläche_ fits a B-spline patch (P-spline height field, exact conversion to an Open
  CASCADE surface) to the selection or a region, with automatic or manual span count, smoothing
  and a margin beyond the triangles; the result block shows noise, RMS, maximum and the share
  within tolerance, and the triangles are coloured pass/fail. Regions curved by more than 150°
  are rejected with a message.
- _Loft_ builds a body through planar sections of the scan along X, Y, Z, a fitted axis or a plane
  normal, with start and end handles, 3 to 64 sections and the usual body operations. Its faces
  are tagged, so fillets and booleans can refer to them.
