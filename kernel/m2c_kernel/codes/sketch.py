"""Codes of section sketches."""

from enum import StrEnum


class ErrorCode(StrEnum):
    EMPTY_SECTION = "sketch.emptySection"


class IssueCode(StrEnum):
    PROFILE_OPEN = "sketch.profileOpen"
