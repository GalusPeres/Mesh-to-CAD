"""Native library calls in a spawned, killable child process.

Some native libraries (fast_simplification, Instant Meshes) keep their state in C++
globals, cannot be interrupted, hold the GIL for the whole call and may print to
stdout, which carries the protocol. They therefore run in a spawned child process.
The child inherits the kernel's standard output, which already points at stderr
(`m2c_kernel.main`), and moves fd 1 to stderr once more before it runs the call. The
parent polls for the result and kills the child when the job is cancelled, so a
cancel takes effect within one polling interval.

`function` must be a module-level function (the spawn context pickles it by name).
"""

from __future__ import annotations

import contextlib
import multiprocessing
import os
import sys
import threading
from collections.abc import Callable, Iterator
from multiprocessing.connection import Connection
from typing import Any

_POLL_S = 0.05


class ChildCallError(Exception):
    """The child process ended without a result, or the call raised in the child."""


def run_in_child[T](
    function: Callable[..., T],
    args: tuple[Any, ...],
    check_cancelled: Callable[[], None] = lambda: None,
) -> T:
    """`function(*args)` in a child process; the child is killed when the job is cancelled.

    Raises:
        ChildCallError: The call raised in the child, or the child died.
    """
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    child = context.Process(target=_child_main, args=(sender, function, args), daemon=True)
    with _stdin_detached():
        child.start()
    sender.close()
    try:
        while not receiver.poll(_POLL_S):
            try:
                check_cancelled()
            except BaseException:
                child.kill()
                raise
            if not child.is_alive() and not receiver.poll(0):
                raise ChildCallError(f"exit code {child.exitcode}")
        try:
            outcome: tuple[bool, Any] = receiver.recv()
        except EOFError as error:
            raise ChildCallError(f"exit code {child.exitcode}") from error
    finally:
        child.join(timeout=5)
        if child.is_alive():
            child.kill()
        receiver.close()
    succeeded, value = outcome
    if not succeeded:
        raise ChildCallError(value)
    result: T = value
    return result


_std_handle_lock = threading.Lock()


@contextlib.contextmanager
def _stdin_detached() -> Iterator[None]:
    """Start children with NUL as standard input (Windows).

    The kernel's reader thread keeps a synchronous read pending on the stdin pipe.
    A console child that receives a duplicate of that handle blocks in its startup
    (Python queries the handle) until the read completes, which can be forever.
    The process-wide standard input handle is therefore swapped for NUL while the
    child is created; the C runtime keeps its own handle for fd 0, so the reader
    thread is not affected.
    """
    if sys.platform != "win32":
        yield
        return
    import ctypes
    import msvcrt

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetStdHandle.restype = ctypes.c_void_p
    kernel32.SetStdHandle.argtypes = (ctypes.c_uint32, ctypes.c_void_p)
    std_input = ctypes.c_uint32(-10 & 0xFFFFFFFF)
    with _std_handle_lock, open(os.devnull, "rb") as null:
        previous = kernel32.GetStdHandle(std_input)
        kernel32.SetStdHandle(std_input, msvcrt.get_osfhandle(null.fileno()))
        try:
            yield
        finally:
            kernel32.SetStdHandle(std_input, previous)


def _child_main(sender: Connection, function: Callable[..., Any], args: tuple[Any, ...]) -> None:
    os.dup2(2, 1)
    try:
        sender.send((True, function(*args)))
    except Exception as error:
        sender.send((False, repr(error)))
    finally:
        sender.close()
