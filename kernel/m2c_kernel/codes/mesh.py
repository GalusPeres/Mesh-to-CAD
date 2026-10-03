"""Codes of mesh import and preparation."""

from enum import StrEnum


class ErrorCode(StrEnum):
    FILE_NOT_FOUND = "mesh.fileNotFound"
    FILE_TOO_LARGE = "mesh.fileTooLarge"
    UNSUPPORTED_FORMAT = "mesh.unsupportedFormat"
    READ_FAILED = "mesh.readFailed"
    INVALID_STL = "mesh.invalidStl"
    EMPTY = "mesh.empty"
    TOO_MANY_FACES = "mesh.tooManyFaces"
    REDUCTION_REQUIRED = "mesh.reductionRequired"
    UNKNOWN_IMPORT = "mesh.unknownImport"
    NO_SCAN = "mesh.noScan"
    STALE_SELECTION = "mesh.staleSelection"
    NOTHING_LEFT = "mesh.nothingLeft"
    DECIMATION_FAILED = "mesh.decimationFailed"


class ProgressStage(StrEnum):
    READING = "mesh.reading"
    WELDING = "mesh.welding"
    ESTIMATING_NOISE = "mesh.estimatingNoise"
    REPAIRING = "mesh.repairing"
    REMOVING_SMALL_PARTS = "mesh.removingSmallParts"
    DECIMATING = "mesh.decimating"
    FILLING_HOLES = "mesh.fillingHoles"
    INSPECTING = "mesh.inspecting"
    STORING = "mesh.storing"
