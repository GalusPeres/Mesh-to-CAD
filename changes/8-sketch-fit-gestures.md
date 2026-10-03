### Added

- Sketch: a click inside a closed section outline fits its shape (circle, slot, rounded
  rectangle, ring arm) with design values; equal buttons get equal sizes, ring arms share a
  centre when the scan supports it. Outlines that are no such shape become lines and arcs.
- Sketch: Ctrl at a corner rounds it with the radius measured on the scan; a Ctrl stroke over two
  entities forms the corner between them.
- Sketch: painted lines within 0.5° of an axis become horizontal or vertical.
- Sketch: every shape and free profile shows its largest deviation from the section in the view;
  the status bar says what the pointer does.
- Sketch: the plane step can start with an empty sketch (_Alle Konturen einpassen_ off); a plane
  selected before the tool opens becomes the sketch plane, and on a plane fitted to the scan the
  cut starts 0.5 mm above the face.

### Changed

- The automatic sketch fit recognises the same shapes and keeps constraints within one outline,
  so a section with twenty buttons fits in seconds instead of not finishing.
- The entity list shows one row per shape and free profile; constraints and snapped values are
  listed for the selection.

### Fixed

- The plane step's cut starts through the middle of the scan again.
- In sketch mode the camera frames the section, and the entities are drawn above the section
  points (their pass/fail colour was hidden).
