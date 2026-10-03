"""Time budgets of the speed tests.

The budgets are measured on a developer machine; the shared CI runners are about half as
fast, so there every budget doubles. A budget still catches a slowdown by a factor.
"""

from __future__ import annotations

import os

CI_SLOWDOWN = 2.0


def budget(seconds: float) -> float:
    """`seconds` on a developer machine, scaled for the CI runners."""
    return seconds * (CI_SLOWDOWN if os.environ.get("CI") else 1.0)
