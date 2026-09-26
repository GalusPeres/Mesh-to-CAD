from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from m2c_kernel.document.snapshot import DocumentSnapshot
from m2c_kernel.protocol.wire import to_json
from m2c_kernel.session.jobs import JobContext
from m2c_kernel.session.session import Session
from tests.kernel_process import KernelProcess
from tests.synthetic import sphere_scan, write_binary_stl


class RecordingEvents:
    """Collects events a session emits (stands in for the protocol server)."""

    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []

    def emit_event(self, event: str, data: object, buffers: object = ()) -> None:
        self.events.append((event, data))


@pytest.fixture
def events() -> RecordingEvents:
    return RecordingEvents()


@pytest.fixture
def session(tmp_path: Path, events: RecordingEvents) -> Iterator[Session]:
    opened = Session.open(tmp_path / "session", events)
    yield opened
    opened.close()


@pytest.fixture
def job(session: Session) -> JobContext:
    return JobContext.detached(session)


@pytest.fixture
def kernel(tmp_path: Path) -> Iterator[KernelProcess]:
    process = KernelProcess(tmp_path / "session")
    ready = process.next_event("ready", timeout=30)
    assert ready["data"]["protocolVersion"] >= 1
    # Waits until the heavy libraries are loaded, so timing assertions measure the request.
    assert process.call("system.info").ok
    yield process
    process.stop()


@pytest.fixture(scope="session")
def sphere_stl(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A closed noisy sphere, R20, 5120 faces, as binary STL."""
    vertices, faces = sphere_scan(radius=20.0, subdivisions=4, sigma=0.02)
    return write_binary_stl(tmp_path_factory.mktemp("meshes") / "sphere.stl", vertices, faces)


def snapshot_json(snapshot: DocumentSnapshot) -> object:
    return to_json(snapshot, DocumentSnapshot)
