"""Kernel information and lifecycle."""

from __future__ import annotations

import platform
import time
from dataclasses import dataclass

import numpy as np

from m2c_kernel import __version__
from m2c_kernel.protocol import PROTOCOL_VERSION
from m2c_kernel.protocol.registry import command
from m2c_kernel.session.jobs import JobContext


@dataclass(frozen=True)
class SystemInfoParams:
    pass


@dataclass(frozen=True)
class SystemInfoResult:
    kernel_version: str
    protocol_version: int
    python_version: str
    numpy_version: str
    ocp_version: str
    occt_version: str
    platform: str


@command("system.info")
def system_info(ctx: JobContext, params: SystemInfoParams) -> SystemInfoResult:
    """Versions of the kernel and its libraries (shown in the About dialog and bug reports)."""
    from m2c_kernel.cad.occ_compat import occt_version, ocp_version

    return SystemInfoResult(
        kernel_version=__version__,
        protocol_version=PROTOCOL_VERSION,
        python_version=platform.python_version(),
        numpy_version=np.__version__,
        ocp_version=ocp_version(),
        occt_version=occt_version(),
        platform=platform.platform(),
    )


@dataclass(frozen=True)
class PingParams:
    pass


@dataclass(frozen=True)
class PingResult:
    time: float


@command("system.ping", light=True)
def system_ping(ctx: JobContext, params: PingParams) -> PingResult:
    """Answer immediately; used to check that the kernel is responsive."""
    return PingResult(time=time.time())


@dataclass(frozen=True)
class ShutdownParams:
    pass


@dataclass(frozen=True)
class ShutdownResult:
    pass


@command("system.shutdown", caller="main", light=True)
def system_shutdown(ctx: JobContext, params: ShutdownParams) -> ShutdownResult:
    """Stop after this response; the server exits once it is sent."""
    return ShutdownResult()
