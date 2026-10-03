"""Parameters of the alignment methods, stored in `Alignment.params`.

`auto` and `none` have no parameters (`None`). `faces` names up to three inputs:
fit or reference features, regions, or a stored face set (the selection at the time
the alignment was made). Fitted inputs are refitted from their triangles in scan
coordinates, so the alignment never depends on its own result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from m2c_kernel.protocol.wire import BlobRef

type InputRole = Literal["primary", "secondary", "tertiary"]


@dataclass(frozen=True, kw_only=True)
class FeatureInput:
    """A fit feature (plane, cylinder, cone, sphere) or a reference plane or axis."""

    type: Literal["feature"] = "feature"
    feature: str


@dataclass(frozen=True, kw_only=True)
class RegionInput:
    """A region whose type is plane, cylinder, cone or sphere."""

    type: Literal["region"] = "region"
    region: str


@dataclass(frozen=True, kw_only=True)
class FacesInput:
    """Scan triangles stored with the alignment; the primitive type is chosen by fitting."""

    type: Literal["faces"] = "faces"
    faces: BlobRef


type AlignmentInput = FeatureInput | RegionInput | FacesInput


@dataclass(frozen=True, kw_only=True)
class FacesAlignmentParams:
    """3-2-1 inputs.

    The primary input gives Z (a plane normal into the material, or an axis). The
    secondary gives the in-plane direction (a plane: Y along its normal; an axis: X)
    or, when it is parallel to Z, a position: an end face on a shaft, a hole axis in
    a plate. The optional tertiary completes the origin; without it, coordinates that
    no input fixes go to the bounding-box minimum of the scan.
    """

    primary: AlignmentInput
    secondary: AlignmentInput
    tertiary: AlignmentInput | None = None
