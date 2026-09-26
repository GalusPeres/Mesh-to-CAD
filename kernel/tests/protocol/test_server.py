"""The kernel as a subprocess: the tests talk to it exactly like the application does."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from tests.kernel_process import KernelProcess


def test_ready_event_reports_versions(tmp_path: Path) -> None:
    start = time.monotonic()
    process = KernelProcess(tmp_path / "session")
    try:
        ready = process.next_event("ready", timeout=10)
        assert time.monotonic() - start < 10
        assert ready["data"]["protocolVersion"] == 1
        assert ready["data"]["kernelVersion"]
    finally:
        assert process.stop() == 0


def test_system_info_reports_the_occt_version(kernel: KernelProcess) -> None:
    result = kernel.call("system.info").result
    assert result["occtVersion"].startswith("8.")
    assert result["protocolVersion"] == 1


def test_unknown_method_and_invalid_params_have_codes(kernel: KernelProcess) -> None:
    assert kernel.call("nothing.here").error_code == "kernel.unknownMethod"
    response = kernel.call("debug.sleep", {"seconds": "long"})
    assert response.error_code == "kernel.invalidParams"
    assert response.header["error"]["params"] == {"field": "seconds"}


def test_path_methods_are_reserved_for_the_main_process(kernel: KernelProcess) -> None:
    response = kernel.call("mesh.import", {"path": "C:/anything.stl"})
    assert response.error_code == "kernel.notAllowed"


def test_debug_commands_need_the_environment_switch(tmp_path: Path) -> None:
    process = KernelProcess(tmp_path / "session", debug_commands=False)
    try:
        process.next_event("ready", timeout=30)
        assert process.call("debug.sleep", {"seconds": 0}).error_code == "kernel.unknownMethod"
    finally:
        process.stop()


def test_stdout_writes_do_not_corrupt_the_stream(kernel: KernelProcess) -> None:
    assert kernel.call("debug.stdoutNoise").result == {"ok": True}
    assert kernel.call("system.ping").ok


def test_buffers_round_trip(kernel: KernelProcess) -> None:
    indices = np.arange(3_000_000, dtype=np.uint32)
    values = np.linspace(-1, 1, 1_000_001, dtype=np.float32)
    params = {
        "indices": {"$buf": 0, "dtype": "uint32", "shape": [len(indices)]},
        "values": {"$buf": 1, "dtype": "float32", "shape": [len(values)]},
    }
    response = kernel.call("debug.echoBuffers", params, buffers=[indices, values])
    assert response.result["indexSum"] == int(indices.astype(np.int64).sum())
    np.testing.assert_array_equal(np.frombuffer(response.buffers[1], np.float32), values)


def test_cancel_stops_a_cooperative_job_quickly(kernel: KernelProcess) -> None:
    request = kernel.send("debug.sleep", {"seconds": 20})
    time.sleep(0.2)
    start = time.monotonic()
    kernel.cancel(request)
    assert kernel.wait(request).error_code == "kernel.cancelled"
    assert time.monotonic() - start < 0.5


def test_a_new_request_in_a_lane_supersedes_the_previous_one(kernel: KernelProcess) -> None:
    first = kernel.send("debug.sleep", {"seconds": 20}, lane="debug.sleep:test")
    time.sleep(0.2)
    second = kernel.send("debug.sleep", {"seconds": 0}, lane="debug.sleep:test")
    assert kernel.wait(first).error_code == "kernel.superseded"
    assert kernel.wait(second).ok


def test_lanes_must_belong_to_their_method(kernel: KernelProcess) -> None:
    response = kernel.call("debug.sleep", {"seconds": 0}, lane="doc.preview")
    assert response.error_code == "kernel.invalidParams"


def test_progress_events_arrive_in_order(kernel: KernelProcess) -> None:
    request = kernel.send("debug.progress", {"steps": 5, "stepSeconds": 0.15})
    fractions = [kernel.next_event("progress")["data"]["fraction"] for _ in range(5)]
    assert kernel.wait(request).ok
    assert fractions == sorted(fractions)
    assert fractions[-1] == 1.0


def test_a_native_call_blocks_the_whole_kernel(kernel: KernelProcess) -> None:
    """Documents why the application enforces cancel timeouts itself (ARCHITECTURE.md 3.5.4)."""
    blocking = kernel.send("debug.nativeBlock", {"milliseconds": 1500})
    time.sleep(0.2)
    start = time.monotonic()
    kernel.cancel(blocking)
    ping = kernel.call("system.ping")
    assert ping.ok
    assert time.monotonic() - start > 1.0
    assert kernel.wait(blocking).error_code == "kernel.cancelled"


def test_restart_after_a_crash_restores_the_last_revision(tmp_path: Path, sphere_stl: Path) -> None:
    session_dir = tmp_path / "session"
    first = KernelProcess(session_dir)
    first.next_event("ready", timeout=30)
    report = first.call("mesh.import", {"path": str(sphere_stl)}, origin="main").result
    commit = first.call("mesh.commitImport", {"pendingId": report["pendingId"], "unit": "mm"})
    assert commit.result["revision"] == 1
    first.send("debug.crash")
    assert first.process.wait(timeout=10) != 0

    second = KernelProcess(session_dir)
    try:
        second.next_event("ready", timeout=30)
        snapshot = second.call("doc.get").result
        assert snapshot["revision"] == 1
        assert snapshot["document"]["scan"]["faceCount"] == report["faceCount"]
    finally:
        second.stop()


def test_shutdown_exits_cleanly(tmp_path: Path) -> None:
    process = KernelProcess(tmp_path / "session")
    process.next_event("ready", timeout=30)
    assert process.stop() == 0
