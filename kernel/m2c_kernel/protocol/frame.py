"""Length-prefixed frames: a JSON header followed by aligned binary buffers.

Layout (all integers little-endian):

| Offset | Size | Content                                              |
|--------|------|------------------------------------------------------|
| 0      | 4    | magic `M2CF`                                         |
| 4      | 4    | uint32 header length H (UTF-8 JSON)                  |
| 8      | 4    | uint32 binary length B (all buffers incl. padding)   |
| 12     | H    | JSON header; `buffers` lists the byte length of each |
| 12 + H | 0-7  | zero padding to an 8-byte boundary                   |
| ...    | B    | buffers, each padded to a multiple of 8 bytes        |

The same test vectors are checked on the TypeScript side
(`src/shared/protocol/frame.ts`) through `tests/fixtures/frame-vectors.json`.
"""

from __future__ import annotations

import json
import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from m2c_kernel.limits import MAX_FRAME_BYTES

MAGIC = b"M2CF"
ALIGNMENT = 8
_PREFIX = struct.Struct("<4sII")

type BufferLike = bytes | bytearray | memoryview | np.ndarray


class ReadableStream(Protocol):
    def readinto(self, buffer: memoryview, /) -> int | None: ...


class WritableStream(Protocol):
    def write(self, data: memoryview, /) -> object: ...

    def flush(self) -> object: ...


class FrameError(Exception):
    """The byte stream does not contain a valid frame; the connection must be closed."""


@dataclass(frozen=True)
class Frame:
    header: dict[str, Any]
    buffers: list[memoryview]


def padding(length: int) -> int:
    """Bytes needed to pad `length` to the frame alignment."""
    return -length % ALIGNMENT


def _as_bytes_view(buffer: BufferLike) -> memoryview:
    if isinstance(buffer, np.ndarray):
        buffer = np.ascontiguousarray(buffer)
    return memoryview(buffer).cast("B")


def encode_frame(header: Mapping[str, Any], buffers: Sequence[BufferLike] = ()) -> list[memoryview]:
    """Return the chunks of one frame; writing them in order produces the frame.

    The header's `buffers` entry is set here from the actual buffer sizes.
    Raises `FrameError` when the frame would exceed `MAX_FRAME_BYTES` and
    `ValueError` when the header contains non-finite floats.
    """
    views = [_as_bytes_view(buffer) for buffer in buffers]
    full_header = {**header, "buffers": [view.nbytes for view in views]}
    head = json.dumps(full_header, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    head_bytes = head.encode("utf-8")
    head_pad = padding(_PREFIX.size + len(head_bytes))
    body_length = sum(view.nbytes + padding(view.nbytes) for view in views)
    total = _PREFIX.size + len(head_bytes) + head_pad + body_length
    if total > MAX_FRAME_BYTES:
        raise FrameError(f"frame of {total} bytes exceeds the limit of {MAX_FRAME_BYTES}")

    chunks = [memoryview(_PREFIX.pack(MAGIC, len(head_bytes), body_length)), memoryview(head_bytes)]
    if head_pad:
        chunks.append(memoryview(bytes(head_pad)))
    for view in views:
        chunks.append(view)
        if pad := padding(view.nbytes):
            chunks.append(memoryview(bytes(pad)))
    return chunks


def encode_frame_bytes(header: Mapping[str, Any], buffers: Sequence[BufferLike] = ()) -> bytes:
    """Encode a whole frame into one bytes object (tests and small messages)."""
    return b"".join(bytes(chunk) for chunk in encode_frame(header, buffers))


def _read_exact(stream: ReadableStream, size: int) -> bytearray | None:
    """Read exactly `size` bytes; None at a clean end of stream before the first byte."""
    data = bytearray(size)
    view = memoryview(data)
    filled = 0
    while filled < size:
        count = stream.readinto(view[filled:])
        if not count:
            if filled == 0:
                return None
            raise FrameError(f"stream ended after {filled} of {size} bytes")
        filled += count
    return data


def read_frame(stream: ReadableStream) -> Frame | None:
    """Read the next frame from a binary stream; None at a clean end of stream."""
    prefix = _read_exact(stream, _PREFIX.size)
    if prefix is None:
        return None
    magic, header_length, body_length = _PREFIX.unpack(prefix)
    if magic != MAGIC:
        raise FrameError(f"bad magic {bytes(magic)!r}")
    head_pad = padding(_PREFIX.size + header_length)
    if _PREFIX.size + header_length + head_pad + body_length > MAX_FRAME_BYTES:
        raise FrameError("frame exceeds the size limit")

    head = _read_exact(stream, header_length + head_pad) if header_length + head_pad else b""
    if head is None:
        raise FrameError("stream ended inside a frame header")
    header = json.loads(bytes(head[:header_length]).decode("utf-8"))
    if not isinstance(header, dict):
        raise FrameError("frame header is not a JSON object")

    body = _read_exact(stream, body_length) if body_length else bytearray()
    if body is None:
        raise FrameError("stream ended inside a frame body")
    return Frame(header, split_buffers(header, memoryview(body)))


def split_buffers(header: Mapping[str, Any], body: memoryview) -> list[memoryview]:
    """Slice the body into the buffers listed in the header."""
    sizes = header.get("buffers", [])
    if not isinstance(sizes, list) or not all(isinstance(s, int) and s >= 0 for s in sizes):
        raise FrameError("header field 'buffers' must be a list of sizes")
    buffers = []
    offset = 0
    for size in sizes:
        if offset + size > len(body):
            raise FrameError("buffer sizes exceed the frame body")
        buffers.append(body[offset : offset + size])
        offset += size + padding(size)
    return buffers


def write_frame(
    stream: WritableStream, header: Mapping[str, Any], buffers: Sequence[BufferLike] = ()
) -> None:
    """Encode and write one frame, then flush."""
    for chunk in encode_frame(header, buffers):
        stream.write(chunk)
    stream.flush()
