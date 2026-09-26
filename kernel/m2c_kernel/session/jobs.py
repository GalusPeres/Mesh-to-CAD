"""The context passed to every command handler."""

from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

import numpy as np

from m2c_kernel.codes.kernel import ProgressStage
from m2c_kernel.protocol.errors import Cancelled

if TYPE_CHECKING:
    from m2c_kernel.session.session import Session

type ProgressSink = Callable[[float | None, str], None]

_PROGRESS_INTERVAL_S = 0.1


class JobContext:
    """Progress, cancellation and session access for one request.

    Long loops call `check_cancelled()` regularly. Before a long native call that
    holds the GIL (Open CASCADE, fast_simplification), wrap it in
    `with ctx.native(stage):` so the application shows an indeterminate progress
    bar; cancelling such a call is handled by the application (see ARCHITECTURE.md 3.5.4).
    """

    def __init__(
        self,
        request_id: int,
        session: Session | None,
        progress_sink: ProgressSink | None = None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        self.request_id = request_id
        self._session = session
        self._sink = progress_sink
        self._cancel_event = cancel_event or threading.Event()
        self._last_progress = 0.0

    @classmethod
    def detached(cls, session: Session | None = None) -> JobContext:
        """A context without a client: no progress events, never cancelled."""
        return cls(request_id=0, session=session)

    @property
    def session(self) -> Session:
        if self._session is None:
            raise RuntimeError("this job has no session")
        return self._session

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def check_cancelled(self) -> None:
        """Raise `Cancelled` if the request was cancelled or superseded."""
        if self._cancel_event.is_set():
            raise Cancelled

    def progress(self, fraction: float | None, stage: str) -> None:
        """Report progress; `fraction` None means indeterminate. Throttled to 10 per second."""
        now = time.monotonic()
        if self._sink is None:
            return
        intermediate = fraction is not None and 0.0 < fraction < 1.0
        if intermediate and now - self._last_progress < _PROGRESS_INTERVAL_S:
            return
        self._last_progress = now
        self._sink(fraction, stage)

    @contextmanager
    def native(self, stage: str = ProgressStage.NATIVE) -> Iterator[None]:
        """Mark a native call that cannot report progress or be interrupted."""
        self.check_cancelled()
        self.progress(None, stage)
        yield
        self.check_cancelled()


def seeded_rng(key: str) -> np.random.Generator:
    """A random generator seeded from a string, so results are reproducible per input."""
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "little"))
