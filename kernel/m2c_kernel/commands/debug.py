"""Commands for protocol tests. Available only when `M2C_DEBUG_COMMANDS=1`."""

from __future__ import annotations

import ctypes
import os
import sys
import time
from dataclasses import dataclass
from typing import Annotated

from m2c_kernel.codes.kernel import ProgressStage
from m2c_kernel.protocol.registry import command
from m2c_kernel.protocol.wire import F32Array, Range, U32Array
from m2c_kernel.session.jobs import JobContext


@dataclass(frozen=True)
class SleepParams:
    seconds: Annotated[float, Range(0.0, 60.0)]


@dataclass(frozen=True)
class SleepResult:
    slept: float


@command("debug.sleep", caller="test", lane=True)
def debug_sleep(ctx: JobContext, params: SleepParams) -> SleepResult:
    """Sleep cooperatively, checking for cancellation every 10 ms."""
    start = time.monotonic()
    while time.monotonic() - start < params.seconds:
        ctx.check_cancelled()
        time.sleep(0.01)
    return SleepResult(slept=time.monotonic() - start)


@dataclass(frozen=True)
class ProgressParams:
    steps: Annotated[int, Range(1, 1000)]
    step_seconds: float = 0.01


@dataclass(frozen=True)
class ProgressResult:
    steps: int


@command("debug.progress", caller="test")
def debug_progress(ctx: JobContext, params: ProgressParams) -> ProgressResult:
    """Report progress for `steps` steps."""
    for step in range(params.steps):
        ctx.check_cancelled()
        ctx.progress((step + 1) / params.steps, ProgressStage.WORKING)
        time.sleep(params.step_seconds)
    return ProgressResult(steps=params.steps)


@dataclass(frozen=True)
class CrashParams:
    exit_code: int = 3


@dataclass(frozen=True)
class CrashResult:
    pass


@command("debug.crash", caller="test", light=True)
def debug_crash(ctx: JobContext, params: CrashParams) -> CrashResult:
    """Terminate the process immediately, as a native crash would."""
    os._exit(params.exit_code)


@dataclass(frozen=True)
class StdoutNoiseParams:
    pass


@dataclass(frozen=True)
class StdoutNoiseResult:
    ok: bool


@command("debug.stdoutNoise", caller="test")
def debug_stdout_noise(ctx: JobContext, params: StdoutNoiseParams) -> StdoutNoiseResult:
    """Write to stdout from Python and from C; none of it may reach the protocol stream."""
    print("python print on stdout")
    sys.stdout.flush()
    os.write(1, b"raw write on file descriptor 1\n")
    libc = ctypes.cdll.msvcrt if sys.platform == "win32" else ctypes.CDLL(None)
    libc.printf(b"C printf on stdout\n")
    libc.fflush(None)
    return StdoutNoiseResult(ok=True)


@dataclass(frozen=True)
class EchoParams:
    indices: U32Array
    values: F32Array


@dataclass(frozen=True)
class EchoResult:
    indices: U32Array
    values: F32Array
    index_sum: int


@command("debug.echoBuffers", caller="test")
def debug_echo_buffers(ctx: JobContext, params: EchoParams) -> EchoResult:
    """Return the received buffers unchanged (buffer transport round trip)."""
    return EchoResult(
        indices=params.indices.copy(),
        values=params.values.copy(),
        index_sum=int(params.indices.astype("int64").sum()),
    )


@dataclass(frozen=True)
class NativeBlockParams:
    milliseconds: Annotated[int, Range(0, 60_000)]


@dataclass(frozen=True)
class NativeBlockResult:
    pass


@command("debug.nativeBlock", caller="test", lane=True)
def debug_native_block(ctx: JobContext, params: NativeBlockParams) -> NativeBlockResult:
    """Hold the GIL in native code, as Open CASCADE does during long operations.

    While this runs, the reader thread cannot answer anything, including cancel.
    """
    with ctx.native():
        if sys.platform == "win32":
            ctypes.PyDLL("kernel32").Sleep(params.milliseconds)
        else:
            end = time.monotonic() + params.milliseconds / 1000
            previous = sys.getswitchinterval()
            sys.setswitchinterval(1000)
            while time.monotonic() < end:
                pass
            sys.setswitchinterval(previous)
    return NativeBlockResult()
