"""Parameters of the alignment methods, stored in `Alignment.params`.

`auto` has no parameters (`None`). `faces` references fit features or regions; the
kernel refits their triangles in scan coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class AlignmentInputRef:
    """Exactly one of `feature` (a fit feature) or `region` is set."""

    feature: str | None = None
    region: str | None = None


@dataclass(frozen=True, kw_only=True)
class FacesAlignmentParams:
    """3-2-1 inputs.

    The primary input gives Z, the secondary the XZ plane (a plane) or X (an axis), the
    optional tertiary fixes the remaining origin coordinate.
    """

    primary: AlignmentInputRef
    secondary: AlignmentInputRef
    tertiary: AlignmentInputRef | None = None
