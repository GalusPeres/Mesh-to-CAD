"""Codes of freeform patches and lofts."""

from enum import StrEnum


class ErrorCode(StrEnum):
    TOO_CURVED = "freeform.tooCurved"
    TOO_FEW_FACES = "freeform.tooFewFaces"
    FIT_FAILED = "freeform.fitFailed"
    INVALID_SURFACE = "freeform.invalidSurface"
    INVALID_RANGE = "freeform.invalidRange"
    NOT_AN_AXIS = "freeform.notAnAxis"
    NO_SECTION = "freeform.noSection"
    SECTION_JUMP = "freeform.sectionJump"
    PLANE_NOT_REACHED = "freeform.planeNotReached"
    LOFT_FAILED = "freeform.loftFailed"
    NOT_A_FREEFORM_FEATURE = "freeform.notAFreeformFeature"


class IssueCode(StrEnum):
    POOR_FIT = "freeform.poorFit"


class ProgressStage(StrEnum):
    FITTING_PATCH = "freeform.fittingPatch"
    SECTIONING = "freeform.sectioning"
    LOFTING = "freeform.lofting"
