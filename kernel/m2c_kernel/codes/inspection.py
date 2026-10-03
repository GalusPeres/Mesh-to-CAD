"""Codes of the deviation analysis and measurements."""

from enum import StrEnum


class ErrorCode(StrEnum):
    NO_BODY = "inspection.noBody"
    UNKNOWN_BODY = "inspection.unknownBody"
    UNKNOWN_ITEM = "inspection.unknownItem"
    """A measured feature, body or face no longer exists."""
    ITEM_UNAVAILABLE = "inspection.itemUnavailable"
    """A measured feature failed, is suppressed or was skipped."""
    NOT_MEASURABLE = "inspection.notMeasurable"
    """The item has no plane, axis or point (a sketch, an extrusion)."""
    NO_PREVIEW = "inspection.noPreview"
    """The preview result is no longer cached (the tool previews again)."""


class ProgressStage(StrEnum):
    PREPARING = "inspection.preparing"
    COMPARING = "inspection.comparing"
