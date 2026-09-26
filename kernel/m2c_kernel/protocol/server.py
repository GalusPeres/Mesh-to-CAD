"""Request dispatcher: one reader thread, one worker thread, lanes and cancellation.

The reader thread parses frames and answers everything that needs no
computation (unknown methods, invalid parameters, superseded and cancelled
queued requests). The worker thread executes requests in arrival order.

Native calls into Open CASCADE or fast_simplification hold the GIL, so while
one runs the reader cannot answer anything. The application therefore never
waits for the kernel to acknowledge a cancel: it rejects the request itself and
offers a restart when the kernel stays busy (ARCHITECTURE.md 3.5.4).
"""

from __future__ import annotations

import logging
import platform
import sys
import threading
import traceback
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

import numpy as np

from m2c_kernel import __version__
from m2c_kernel.codes.kernel import ErrorCode
from m2c_kernel.protocol import PROTOCOL_VERSION
from m2c_kernel.protocol.errors import Cancelled, KernelError
from m2c_kernel.protocol.frame import (
    Frame,
    FrameError,
    ReadableStream,
    WritableStream,
    read_frame,
    write_frame,
)
from m2c_kernel.protocol.registry import CommandSpec, lane_is_valid
from m2c_kernel.protocol.wire import from_wire, to_wire
from m2c_kernel.session.jobs import JobContext

if TYPE_CHECKING:
    from m2c_kernel.session.session import Session

log = logging.getLogger(__name__)


class EventSink(Protocol):
    def emit_event(self, event: str, data: Any, buffers: Sequence[np.ndarray] = ()) -> None: ...


type SessionFactory = Callable[[EventSink], Session]


@dataclass(eq=False)
class _Job:
    request_id: int
    spec: CommandSpec
    params: Any
    lane: str | None
    cancel: threading.Event = field(default_factory=threading.Event)
    superseded: bool = False


class Server:
    """Serves protocol requests until the input ends or `system.shutdown` is called."""

    def __init__(
        self,
        *,
        input_stream: ReadableStream,
        output_stream: WritableStream,
        commands: Mapping[str, CommandSpec],
        session_factory: SessionFactory,
        warmup: Callable[[], None] | None = None,
        debug_commands: bool = False,
    ) -> None:
        self._input = input_stream
        self._output = output_stream
        self._commands = commands
        self._session_factory = session_factory
        self._warmup_fn = warmup
        self._debug_commands = debug_commands
        self._write_lock = threading.Lock()
        self._queue: deque[_Job] = deque()
        self._queue_changed = threading.Condition()
        self._running: _Job | None = None
        self._stop = threading.Event()
        self._warm = threading.Event()
        self._warm_error: BaseException | None = None
        self._session: Session | None = None

    def run(self) -> int:
        """Start the threads and block until the server stops. Returns the exit code."""
        self._session = self._session_factory(self)
        self.emit_event(
            "ready",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "kernelVersion": __version__,
                "pythonVersion": platform.python_version(),
            },
        )
        threading.Thread(target=self._warm_up, name="warmup", daemon=True).start()
        threading.Thread(target=self._work, name="worker", daemon=True).start()
        threading.Thread(target=self._read, name="reader", daemon=True).start()
        self._stop.wait()
        self._session.close()
        return 0

    @property
    def session(self) -> Session | None:
        return self._session

    def emit_event(self, event: str, data: Any, buffers: Sequence[np.ndarray] = ()) -> None:
        self._send({"type": "event", "event": event, "data": data}, buffers)

    def _send(self, header: dict[str, Any], buffers: Sequence[np.ndarray] = ()) -> None:
        with self._write_lock:
            write_frame(self._output, header, buffers)

    def _respond_error(self, request_id: int, error: KernelError) -> None:
        payload: dict[str, Any] = {"code": error.code, "params": error.params}
        if error.details:
            payload["details"] = error.details
        self._send({"type": "response", "id": request_id, "ok": False, "error": payload})

    def _warm_up(self) -> None:
        try:
            if self._warmup_fn is not None:
                self._warmup_fn()
        except BaseException as error:  # reported to every request that needs the imports
            self._warm_error = error
            log.exception("loading the geometry libraries failed")
        finally:
            self._warm.set()

    def _read(self) -> None:
        try:
            while not self._stop.is_set():
                frame = read_frame(self._input)
                if frame is None:
                    log.info("input closed; stopping")
                    break
                self._dispatch(frame)
        except FrameError:
            log.exception("protocol error on the input stream; stopping")
        finally:
            self._stop_now()

    def _dispatch(self, frame: Frame) -> None:
        kind = frame.header.get("type")
        if kind == "request":
            self._accept(frame)
        elif kind == "cancel":
            self._cancel(frame.header.get("id"))
        else:
            log.warning("ignoring frame of type %r", kind)

    def _accept(self, frame: Frame) -> None:
        header = frame.header
        request_id = header.get("id")
        if not isinstance(request_id, int):
            log.warning("ignoring request without an integer id")
            return
        method, lane, origin = header.get("method"), header.get("lane"), header.get("origin")
        spec = self._commands.get(method) if isinstance(method, str) else None
        if spec is None or (spec.caller == "test" and not self._debug_commands):
            self._respond_error(
                request_id, KernelError(ErrorCode.UNKNOWN_METHOD, {"method": method})
            )
            return
        if spec.caller == "main" and origin != "main":
            self._respond_error(request_id, KernelError(ErrorCode.NOT_ALLOWED, {"method": method}))
            return
        if lane is not None and not (isinstance(lane, str) and lane_is_valid(spec, lane)):
            self._respond_error(
                request_id, KernelError(ErrorCode.INVALID_PARAMS, {"field": "lane"}, str(lane))
            )
            return
        try:
            params: Any = from_wire(header.get("params", {}), spec.params_type, frame.buffers)
        except KernelError as error:
            self._respond_error(request_id, error)
            return
        self._enqueue(_Job(request_id, spec, params, lane))

    def _enqueue(self, job: _Job) -> None:
        with self._queue_changed:
            running = self._running
            if job.lane is not None:
                if running is not None and running.spec.exclusive:
                    self._respond_error(job.request_id, KernelError(ErrorCode.BUSY))
                    return
                for queued in [queued for queued in self._queue if queued.lane == job.lane]:
                    self._queue.remove(queued)
                    self._respond_error(queued.request_id, KernelError(ErrorCode.SUPERSEDED))
                if running is not None and running.lane == job.lane:
                    running.superseded = True
                    running.cancel.set()
            self._queue.append(job)
            self._queue_changed.notify()

    def _cancel(self, request_id: object) -> None:
        with self._queue_changed:
            for queued in self._queue:
                if queued.request_id == request_id:
                    self._queue.remove(queued)
                    self._respond_error(queued.request_id, KernelError(ErrorCode.CANCELLED))
                    return
            if self._running is not None and self._running.request_id == request_id:
                self._running.cancel.set()

    def _work(self) -> None:
        while True:
            with self._queue_changed:
                while not self._queue and not self._stop.is_set():
                    self._queue_changed.wait()
                if self._stop.is_set():
                    return
                job = self._queue.popleft()
                self._running = job
            try:
                self._execute(job)
            finally:
                with self._queue_changed:
                    self._running = None
            if job.spec.method == "system.shutdown":
                self._stop_now()
                return

    def _execute(self, job: _Job) -> None:
        if not job.spec.light:
            while not self._warm.wait(0.05):
                if job.cancel.is_set():
                    code = ErrorCode.SUPERSEDED if job.superseded else ErrorCode.CANCELLED
                    self._respond_error(job.request_id, KernelError(code))
                    return
            if self._warm_error is not None:
                error = KernelError(ErrorCode.INTERNAL, details=repr(self._warm_error))
                self._respond_error(job.request_id, error)
                return
        context = JobContext(
            job.request_id,
            self._session,
            progress_sink=lambda fraction, stage: self._progress(job, fraction, stage),
            cancel_event=job.cancel,
        )
        try:
            result = job.spec.handler(context, job.params)
            if job.lane is not None and job.cancel.is_set():
                raise Cancelled
            payload, buffers = to_wire(result, job.spec.result_type)
            self._send(
                {"type": "response", "id": job.request_id, "ok": True, "result": payload}, buffers
            )
        except Cancelled:
            code = ErrorCode.SUPERSEDED if job.superseded else ErrorCode.CANCELLED
            self._respond_error(job.request_id, KernelError(code))
        except KernelError as error:
            self._respond_error(job.request_id, error)
        except Exception:
            log.exception("request %s (%s) failed", job.request_id, job.spec.method)
            details = traceback.format_exc()
            self._respond_error(job.request_id, KernelError(ErrorCode.INTERNAL, details=details))

    def _progress(self, job: _Job, fraction: float | None, stage: str) -> None:
        data = {"fraction": fraction, "stage": stage}
        self._send(
            {"type": "event", "event": "progress", "requestId": job.request_id, "data": data}
        )

    def _stop_now(self) -> None:
        self._stop.set()
        with self._queue_changed:
            self._queue_changed.notify_all()


def python_description() -> str:
    """Interpreter description for `system.info`."""
    return f"{platform.python_implementation()} {platform.python_version()} ({sys.platform})"
