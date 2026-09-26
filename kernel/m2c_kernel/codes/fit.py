"""Codes of primitive fitting and design-intent snapping."""

from enum import StrEnum


class ErrorCode(StrEnum):
    TOO_FEW_FACES = "fit.tooFewFaces"
    DID_NOT_CONVERGE = "fit.didNotConverge"
    INVALID_RELATION = "fit.invalidRelation"
    FIXED_NOT_APPLICABLE = "fit.fixedNotApplicable"
    INVALID_VALUE = "fit.invalidValue"
    STALE_SELECTION = "fit.staleSelection"
    NOT_A_FIT = "fit.notAFit"


class IssueCode(StrEnum):
    POOR_FIT = "fit.poorFit"
