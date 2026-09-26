"""The protocol subprocess suite, run against the frozen kernel.

`KernelProcess` starts `M2C_KERNEL_EXE` when it is set, so the tests of
tests/protocol/test_server.py check the frozen build unchanged: handshake, stdout
protection, cancellation, lanes, progress, native blocking, crash and restart.
"""

import pytest

from tests.frozen.conftest import requires_frozen_kernel
from tests.protocol.test_server import (
    test_a_native_call_blocks_the_whole_kernel,
    test_a_new_request_in_a_lane_supersedes_the_previous_one,
    test_buffers_round_trip,
    test_cancel_stops_a_cooperative_job_quickly,
    test_debug_commands_need_the_environment_switch,
    test_lanes_must_belong_to_their_method,
    test_path_methods_are_reserved_for_the_main_process,
    test_progress_events_arrive_in_order,
    test_ready_event_reports_versions,
    test_restart_after_a_crash_restores_the_last_revision,
    test_shutdown_exits_cleanly,
    test_stdout_writes_do_not_corrupt_the_stream,
    test_system_info_reports_the_occt_version,
    test_unknown_method_and_invalid_params_have_codes,
)

pytestmark = [pytest.mark.frozen, requires_frozen_kernel]

__all__ = [
    "test_a_native_call_blocks_the_whole_kernel",
    "test_a_new_request_in_a_lane_supersedes_the_previous_one",
    "test_buffers_round_trip",
    "test_cancel_stops_a_cooperative_job_quickly",
    "test_debug_commands_need_the_environment_switch",
    "test_lanes_must_belong_to_their_method",
    "test_path_methods_are_reserved_for_the_main_process",
    "test_progress_events_arrive_in_order",
    "test_ready_event_reports_versions",
    "test_restart_after_a_crash_restores_the_last_revision",
    "test_shutdown_exits_cleanly",
    "test_stdout_writes_do_not_corrupt_the_stream",
    "test_system_info_reports_the_occt_version",
    "test_unknown_method_and_invalid_params_have_codes",
]
