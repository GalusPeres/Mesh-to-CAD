### Added

- Loft: "Anfang bis" and "Ende bis" a plane. The walls continue straight up to the plane
  and end in it, past the rounding of the scan, so a fillet runs along the end edge.
- Fillets narrow where the faces bend tighter than the radius, instead of failing (on a
  remote control's 0.3 mm corners); the history says down to which radius.

### Fixed

- The fillet tool picks edges in the shaded view too, not only with edges shown.
- A fillet that Open CASCADE builds with an open gap is reported as failed instead of kept.
