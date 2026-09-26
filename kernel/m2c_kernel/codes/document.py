"""Codes of the document model, revisions and the rebuild engine."""

from enum import StrEnum


class ErrorCode(StrEnum):
    NO_SCAN = "document.noScan"
    STALE_REVISION = "document.staleRevision"
    REVISION_GONE = "document.revisionGone"
    UNKNOWN_FEATURE = "document.unknownFeature"
    UNKNOWN_FEATURE_TYPE = "document.unknownFeatureType"
    FORWARD_REFERENCE = "document.forwardReference"
    HAS_DEPENDENTS = "document.hasDependents"
    LIMIT_EXCEEDED = "document.limitExceeded"
    FEATURE_NOT_IMPLEMENTED = "document.featureNotImplemented"
    INPUT_UNAVAILABLE = "document.inputUnavailable"


class ProgressStage(StrEnum):
    REBUILDING = "document.rebuilding"
