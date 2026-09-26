"""Codes of primitive fitting and design-intent snapping."""

from enum import StrEnum


class ErrorCode(StrEnum):
    TOO_FEW_FACES = "fit.tooFewFaces"
    DID_NOT_CONVERGE = "fit.didNotConverge"
    INVALID_RELATION = "fit.invalidRelation"


class IssueCode(StrEnum):
    POOR_FIT = "fit.poorFit"
