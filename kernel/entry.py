"""Entry point of the frozen kernel (PyInstaller, `kernel/m2c-kernel.spec`).

Mesh decimation runs in a `multiprocessing` child process. In a frozen build the
child is this executable again, started with `--multiprocessing-fork`;
`freeze_support` must run first so that the child executes its task and exits
instead of starting a second kernel on the protocol pipes.
"""

import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()

    from m2c_kernel.main import run

    sys.exit(run())
