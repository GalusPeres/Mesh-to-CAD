### Added

- Freeform net: _push past reference faces_ moves the net's open border 0.5 mm past the shown
  planes and bodies it ends at, then fits the rest of the net to the scan again (QuickSurface's
  Offset by reference surfaces).
- _Zuschneiden_: bodies, open nets and planes cut each other into pieces; the pieces inside the
  scan are kept by default, a click on a piece removes it or brings it back, and the kept pieces
  become one body.

### Fixed

- An auto net on a selection ends on the selection's edge instead of up to two quads short of
  it, with notches.
- Construction a later feature uses is hidden in the view (the tree listed it as hidden, but it
  stayed drawn); an open net that is trimmed no longer warns.
- A new project no longer keeps the last project's choice in the tree or its hidden objects.
