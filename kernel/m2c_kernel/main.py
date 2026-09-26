"""Process entry point: protect the protocol channel, configure logging, serve.

Open CASCADE and other native libraries print to the C-level standard output.
Before anything can print, the real stdout is duplicated into a private file
object for the protocol, and file descriptor 1 is pointed at stderr. Every
stray `print` or native write then ends up in the log instead of corrupting a
frame. The application copies stderr into `kernel.log`.
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import sys
from collections.abc import Sequence
from functools import partial
from pathlib import Path
from typing import BinaryIO, cast


def _protect_stdout() -> BinaryIO:
    protocol_out = os.fdopen(os.dup(1), "wb", buffering=0)
    os.dup2(2, 1)
    sys.stdout = os.fdopen(1, "w", buffering=1, encoding="utf-8", closefd=False)
    return protocol_out


def _configure_logging() -> None:
    level = os.environ.get("M2C_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        stream=sys.stderr,
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _warm_up() -> None:
    """Import the heavy libraries once, off the startup path, and silence OCCT."""
    import scipy.optimize
    import scipy.spatial
    import trimesh

    from m2c_kernel.cad.occ_compat import quiet_occt

    quiet_occt()
    del scipy, trimesh


def _parse(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="m2c-kernel", description="Mesh-to-CAD geometry kernel")
    parser.add_argument("--session-dir", type=Path, required=True, help="session directory to use")
    return parser.parse_args(argv)


def run(argv: Sequence[str] | None = None) -> int:
    protocol_out = _protect_stdout()
    args = _parse(argv)
    _configure_logging()

    from m2c_kernel.protocol.registry import load_commands
    from m2c_kernel.protocol.server import Server
    from m2c_kernel.session.session import Session

    server = Server(
        input_stream=cast(io.BufferedReader, sys.stdin.buffer),
        output_stream=protocol_out,
        commands=load_commands(),
        session_factory=partial(Session.open, args.session_dir),
        warmup=_warm_up,
        debug_commands=os.environ.get("M2C_DEBUG_COMMANDS") == "1",
    )
    code = server.run()
    # The reader thread may still block in a read on stdin. Normal interpreter
    # shutdown would then abort while taking the stdin lock, so the process ends
    # here, after the session lock is released and the logs are flushed.
    logging.shutdown()
    sys.stderr.flush()
    os._exit(code)
