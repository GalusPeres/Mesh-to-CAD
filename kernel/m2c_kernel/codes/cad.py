"""Codes of the solid modelling operations (Open CASCADE)."""

from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_RESULT = "cad.invalidResult"
    OCCT_UNAVAILABLE = "cad.occtUnavailable"
    PROFILE_OPEN = "cad.profileOpen"
    """The sketch has no closed profile to extrude or revolve."""
    AXIS_CROSSES_PROFILE = "cad.axisCrossesProfile"
    AXIS_NOT_IN_PLANE = "cad.axisNotInPlane"
    PLANE_PARALLEL = "cad.planeParallel"
    """The up-to plane of an extrusion is parallel to the extrusion direction."""
    PLANE_BEHIND = "cad.planeBehind"
    EMPTY_RESULT = "cad.emptyResult"
    BOOLEAN_FAILED = "cad.booleanFailed"
    FILLET_FAILED = "cad.filletFailed"
    EDGE_NOT_FOUND = "cad.edgeNotFound"
    TARGET_REQUIRED = "cad.targetRequired"
    UNSUPPORTED_TOOL = "cad.unsupportedTool"
    """A trim tool or primitive-body fit of a kind the operation cannot use."""
    NO_EXTENT = "cad.noExtent"
    """The fit has no triangles to derive the body extent from."""
    TAPER_UNSUPPORTED = "cad.taperUnsupported"


class IssueCode(StrEnum):
    HIGH_TOLERANCE = "cad.highTolerance"
    SPLIT_FACES_KEPT = "cad.splitFacesKept"


class ProgressStage(StrEnum):
    TESSELLATING = "cad.tessellating"
    MODELLING = "cad.modelling"
    BOOLEAN = "cad.boolean"
    FILLET = "cad.fillet"
