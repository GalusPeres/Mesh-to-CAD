"""Codes of STEP and STL export."""

from enum import StrEnum


class ErrorCode(StrEnum):
    WRITE_FAILED = "export.writeFailed"
    NO_BODY = "export.noBody"
    UNKNOWN_BODY = "export.unknownBody"
    BLOCKED = "export.blocked"
    VERIFY_FAILED = "export.verifyFailed"


class ProgressStage(StrEnum):
    WRITING = "export.writing"
    VERIFYING = "export.verifying"
