"""Codes of reference geometry (planes, axes and points built from other features)."""

from enum import StrEnum


class ErrorCode(StrEnum):
    UNSUPPORTED_INPUT = "reference.unsupportedInput"
    NOT_A_PLANE = "reference.notAPlane"
    NOT_AN_AXIS = "reference.notAnAxis"
    PARALLEL_PLANES = "reference.parallelPlanes"
    NOT_PARALLEL = "reference.notParallel"
