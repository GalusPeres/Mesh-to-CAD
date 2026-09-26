"""Codes of the solid modelling operations (Open CASCADE)."""

from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_RESULT = "cad.invalidResult"
    OCCT_UNAVAILABLE = "cad.occtUnavailable"


class IssueCode(StrEnum):
    HIGH_TOLERANCE = "cad.highTolerance"


class ProgressStage(StrEnum):
    TESSELLATING = "cad.tessellating"
