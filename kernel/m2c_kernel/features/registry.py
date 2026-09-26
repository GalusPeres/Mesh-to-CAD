"""Registry of feature types.

A feature type is a class in a module of `m2c_kernel.features.types`:

    @feature_type("extrude", params=ExtrudeParams, reads=ReadSet(settings=("tolerance",)))
    class Extrude:
        @staticmethod
        def references(params: ExtrudeParams) -> Refs: ...

        @staticmethod
        def evaluate(ctx: EvalContext, params: ExtrudeParams) -> FeatureOutput: ...

`reads` declares what the result depends on besides the referenced features;
it is part of the result key, so a feature is re-evaluated exactly when one of
its inputs changes. Types whose input differs from the stored parameters (a fit
receives triangles as a `U32Array` but stores them as a blob) pass `input=`
and a `store=` function.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, is_dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from m2c_kernel.document.rebuild import EvalContext
    from m2c_kernel.document.results import FeatureOutput
    from m2c_kernel.session.blobs import BlobStore


@dataclass(frozen=True)
class ReadSet:
    """Inputs of a feature besides the features and bodies it references.

    Attributes:
        mesh: Reads the aligned scan (vertices, faces, normals, face sets).
        alignment: Reads the alignment matrix without reading the scan.
        settings: Names of `DocumentSettings` fields it reads.
    """

    mesh: bool = False
    alignment: bool = False
    settings: tuple[str, ...] = ()


@dataclass(frozen=True)
class Refs:
    """Features and bodies a feature reads; they must come earlier in the history."""

    features: tuple[str, ...] = ()
    bodies: tuple[str, ...] = ()


type ReferencesFn = Callable[[Any], Refs]
type EvaluateFn = Callable[["EvalContext", Any], "FeatureOutput"]
type StoreFn = Callable[[Any, "BlobStore"], Any]


@dataclass(frozen=True)
class FeatureTypeSpec:
    type_id: str
    params_type: type
    input_type: type
    reads: ReadSet
    references: ReferencesFn
    evaluate: EvaluateFn
    store: StoreFn
    module: str


_REGISTRY: dict[str, FeatureTypeSpec] = {}
_READS_NOTHING = ReadSet()


def _identity(value: Any, _blobs: BlobStore) -> Any:
    return value


def feature_type(
    type_id: str,
    *,
    params: type,
    reads: ReadSet = _READS_NOTHING,
    input: type | None = None,  # noqa: A002 (the natural name in this API)
    store: StoreFn | None = None,
) -> Callable[[type], type]:
    """Register the decorated class as the implementation of feature type `type_id`."""
    if input is not None and store is None:
        raise TypeError(f"{type_id}: a separate input type needs a store function")
    for kind, annotation in (("params", params), ("input", input or params)):
        if not is_dataclass(annotation):
            raise TypeError(f"{type_id}: {kind} must be a dataclass")

    def register(cls: type) -> type:
        register_feature_type(
            FeatureTypeSpec(
                type_id=type_id,
                params_type=params,
                input_type=input or params,
                reads=reads,
                references=cls.references,  # type: ignore[attr-defined]
                evaluate=cls.evaluate,  # type: ignore[attr-defined]
                store=store or _identity,
                module=cls.__module__,
            )
        )
        return cls

    return register


def register_feature_type(spec: FeatureTypeSpec) -> None:
    if spec.type_id in _REGISTRY and _REGISTRY[spec.type_id].module != spec.module:
        raise ValueError(f"feature type {spec.type_id!r} is registered twice")
    _REGISTRY[spec.type_id] = spec


@contextmanager
def temporary_feature_type(spec: FeatureTypeSpec) -> Iterator[FeatureTypeSpec]:
    """Register a feature type for the duration of a test."""
    previous = _REGISTRY.get(spec.type_id)
    _REGISTRY[spec.type_id] = spec
    try:
        yield spec
    finally:
        if previous is None:
            _REGISTRY.pop(spec.type_id, None)
        else:
            _REGISTRY[spec.type_id] = previous


def load_feature_types() -> Mapping[str, FeatureTypeSpec]:
    """Import every module of `m2c_kernel.features.types` and return the registry."""
    package = importlib.import_module("m2c_kernel.features.types")
    for module in pkgutil.iter_modules(package.__path__):
        importlib.import_module(f"{package.__name__}.{module.name}")
    return _REGISTRY


def feature_types() -> Mapping[str, FeatureTypeSpec]:
    """The registry, including types registered by tests."""
    return _REGISTRY
