"""Codes of section sketches."""

from enum import StrEnum


class ErrorCode(StrEnum):
    EMPTY_SECTION = "sketch.emptySection"
    NOT_A_PLANE = "sketch.notAPlane"
    NOT_AN_AXIS = "sketch.notAnAxis"
    INVALID_GEOMETRY = "sketch.invalidGeometry"
    TOO_FEW_POINTS = "sketch.tooFewPoints"


class IssueCode(StrEnum):
    PROFILE_OPEN = "sketch.profileOpen"
    PROFILE_INVALID = "sketch.profileInvalid"
    DEVIATES_FROM_SCAN = "sketch.deviatesFromScan"
    SECTION_EMPTY = "sketch.sectionEmpty"
