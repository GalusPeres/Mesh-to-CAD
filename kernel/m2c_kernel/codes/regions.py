"""Codes of selections, regions and segmentation."""

from enum import StrEnum


class ErrorCode(StrEnum):
    UNKNOWN_REGION = "regions.unknownRegion"
    NO_SCAN = "regions.noScan"
    INVALID_FACE = "regions.invalidFace"
    EMPTY_SELECTION = "regions.emptySelection"
    TOO_MANY_REGIONS = "regions.tooManyRegions"
    NO_SURFACE = "regions.noSurface"


class ProgressStage(StrEnum):
    ANALYSING = "regions.analysing"
    REDUCING = "regions.reducing"
    GROWING = "regions.growing"
    TRANSFERRING = "regions.transferring"
