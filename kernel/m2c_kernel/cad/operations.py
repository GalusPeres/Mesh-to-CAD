"""How a new solid combines with the existing bodies (`operation`, `targetBody`).

`newBody` adds a body whose id is the feature id (ARCHITECTURE.md 4.4); `add`,
`cut` and `intersect` change the target body, which keeps its id.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from m2c_kernel.cad.booleans import boolean
from m2c_kernel.codes.cad import ErrorCode
from m2c_kernel.document.results import Body, BodyUpdate, FeatureOutput
from m2c_kernel.protocol.errors import KernelError

type BodyOperation = Literal["newBody", "add", "cut", "intersect"]


def require_target(operation: BodyOperation, target_body: str | None) -> str | None:
    """The target body id; operations other than `newBody` need one."""
    if operation != "newBody" and not target_body:
        raise KernelError(ErrorCode.TARGET_REQUIRED, {"operation": operation})
    return target_body if operation != "newBody" else None


def solid_output(
    feature_id: str,
    operation: BodyOperation,
    target_body: str | None,
    created: Body,
    body_of: Callable[[str], Body],
) -> FeatureOutput:
    """Feature output for a created solid under `operation`."""
    target_id = require_target(operation, target_body)
    if target_id is None or operation == "newBody":
        return FeatureOutput(bodies=BodyUpdate(changed={feature_id: created}))
    result = boolean(operation, body_of(target_id), [created])
    return FeatureOutput(bodies=BodyUpdate(changed={target_id: result.body}), issues=result.issues)
