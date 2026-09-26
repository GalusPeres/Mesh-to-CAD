"""Registry of protocol commands.

A command is a function in a module of `m2c_kernel.commands`, decorated with
`@command`. The parameter and result types come from its annotations:

    @command("fit.preview", lane=True)
    def fit_preview(ctx: JobContext, params: FitPreviewParams) -> FitPreviewResult: ...

The module name is the command group, and every method of a module must start
with `<group>.`. Codegen reads this registry to write the TypeScript method maps.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass, is_dataclass
from typing import Any, Literal, get_type_hints

type Caller = Literal["renderer", "main", "test"]

type Handler = Callable[[Any, Any], Any]


@dataclass(frozen=True)
class CommandSpec:
    """Metadata of one protocol method.

    Attributes:
        method: Wire name, `<group>.<camelCase>`.
        group: Command group (the module name).
        handler: The decorated function.
        params_type: Dataclass of the parameters.
        result_type: Dataclass of the result.
        lane: Whether requests may name a lane (`<method>` or `<method>:<suffix>`). A new
            request in a lane supersedes queued and running requests of the same lane.
        caller: Who may call it: the renderer, only the main process (methods that take
            file paths), or only tests (enabled by `M2C_DEBUG_COMMANDS=1`).
        exclusive: Long-running method; while it runs, lane requests are answered with
            `kernel.busy` instead of queueing behind it.
        light: Runs before the heavy imports (numpy, scipy, trimesh, OCP) are ready.
    """

    method: str
    group: str
    handler: Handler
    params_type: type
    result_type: type
    lane: bool
    caller: Caller
    exclusive: bool
    light: bool


_REGISTRY: dict[str, CommandSpec] = {}


def command(
    method: str,
    *,
    lane: bool = False,
    caller: Caller = "renderer",
    exclusive: bool = False,
    light: bool = False,
) -> Callable[[Handler], Handler]:
    """Register a protocol method implemented by the decorated function."""

    def register(handler: Handler) -> Handler:
        group = handler.__module__.rsplit(".", 1)[-1]
        if not method.startswith(f"{group}."):
            raise ValueError(f"method {method!r} must start with its module group {group!r}")
        if method in _REGISTRY:
            raise ValueError(f"method {method!r} is registered twice")
        hints = get_type_hints(handler)
        params_type, result_type = hints.get("params"), hints.get("return")
        for kind, annotation in (("params", params_type), ("result", result_type)):
            if not (isinstance(annotation, type) and is_dataclass(annotation)):
                raise TypeError(f"{method}: the {kind} type must be a dataclass")
        assert params_type is not None and result_type is not None
        _REGISTRY[method] = CommandSpec(
            method=method,
            group=group,
            handler=handler,
            params_type=params_type,
            result_type=result_type,
            lane=lane,
            caller=caller,
            exclusive=exclusive,
            light=light,
        )
        return handler

    return register


def load_commands() -> Mapping[str, CommandSpec]:
    """Import every module of `m2c_kernel.commands` and return the registry."""
    package = importlib.import_module("m2c_kernel.commands")
    for module in pkgutil.iter_modules(package.__path__):
        importlib.import_module(f"{package.__name__}.{module.name}")
    return dict(_REGISTRY)


def lane_is_valid(spec: CommandSpec, lane: str) -> bool:
    """A lane is the method name, optionally followed by `:` and a suffix (a tool id)."""
    return spec.lane and (lane == spec.method or lane.startswith(f"{spec.method}:"))
