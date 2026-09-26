"""Conversion between typed Python values and the JSON + buffer wire format.

Wire types are frozen dataclasses with fully annotated fields. The encoder and
decoder walk the annotations, so no handler converts keys or checks shapes by
hand:

- Field names are snake_case in Python and camelCase on the wire. Dictionary
  keys are data and are never converted.
- Arrays are declared with the aliases below (`U32Array`, `F32Array`, ...).
  They travel as binary buffers referenced from the JSON as
  `{"$buf": index, "dtype": "uint32", "shape": [n]}`; a numpy array in a field
  that is not declared as an array is a programming error.
- Unions of dataclasses need a `type: Literal[...]` discriminator field.
- Non-finite floats are sent as `null`; fields that can carry them are declared
  `float | None`.
- `Annotated[int, Range(3, 64)]` declares limits that the decoder enforces and
  codegen exports to TypeScript.

The same annotations drive `m2c_kernel.protocol.codegen`.
"""

from __future__ import annotations

import dataclasses
import math
import types
from collections.abc import Sequence
from enum import Enum
from functools import cache
from typing import (
    Annotated,
    Any,
    Literal,
    TypeAliasType,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

import numpy as np
import numpy.typing as npt

from m2c_kernel.codes.kernel import ErrorCode
from m2c_kernel.protocol.errors import KernelError

type DType = Literal["uint8", "uint16", "uint32", "int32", "float32", "float64"]


@dataclasses.dataclass(frozen=True)
class WireArray:
    """Marks an array field; the value travels as a binary buffer."""

    dtype: DType


@dataclasses.dataclass(frozen=True)
class Brand:
    """Marks a string with a specific meaning (a branded string type in TypeScript)."""

    name: str


@dataclasses.dataclass(frozen=True)
class Range:
    """Inclusive numeric limits of a field, enforced when decoding parameters."""

    min: float | None = None
    max: float | None = None


type U8Array = Annotated[npt.NDArray[np.uint8], WireArray("uint8")]
type U16Array = Annotated[npt.NDArray[np.uint16], WireArray("uint16")]
type U32Array = Annotated[npt.NDArray[np.uint32], WireArray("uint32")]
type I32Array = Annotated[npt.NDArray[np.int32], WireArray("int32")]
type F32Array = Annotated[npt.NDArray[np.float32], WireArray("float32")]
type F64Array = Annotated[npt.NDArray[np.float64], WireArray("float64")]
type BlobRef = Annotated[str, Brand("BlobRef")]
type JsonValue = bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None


@dataclasses.dataclass(frozen=True)
class RawObject:
    """A JSON object whose schema belongs to the receiving module.

    Used for feature parameters: `doc.apply` does not know the parameter types of
    every feature, so it passes the object on and the feature type decodes it.
    Buffers referenced inside stay reachable through `buffers`.
    """

    json: dict[str, Any]
    buffers: tuple[memoryview, ...] = ()


_UNION_ORIGINS = (Union, types.UnionType)
_NONE = type(None)
_DTYPES: dict[str, np.dtype[Any]] = {
    name: np.dtype(name) for name in ("uint8", "uint16", "uint32", "int32", "float32", "float64")
}


@cache
def to_camel(name: str) -> str:
    """Convert a snake_case field name to camelCase (`half_angle_deg` -> `halfAngleDeg`)."""
    head, *rest = name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


@dataclasses.dataclass(frozen=True)
class FieldInfo:
    name: str
    key: str
    annotation: Any
    has_default: bool


@cache
def fields_of(cls: type) -> tuple[FieldInfo, ...]:
    """Wire fields of a dataclass, with resolved annotations."""
    hints = get_type_hints(cls, include_extras=True)
    return tuple(
        FieldInfo(
            name=field.name,
            key=to_camel(field.name),
            annotation=hints[field.name],
            has_default=field.default is not dataclasses.MISSING
            or field.default_factory is not dataclasses.MISSING,
        )
        for field in dataclasses.fields(cls)
        if field.init
    )


def unwrap(annotation: Any) -> tuple[Any, tuple[Any, ...]]:
    """Resolve type aliases and `Annotated`, returning the base type and all metadata."""
    metadata: tuple[Any, ...] = ()
    while True:
        if annotation is JsonValue:
            return annotation, metadata
        if isinstance(annotation, TypeAliasType):
            annotation = annotation.__value__
            continue
        if get_origin(annotation) is Annotated:
            base, *extra = get_args(annotation)
            metadata += tuple(extra)
            annotation = base
            continue
        return annotation, metadata


def is_union(annotation: Any) -> bool:
    return get_origin(annotation) in _UNION_ORIGINS


def discriminator_of(cls: type) -> tuple[str, ...]:
    """Values of the `type: Literal[...]` field of a dataclass, or () if it has none."""
    for info in fields_of(cls):
        if info.name == "type":
            base, _ = unwrap(info.annotation)
            if get_origin(base) is Literal:
                return tuple(str(value) for value in get_args(base))
    return ()


def _metadata_of[T](metadata: tuple[Any, ...], kind: type[T]) -> T | None:
    return next((item for item in metadata if isinstance(item, kind)), None)


class _Encoder:
    def __init__(self, allow_buffers: bool) -> None:
        self.allow_buffers = allow_buffers
        self.buffers: list[np.ndarray] = []

    def encode(self, value: Any, annotation: Any) -> Any:
        base, metadata = unwrap(annotation)
        array = _metadata_of(metadata, WireArray)
        if array is not None:
            return self._array(value, array)
        if base is JsonValue:
            return _checked_json(value)
        if is_union(base):
            return self._union(value, base)
        origin = get_origin(base)
        if origin is Literal:
            return value
        if origin in (list, tuple):
            return self._sequence(value, base)
        if origin is dict:
            value_type = get_args(base)[1]
            return {str(key): self.encode(item, value_type) for key, item in value.items()}
        if isinstance(base, type):
            return self._simple(value, base)
        raise TypeError(f"unsupported wire type {annotation!r}")

    def _simple(self, value: Any, base: type) -> Any:
        if base is RawObject:
            return _checked_json(value.json)
        if dataclasses.is_dataclass(base):
            return {
                info.key: self.encode(getattr(value, info.name), info.annotation)
                for info in fields_of(base)
            }
        if issubclass(base, Enum):
            return value.value
        if base is bool:
            return bool(value)
        if base is int:
            return int(value)
        if base is float:
            number = float(value)
            return number if math.isfinite(number) else None
        if base is str:
            return str(value)
        if base is _NONE:
            return None
        raise TypeError(f"unsupported wire type {base!r}")

    def _union(self, value: Any, base: Any) -> Any:
        options = [option for option in get_args(base) if option is not _NONE]
        if value is None:
            if len(options) == len(get_args(base)):
                raise TypeError("None is not allowed here")
            return None
        if len(options) == 1:
            return self.encode(value, options[0])
        for option in options:
            option_base, _ = unwrap(option)
            if isinstance(option_base, type) and isinstance(value, option_base):
                return self.encode(value, option)
        raise TypeError(f"{type(value).__name__} does not match {base!r}")

    def _sequence(self, value: Any, base: Any) -> list[Any]:
        args = get_args(base)
        if get_origin(base) is tuple and not (len(args) == 2 and args[1] is Ellipsis):
            return [
                self.encode(item, item_type) for item, item_type in zip(value, args, strict=True)
            ]
        return [self.encode(item, args[0]) for item in value]

    def _array(self, value: Any, spec: WireArray) -> dict[str, Any]:
        if not self.allow_buffers:
            raise TypeError("arrays cannot be stored as JSON; store them as blobs")
        if not isinstance(value, np.ndarray):
            raise TypeError(f"expected a numpy array, got {type(value).__name__}")
        array = np.ascontiguousarray(value, dtype=_DTYPES[spec.dtype])
        self.buffers.append(array)
        return {"$buf": len(self.buffers) - 1, "dtype": spec.dtype, "shape": list(array.shape)}


class _Decoder:
    def __init__(self, buffers: Sequence[memoryview]) -> None:
        self.buffers = buffers

    def decode(self, value: Any, annotation: Any, path: str) -> Any:
        base, metadata = unwrap(annotation)
        array = _metadata_of(metadata, WireArray)
        if array is not None:
            return self._array(value, array, path)
        result = self._decode_base(value, base, path)
        limits = _metadata_of(metadata, Range)
        if limits is not None and result is not None:
            if limits.min is not None and result < limits.min:
                raise _invalid(path, f"must be at least {limits.min}")
            if limits.max is not None and result > limits.max:
                raise _invalid(path, f"must be at most {limits.max}")
        return result

    def _decode_base(self, value: Any, base: Any, path: str) -> Any:
        if base is JsonValue:
            return _checked_json(value, path)
        if is_union(base):
            return self._union(value, base, path)
        origin = get_origin(base)
        if origin is Literal:
            if value not in get_args(base):
                raise _invalid(path, f"must be one of {list(get_args(base))}")
            return value
        if origin in (list, tuple):
            return self._sequence(value, base, path)
        if origin is dict:
            if not isinstance(value, dict):
                raise _invalid(path, "must be an object")
            value_type = get_args(base)[1]
            return {
                key: self.decode(item, value_type, f"{path}.{key}") for key, item in value.items()
            }
        if isinstance(base, type):
            return self._simple(value, base, path)
        raise TypeError(f"unsupported wire type {base!r}")

    def _simple(self, value: Any, base: type, path: str) -> Any:
        if base is RawObject:
            if not isinstance(value, dict):
                raise _invalid(path, "must be an object")
            return RawObject(value, tuple(self.buffers))
        if dataclasses.is_dataclass(base):
            return self._dataclass(value, base, path)
        if issubclass(base, Enum):
            try:
                return base(value)
            except ValueError:
                raise _invalid(path, f"unknown value {value!r}") from None
        if base is bool:
            if not isinstance(value, bool):
                raise _invalid(path, "must be a boolean")
            return value
        if base is int:
            if isinstance(value, bool) or not isinstance(value, int):
                raise _invalid(path, "must be an integer")
            return value
        if base is float:
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise _invalid(path, "must be a number")
            return float(value)
        if base is str:
            if not isinstance(value, str):
                raise _invalid(path, "must be a string")
            return value
        if base is _NONE:
            if value is not None:
                raise _invalid(path, "must be null")
            return None
        raise TypeError(f"unsupported wire type {base!r}")

    def _dataclass(self, value: Any, cls: type, path: str) -> Any:
        if not isinstance(value, dict):
            raise _invalid(path, "must be an object")
        infos = fields_of(cls)
        known = {info.key for info in infos}
        unknown = [key for key in value if key not in known]
        if unknown:
            raise _invalid(_join(path, unknown[0]), "is not a known field")
        kwargs: dict[str, Any] = {}
        for info in infos:
            if info.key in value:
                kwargs[info.name] = self.decode(
                    value[info.key], info.annotation, _join(path, info.key)
                )
            elif not info.has_default:
                raise _invalid(_join(path, info.key), "is required")
        return cls(**kwargs)

    def _union(self, value: Any, base: Any, path: str) -> Any:
        options = [option for option in get_args(base) if option is not _NONE]
        if value is None:
            if len(options) == len(get_args(base)):
                raise _invalid(path, "must not be null")
            return None
        if len(options) == 1:
            return self.decode(value, options[0], path)
        tagged = [option for option in options if _is_tagged_dataclass(option)]
        if tagged:
            tag = value.get("type") if isinstance(value, dict) else None
            for option in tagged:
                if tag in discriminator_of(unwrap(option)[0]):
                    return self.decode(value, option, path)
            raise _invalid(_join(path, "type"), f"unknown variant {tag!r}")
        for option in options:
            try:
                return self.decode(value, option, path)
            except KernelError:
                continue
        raise _invalid(path, "has an unexpected type")

    def _sequence(self, value: Any, base: Any, path: str) -> Any:
        if not isinstance(value, list):
            raise _invalid(path, "must be an array")
        args = get_args(base)
        if get_origin(base) is tuple and not (len(args) == 2 and args[1] is Ellipsis):
            if len(value) != len(args):
                raise _invalid(path, f"must have {len(args)} elements")
            return tuple(
                self.decode(item, item_type, f"{path}[{index}]")
                for index, (item, item_type) in enumerate(zip(value, args, strict=True))
            )
        items = [self.decode(item, args[0], f"{path}[{index}]") for index, item in enumerate(value)]
        return tuple(items) if get_origin(base) is tuple else items

    def _array(self, value: Any, spec: WireArray, path: str) -> np.ndarray:
        if not isinstance(value, dict) or not isinstance(value.get("$buf"), int):
            raise _invalid(path, "must be a buffer reference")
        index, dtype, shape = value["$buf"], value.get("dtype"), value.get("shape")
        if dtype != spec.dtype:
            raise _invalid(path, f"must have dtype {spec.dtype}, got {dtype}")
        if not 0 <= index < len(self.buffers):
            raise _invalid(path, f"references missing buffer {index}")
        if not isinstance(shape, list) or not all(isinstance(n, int) and n >= 0 for n in shape):
            raise _invalid(path, "has an invalid shape")
        array = np.frombuffer(self.buffers[index], dtype=_DTYPES[spec.dtype])
        if array.size != math.prod(shape):
            raise _invalid(path, f"shape {shape} does not match {array.size} elements")
        return array.reshape(shape)


def _is_tagged_dataclass(annotation: Any) -> bool:
    base, _ = unwrap(annotation)
    return (
        isinstance(base, type) and dataclasses.is_dataclass(base) and bool(discriminator_of(base))
    )


def _join(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def _invalid(path: str, message: str) -> KernelError:
    return KernelError(ErrorCode.INVALID_PARAMS, {"field": path}, details=f"{path}: {message}")


def _checked_json(value: Any, path: str = "") -> Any:
    """Return `value` if it is plain JSON; buffer references are not allowed inside."""
    if value is None or isinstance(value, bool | str):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, list | tuple):
        return [_checked_json(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, dict):
        if "$buf" in value:
            raise _invalid(path, "buffers are not allowed in plain JSON values")
        return {str(key): _checked_json(item, _join(path, str(key))) for key, item in value.items()}
    raise _invalid(path, f"{type(value).__name__} is not a JSON value")


def to_wire(value: Any, annotation: Any) -> tuple[Any, list[np.ndarray]]:
    """Encode a value into JSON-compatible data plus the buffers it references."""
    encoder = _Encoder(allow_buffers=True)
    return encoder.encode(value, annotation), encoder.buffers


def to_json(value: Any, annotation: Any) -> Any:
    """Encode a value that must not contain arrays (persisted documents, events)."""
    return _Encoder(allow_buffers=False).encode(value, annotation)


def from_wire[T](value: Any, annotation: type[T], buffers: Sequence[memoryview] = ()) -> T:
    """Decode wire data into `annotation`; raises `KernelError(kernel.invalidParams)`."""
    return cast(T, _Decoder(buffers).decode(value, annotation, ""))


def from_json[T](value: Any, annotation: type[T]) -> T:
    """Decode JSON data without buffers into `annotation`."""
    return from_wire(value, annotation, ())
