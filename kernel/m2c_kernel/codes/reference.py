"""Codes of reference geometry (planes and axes built from other features)."""

from enum import StrEnum


class ErrorCode(StrEnum):
    NOT_A_PLANE = "reference.notAPlane"
    NOT_AN_AXIS = "reference.notAnAxis"
    PARALLEL_PLANES = "reference.parallelPlanes"
    NOT_PARALLEL = "reference.notParallel"
