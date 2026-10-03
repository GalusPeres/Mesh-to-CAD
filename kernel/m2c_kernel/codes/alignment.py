"""Codes of the scan alignment."""

from enum import StrEnum


class ErrorCode(StrEnum):
    PARALLEL_INPUTS = "alignment.parallelInputs"
    NO_POINT = "alignment.noPoint"
    INPUT_NOT_FOUND = "alignment.inputNotFound"
    UNSUPPORTED_INPUT = "alignment.unsupportedInput"
    TOO_FEW_FACES = "alignment.tooFewFaces"
    FIT_FAILED = "alignment.fitFailed"
    INVALID_PARAMS = "alignment.invalidParams"


class IssueCode(StrEnum):
    PCA_FALLBACK = "alignment.pcaFallback"
    SINGLE_PLANE = "alignment.singlePlane"


class ProgressStage(StrEnum):
    DETECTING_PLANES = "alignment.detectingPlanes"
    FITTING_INPUTS = "alignment.fittingInputs"
