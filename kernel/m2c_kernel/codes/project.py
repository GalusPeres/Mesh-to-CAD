"""Codes of project files and session recovery."""

from enum import StrEnum


class ErrorCode(StrEnum):
    CORRUPT = "project.corrupt"
    UNSUPPORTED_VERSION = "project.unsupportedVersion"
