"""Codes of project files."""

from enum import StrEnum


class ErrorCode(StrEnum):
    FILE_NOT_FOUND = "project.fileNotFound"
    CORRUPT = "project.corrupt"
    UNSUPPORTED_VERSION = "project.unsupportedVersion"
    SAVE_FAILED = "project.saveFailed"
    READ_FAILED = "project.readFailed"


class ProgressStage(StrEnum):
    SAVING = "project.saving"
    LOADING = "project.loading"
