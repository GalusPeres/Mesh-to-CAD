"""Codes of automatic freeform surfacing (B-spline patch networks from organic scans)."""

from enum import StrEnum


class ErrorCode(StrEnum):
    TOO_FEW_FACES = "surfacing.tooFewFaces"
    """The scan or the selection has too few triangles for a control cage."""
    CAGE_FAILED = "surfacing.cageFailed"
    """Decimation gave no manifold control cage (the scan needs repair)."""
    SHAPE_INVALID = "surfacing.shapeInvalid"
    """The assembled patches do not form a valid shell."""
    NOT_AUTO_SURFACE = "surfacing.notAutoSurface"
    """`surfacing.preview` or `surfacing.featureFaces` was called for another feature type."""
    NET_FAILED = "surfacing.netFailed"
    """Remeshing gave no usable quad net (the scan needs repair, or another density)."""
    NET_INVALID = "surfacing.netInvalid"
    """The quads of a freeform net do not form an oriented 2-manifold."""
    NOT_FREEFORM_NET = "surfacing.notFreeformNet"
    """`net.featureNet` was called for another feature type."""


class IssueCode(StrEnum):
    OPEN_SURFACE = "surfacing.openSurface"
    """The scan is open, so the result is a surface, not a solid body."""
    OPEN_NET = "surfacing.openNet"
    """The freeform net has open borders, so the result is a surface, not a solid."""
    PARTS_IGNORED = "surfacing.partsIgnored"
    """Only the largest connected part was surfaced; `count` parts were left out."""


class ProgressStage(StrEnum):
    NET = "surfacing.net"
    CAGE = "surfacing.cage"
    FITTING = "surfacing.fitting"
    PATCHES = "surfacing.patches"
    SHAPE = "surfacing.shape"
    DEVIATION = "surfacing.deviation"
