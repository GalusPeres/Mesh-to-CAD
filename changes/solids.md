### Added

- Extrusion of sketch profiles: distance in one or both directions, symmetric, or up to a
  plane; the distance is pre-filled from the scan and can be dragged at an arrow handle.
- Drehung (revolve) about a sketch line, a fitted or reference axis, or X/Y/Z, with any angle.
- Grundkörper: solid cylinders, cones, spheres and tori from fits, with the length taken from
  the scan triangles on the fitted surface plus a margin, or entered manually.
- Körper teilen: split a body with an origin plane, a plane feature or a freeform patch and keep
  one side.
- Kombinieren: unite, subtract or intersect bodies, optionally keeping the tool bodies.
- Verrundung and Fase on picked edges, with _Radius aus Scan_ proposing the snapped radius.
- New bodies can be united with, subtracted from or intersected with an existing body in every
  solid tool.
- Every body face carries a name from the feature that created it, so fillets and chamfers keep
  their edges when earlier steps change (for example a new extrusion height).
- Near-coincident planar faces are aligned before body operations, which keeps results valid and
  free of split faces.
