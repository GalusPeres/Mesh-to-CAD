"""Codes of the deviation analysis and measurements."""

from enum import StrEnum


class ErrorCode(StrEnum):
    NO_BODY = "inspection.noBody"
    UNKNOWN_BODY = "inspection.unknownBody"
    UNKNOWN_REFERENCE = "inspection.unknownReference"
    NOT_MEASURABLE = "inspection.notMeasurable"
    NO_PREVIEW = "inspection.noPreview"


class ProgressStage(StrEnum):
    PREPARING = "inspection.preparing"
    COMPARING = "inspection.comparing"
