"""Limits shared by the kernel and the application.

This module is the single source of these values: codegen writes them to
`src/shared/protocol/generated/limits.ts`, and no other file may hard-code them.
"""

MAX_WORKING_FACES = 2_000_000
"""Largest scan kept at full resolution (renderer memory for the non-indexed scan)."""

MAX_IMPORT_FACES = 10_000_000
"""Largest file accepted by the import; larger scans must be reduced elsewhere first."""

MAX_IMPORT_BYTES = 1 << 30
"""Largest mesh file accepted by the import (1 GiB)."""

MIN_FIT_FACES = 200
"""Fewer triangles give unstable primitive fits."""

MAX_REGIONS = 65_534
"""Region labels are uint16 per face; 0 means unassigned."""

MAX_FEATURES = 500
"""Rebuild time and tree usability."""

MAX_REVISIONS = 200
"""Undo depth."""

MAX_MESH_REVISIONS = 10
"""Revisions that store their own copy of the scan (topology-changing operations)."""

MAX_FRAME_BYTES = 256 << 20
"""Largest protocol frame in either direction (256 MiB)."""

DEFAULT_TOLERANCE_MM = 0.10
"""Project tolerance used until the import proposes one from the scan noise."""

CANCEL_GRACE_MS = 3000
"""Time a cancelled request may keep running before the application offers a restart."""
