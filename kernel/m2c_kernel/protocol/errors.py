"""Errors that reach the protocol with a translatable code."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

type ErrorParam = str | int | float | bool | None


class KernelError(Exception):
    """A failure the user should see, identified by a code the renderer translates.

    `code` has the form `<group>.<camelCase>` and doubles as the i18n key in the
    `errors` namespace. `params` carry the values for the message (numbers stay
    numbers; the renderer formats them). `details` is technical text for the log
    and the *Details* disclosure, never shown as the main message.
    """

    def __init__(
        self,
        code: StrEnum | str,
        params: Mapping[str, ErrorParam] | None = None,
        details: str | None = None,
    ) -> None:
        self.code = str(code)
        self.params: dict[str, ErrorParam] = dict(params or {})
        self.details = details
        super().__init__(f"{self.code} {self.params}" + (f": {details}" if details else ""))


class Cancelled(Exception):  # noqa: N818 (a control-flow signal, not an error)
    """Raised by `JobContext.check_cancelled` when the request was cancelled."""
