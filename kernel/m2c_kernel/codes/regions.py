"""Codes of selections, regions and segmentation."""

from enum import StrEnum


class ErrorCode(StrEnum):
    NO_SCAN = "regions.noScan"
    STALE_SCAN = "regions.staleScan"
    INVALID_FACE = "regions.invalidFace"
    EMPTY_SELECTION = "regions.emptySelection"
    UNKNOWN_REGION = "regions.unknownRegion"
    MERGE_NEEDS_TWO = "regions.mergeNeedsTwo"
    TOO_MANY_REGIONS = "regions.tooManyRegions"


class ProgressStage(StrEnum):
    ANALYSING = "regions.analysing"
    REDUCING = "regions.reducing"
    GROWING = "regions.growing"
    REFINING = "regions.refining"
    TRANSFERRING = "regions.transferring"
