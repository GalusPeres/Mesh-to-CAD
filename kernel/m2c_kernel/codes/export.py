"""Codes of STEP and STL export."""

from enum import StrEnum


class ErrorCode(StrEnum):
    NO_BODY = "export.noBody"
    UNKNOWN_BODY = "export.unknownBody"
    UNKNOWN_SURFACE = "export.unknownSurface"
    """`surface` names no feature with an open surface (an open freeform net)."""
    BLOCKED = "export.blocked"
    """A body failed the pre-flight check; `problem` is its `IssueCode`."""
    INVALID_NAMES = "export.invalidNames"
    WRITE_FAILED = "export.writeFailed"
    VERIFY_FAILED = "export.verifyFailed"
    """The file read back differs from the bodies; the target file was left untouched."""


class IssueCode(StrEnum):
    """Pre-flight findings; all but `HIGH_TOLERANCE` block the export."""

    NOT_VALID = "export.notValid"
    NOT_CLOSED = "export.notClosed"
    NOT_ONE_SOLID = "export.notOneSolid"
    NO_VOLUME = "export.noVolume"
    HIGH_TOLERANCE = "export.highTolerance"


class ProgressStage(StrEnum):
    WRITING = "export.writing"
    VERIFYING = "export.verifying"
