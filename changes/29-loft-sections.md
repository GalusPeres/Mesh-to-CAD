### Fixed

- Loft corners are no longer dented at every section: the corners land on the same section
  points from section to section.
- Lofts no longer cut the corners of the outline: sections take a point every 0.5 mm instead
  of 96 around (on a remote control 0.13 mm instead of 1.1 mm off at the corners), and the
  loft builds faster.
- Volume and area of lofted bodies are exact; they were off by up to 4 %.
