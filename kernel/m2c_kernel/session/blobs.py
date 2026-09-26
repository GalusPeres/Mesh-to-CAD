"""Content-addressed array storage shared by all revisions of a session."""

from __future__ import annotations

import hashlib
import io
from collections import OrderedDict
from pathlib import Path

import numpy as np

from m2c_kernel.protocol.wire import BlobRef
from m2c_kernel.session.fs import atomic_write_bytes, remove_quietly

_PREFIX = "blob:"
_DEFAULT_CACHE_BYTES = 768 << 20


def blob_digest(array: np.ndarray) -> str:
    """SHA-256 over dtype, shape and bytes: equal arrays get equal references."""
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(repr(array.shape).encode("ascii"))
    digest.update(memoryview(np.ascontiguousarray(array)).cast("B"))
    return digest.hexdigest()


class BlobStore:
    """Arrays stored once as `blobs/<sha256>.npy` and referenced as `blob:<sha256>`.

    Blobs are read fully into memory instead of being memory-mapped: Windows
    cannot delete a mapped file, which would block garbage collection and the
    removal of the session directory. Recently used arrays stay in an LRU cache.
    Returned arrays are read-only.
    """

    def __init__(self, directory: Path, cache_bytes: int = _DEFAULT_CACHE_BYTES) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._cache_bytes = cache_bytes
        self._cached_bytes = 0

    def put(self, array: np.ndarray) -> BlobRef:
        array = np.ascontiguousarray(array)
        digest = blob_digest(array)
        path = self._path(digest)
        if not path.exists():
            buffer = io.BytesIO()
            np.save(buffer, array, allow_pickle=False)
            atomic_write_bytes(path, buffer.getvalue())
        stored = array.copy() if array.flags.writeable else array
        stored.flags.writeable = False
        self._remember(digest, stored)
        return f"{_PREFIX}{digest}"

    def get(self, ref: BlobRef) -> np.ndarray:
        digest = self._digest(ref)
        cached = self._cache.get(digest)
        if cached is not None:
            self._cache.move_to_end(digest)
            return cached
        array: np.ndarray = np.load(self._path(digest), allow_pickle=False)
        array.flags.writeable = False
        self._remember(digest, array)
        return array

    def contains(self, ref: BlobRef) -> bool:
        return self._path(self._digest(ref)).exists()

    def collect(self, referenced: set[BlobRef]) -> int:
        """Delete blobs that no kept revision references. Returns the number deleted."""
        keep = {self._digest(ref) for ref in referenced}
        removed = 0
        for path in self.directory.glob("*.npy"):
            digest = path.stem
            if digest in keep:
                continue
            self._forget(digest)
            if remove_quietly(path):
                removed += 1
        return removed

    def _path(self, digest: str) -> Path:
        return self.directory / f"{digest}.npy"

    @staticmethod
    def _digest(ref: BlobRef) -> str:
        if not ref.startswith(_PREFIX):
            raise ValueError(f"not a blob reference: {ref!r}")
        return ref[len(_PREFIX) :]

    def _remember(self, digest: str, array: np.ndarray) -> None:
        if digest in self._cache:
            self._cache.move_to_end(digest)
            return
        self._cache[digest] = array
        self._cached_bytes += array.nbytes
        while self._cached_bytes > self._cache_bytes and len(self._cache) > 1:
            _, evicted = self._cache.popitem(last=False)
            self._cached_bytes -= evicted.nbytes

    def _forget(self, digest: str) -> None:
        array = self._cache.pop(digest, None)
        if array is not None:
            self._cached_bytes -= array.nbytes
