from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pytest

from m2c_kernel.protocol.frame import (
    ALIGNMENT,
    FrameError,
    encode_frame_bytes,
    read_frame,
)

VECTORS = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "frame-vectors.json"


@pytest.mark.parametrize("sizes", [[], [0], [1], [7], [8], [9], [3, 17, 64]])
def test_round_trip_keeps_header_and_buffers(sizes: list[int]) -> None:
    rng = np.random.default_rng(len(sizes))
    buffers = [rng.integers(0, 255, size, dtype=np.uint8).tobytes() for size in sizes]
    header = {"type": "request", "id": 7, "method": "debug.echoBuffers", "params": {"ä": "ü"}}

    data = encode_frame_bytes(header, buffers)
    frame = read_frame(io.BytesIO(data))

    assert frame is not None
    assert {key: frame.header[key] for key in header} == header
    assert frame.header["buffers"] == sizes
    assert [bytes(buffer) for buffer in frame.buffers] == buffers
    assert len(data) % ALIGNMENT == 0


def test_every_buffer_starts_on_the_alignment_boundary() -> None:
    data = encode_frame_bytes({"type": "event"}, [b"x" * 3, b"y" * 5])
    frame = read_frame(io.BytesIO(data))
    assert frame is not None
    start = data.index(b"xxx")
    assert start % ALIGNMENT == 0
    assert data.index(b"yyyyy") % ALIGNMENT == 0


def test_numpy_arrays_are_written_without_conversion() -> None:
    values = np.arange(10, dtype=np.float32)
    frame = read_frame(io.BytesIO(encode_frame_bytes({"type": "event"}, [values])))
    assert frame is not None
    np.testing.assert_array_equal(np.frombuffer(frame.buffers[0], np.float32), values)


def test_end_of_stream_before_a_frame_is_clean() -> None:
    assert read_frame(io.BytesIO(b"")) is None


def test_truncated_frame_is_an_error() -> None:
    data = encode_frame_bytes({"type": "event"}, [b"payload"])
    with pytest.raises(FrameError):
        read_frame(io.BytesIO(data[:-3]))


def test_bad_magic_is_an_error() -> None:
    data = bytearray(encode_frame_bytes({"type": "event"}))
    data[0:4] = b"XXXX"
    with pytest.raises(FrameError):
        read_frame(io.BytesIO(bytes(data)))


def test_non_finite_numbers_are_rejected_in_headers() -> None:
    with pytest.raises(ValueError):
        encode_frame_bytes({"value": float("nan")})


def test_shared_vectors_match_the_typescript_encoder() -> None:
    vectors = json.loads(VECTORS.read_text(encoding="utf-8"))
    assert vectors, "no frame test vectors"
    for vector in vectors:
        buffers = [bytes.fromhex(item) for item in vector["buffers"]]
        assert encode_frame_bytes(vector["header"], buffers).hex() == vector["frame"], vector[
            "name"
        ]
