"""Codes of the protocol and the kernel process itself."""

from enum import StrEnum


class ErrorCode(StrEnum):
    INTERNAL = "kernel.internal"
    INVALID_PARAMS = "kernel.invalidParams"
    UNKNOWN_METHOD = "kernel.unknownMethod"
    NOT_ALLOWED = "kernel.notAllowed"
    CANCELLED = "kernel.cancelled"
    SUPERSEDED = "kernel.superseded"
    BUSY = "kernel.busy"
    NOT_IMPLEMENTED = "kernel.notImplemented"
    # Raised by the application's kernel host, not by the kernel process.
    STOPPED = "kernel.stopped"
    START_FAILED = "kernel.startFailed"
    PROTOCOL_MISMATCH = "kernel.protocolMismatch"


class ProgressStage(StrEnum):
    NATIVE = "kernel.native"
    WORKING = "kernel.working"
