from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Literal

import numpy as np
import pytest

from m2c_kernel.document.ops import AddFeature, DocOp, SetSuppressed
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.wire import (
    F32Array,
    Range,
    RawObject,
    U32Array,
    from_json,
    from_wire,
    to_camel,
    to_json,
    to_wire,
)


@dataclass(frozen=True)
class Inner:
    half_angle_deg: float
    tags: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Outer:
    name: str
    inner: Inner
    count: Annotated[int, Range(1, 10)] = 3
    mode: Literal["a", "b"] = "a"
    note: str | None = None


@dataclass(frozen=True)
class WithArrays:
    faces: U32Array
    values: F32Array


def test_snake_case_becomes_camel_case() -> None:
    assert to_camel("half_angle_deg") == "halfAngleDeg"
    assert to_camel("id") == "id"


def test_dataclasses_round_trip_with_camel_case_keys() -> None:
    value = Outer(name="x", inner=Inner(half_angle_deg=45.0, tags={"snake_key": 1}), count=4)
    data = to_json(value, Outer)
    assert data == {
        "name": "x",
        "inner": {"halfAngleDeg": 45.0, "tags": {"snake_key": 1}},
        "count": 4,
        "mode": "a",
        "note": None,
    }
    assert from_json(data, Outer) == value


def test_defaults_fill_missing_fields() -> None:
    decoded = from_json({"name": "x", "inner": {"halfAngleDeg": 1}}, Outer)
    assert decoded.count == 3
    assert decoded.inner.half_angle_deg == 1.0


@pytest.mark.parametrize(
    ("data", "field_path"),
    [
        ({"inner": {"halfAngleDeg": 1}}, "name"),
        ({"name": "x", "inner": {"halfAngleDeg": "1"}}, "inner.halfAngleDeg"),
        ({"name": "x", "inner": {"halfAngleDeg": 1}, "count": 11}, "count"),
        ({"name": "x", "inner": {"halfAngleDeg": 1}, "mode": "c"}, "mode"),
        ({"name": "x", "inner": {"halfAngleDeg": 1}, "extra": 1}, "extra"),
        ({"name": True, "inner": {"halfAngleDeg": 1}}, "name"),
    ],
)
def test_invalid_input_names_the_field(data: dict[str, object], field_path: str) -> None:
    with pytest.raises(KernelError) as caught:
        from_json(data, Outer)
    assert caught.value.code == "kernel.invalidParams"
    assert caught.value.params["field"] == field_path


def test_unions_are_decoded_by_their_type_field() -> None:
    ops = from_json(
        [
            {"type": "setSuppressed", "id": "f1", "suppressed": True},
            {"type": "addFeature", "feature": {"type": "extrude", "params": {"sketch": "f2"}}},
        ],
        list[DocOp],
    )
    assert isinstance(ops[0], SetSuppressed)
    assert isinstance(ops[1], AddFeature)
    assert isinstance(ops[1].feature.params, RawObject)
    assert ops[1].feature.params.json == {"sketch": "f2"}


def test_unknown_union_variant_is_invalid() -> None:
    with pytest.raises(KernelError) as caught:
        from_json([{"type": "explode"}], list[DocOp])
    assert caught.value.params["field"] == "[0].type"


def test_arrays_travel_as_buffers_without_copies() -> None:
    faces = np.arange(12, dtype=np.uint32)
    values = np.linspace(0, 1, 4, dtype=np.float32)
    data, buffers = to_wire(WithArrays(faces, values), WithArrays)
    assert data["faces"] == {"$buf": 0, "dtype": "uint32", "shape": [12]}

    views = [memoryview(buffer).cast("B") for buffer in buffers]
    decoded = from_wire(data, WithArrays, views)
    np.testing.assert_array_equal(decoded.faces, faces)
    assert np.shares_memory(decoded.faces, np.frombuffer(views[0], np.uint32))


def test_array_dtype_must_match_the_declaration() -> None:
    data = {
        "faces": {"$buf": 0, "dtype": "int32", "shape": [1]},
        "values": {"$buf": 0, "dtype": "float32", "shape": [1]},
    }
    with pytest.raises(KernelError) as caught:
        from_wire(data, WithArrays, [memoryview(bytes(4))])
    assert caught.value.params["field"] == "faces"


def test_arrays_cannot_be_stored_as_json() -> None:
    with pytest.raises(TypeError):
        to_json(WithArrays(np.zeros(1, np.uint32), np.zeros(1, np.float32)), WithArrays)


def test_non_finite_floats_become_null() -> None:
    assert to_json(Inner(half_angle_deg=float("nan")), Inner)["halfAngleDeg"] is None
