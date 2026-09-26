"""Parameter types shared by several feature types."""

from __future__ import annotations

from typing import Literal

from m2c_kernel.codes.document import ErrorCode
from m2c_kernel.protocol.errors import KernelError

type BodyOperation = Literal["newBody", "add", "cut", "intersect"]
"""How a solid feature's result combines with `target_body`."""

type StandardPlane = Literal["XY", "YZ", "XZ"]
type StandardAxis = Literal["X", "Y", "Z"]

STANDARD_NAMES = frozenset({"XY", "YZ", "XZ", "X", "Y", "Z"})


def feature_refs(*names: str | None) -> tuple[str, ...]:
    """Feature ids among `names`, skipping standard planes, axes and empty values."""
    return tuple(name for name in names if name and name not in STANDARD_NAMES)


def not_implemented(type_id: str) -> KernelError:
    """The error a feature type reports until its evaluation exists."""
    return KernelError(ErrorCode.FEATURE_NOT_IMPLEMENTED, {"type": type_id})
