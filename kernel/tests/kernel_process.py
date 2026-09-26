"""Runs the kernel as a subprocess and speaks the protocol with it (test helper).

`M2C_KERNEL_EXE` selects a PyInstaller build instead of `python -m m2c_kernel`,
so the same tests can run against the frozen kernel.
"""

from __future__ import annotations

import itertools
import os
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from m2c_kernel.protocol.frame import Frame, encode_frame, read_frame

KERNEL_DIR = Path(__file__).resolve().parents[1]


@dataclass
class Response:
    header: dict[str, Any]
    buffers: list[memoryview]
    events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.header["ok"])

    @property
    def result(self) -> Any:
        assert self.ok, self.header.get("error")
        return self.header["result"]

    @property
    def error_code(self) -> str:
        assert not self.ok, "expected an error response"
        return str(self.header["error"]["code"])


class KernelProcess:
    """A running kernel with a background reader that sorts responses and events."""

    def __init__(self, session_dir: Path, debug_commands: bool = True) -> None:
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in ("PYTHONPATH", "PYTHONHOME")
        }
        env.update({"PYTHONUTF8": "1", "M2C_LOG_LEVEL": "WARNING"})
        if debug_commands:
            env["M2C_DEBUG_COMMANDS"] = "1"
        executable = os.environ.get("M2C_KERNEL_EXE")
        if executable:
            command = [executable, "--session-dir", str(session_dir)]
        else:
            command = [
                sys.executable,
                "-X",
                "utf8",
                "-u",
                "-m",
                "m2c_kernel",
                "--session-dir",
                str(session_dir),
            ]
        self.process = subprocess.Popen(
            command,
            cwd=KERNEL_DIR,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._ids = itertools.count(1)
        self._responses: dict[int, queue.Queue[Frame]] = {}
        self._events: queue.Queue[Frame] = queue.Queue()
        self._lock = threading.Lock()
        self.stderr_lines: list[str] = []
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_stdout(self) -> None:
        assert self.process.stdout is not None
        while True:
            try:
                frame = read_frame(self.process.stdout)
            except Exception:
                return
            if frame is None:
                return
            if frame.header.get("type") == "response":
                self._response_queue(frame.header["id"]).put(frame)
            else:
                self._events.put(frame)

    def _read_stderr(self) -> None:
        assert self.process.stderr is not None
        for line in self.process.stderr:
            self.stderr_lines.append(line.decode("utf-8", "replace").rstrip())

    def _response_queue(self, request_id: int) -> queue.Queue[Frame]:
        with self._lock:
            return self._responses.setdefault(request_id, queue.Queue())

    def next_event(self, name: str | None = None, timeout: float = 10.0) -> dict[str, Any]:
        """The next event (of the given name), skipping others."""
        deadline = time.monotonic() + timeout
        while True:
            frame = self._events.get(timeout=max(deadline - time.monotonic(), 0.001))
            if name is None or frame.header.get("event") == name:
                return frame.header

    def send(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        origin: str = "renderer",
        lane: str | None = None,
        buffers: Sequence[np.ndarray] = (),
    ) -> int:
        request_id = next(self._ids)
        header: dict[str, Any] = {
            "type": "request",
            "id": request_id,
            "method": method,
            "params": params or {},
            "origin": origin,
        }
        if lane is not None:
            header["lane"] = lane
        self._write(header, buffers)
        return request_id

    def cancel(self, request_id: int) -> None:
        self._write({"type": "cancel", "id": request_id}, ())

    def wait(self, request_id: int, timeout: float = 30.0) -> Response:
        frame = self._response_queue(request_id).get(timeout=timeout)
        return Response(frame.header, frame.buffers)

    def call(self, method: str, params: dict[str, Any] | None = None, **options: Any) -> Response:
        timeout = options.pop("timeout", 60.0)
        return self.wait(self.send(method, params, **options), timeout=timeout)

    def _write(self, header: dict[str, Any], buffers: Sequence[np.ndarray]) -> None:
        assert self.process.stdin is not None
        with self._lock:
            for chunk in encode_frame(header, buffers):
                self.process.stdin.write(chunk)
            self.process.stdin.flush()

    def stop(self) -> int:
        if self.process.poll() is None:
            try:
                self.call("system.shutdown", origin="main", timeout=10)
            except Exception:
                self.process.kill()
        try:
            return self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            return self.process.wait()
