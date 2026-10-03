### Added

- Formen erkennen: every outline is a chain of lines and arcs. Buttons cut by the part's
  outline are found as cut circles (with the radius of their whole twins), and free contours
  are fitted as lines and arcs; both are built like any other shape.

### Fixed

- Skizze: the auto fit of smoothed scans (the remote control's outline) no longer splits long
  sides into many pieces, and inferred directions and equal radii are only kept where every
  entity still fits the scan.
- Formen erkennen: buttons at the edge of a warped face are no longer lost, and rows of buttons
  line up with the part's axes instead of the face's principal axis.
