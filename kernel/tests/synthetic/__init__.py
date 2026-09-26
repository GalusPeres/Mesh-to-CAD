"""Synthetic scans with exact ground truth, shared by all kernel tests.

Every test input is generated from code with fixed seeds; no binary fixtures are
stored in the repository.
"""

from tests.synthetic.meshes import (
    Patch,
    box_scan,
    primitive_patch,
    sphere_scan,
    write_binary_stl,
)
from tests.synthetic.noise import add_scanner_noise, random_pose, random_rotation

__all__ = [
    "Patch",
    "add_scanner_noise",
    "box_scan",
    "primitive_patch",
    "random_pose",
    "random_rotation",
    "sphere_scan",
    "write_binary_stl",
]
