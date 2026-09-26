# PyInstaller build of the geometry kernel (docs/ARCHITECTURE.md 3.4, 6.2).
#
# One folder, console subsystem: the application talks to the kernel over stdin and
# stdout. Run through scripts/build-kernel.mjs, which builds into release/kernel:
#
#   python -m PyInstaller kernel/m2c-kernel.spec --distpath release --workpath release/pyinstaller
#
# The frozen tests (kernel/tests/frozen) are the gate for every change here.

import importlib.util
from pathlib import Path

from PyInstaller.depend.bindepend import get_imports
from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

KERNEL = Path(SPECPATH)  # noqa: F821 - defined by PyInstaller

datas = []
binaries = []
hiddenimports = []

# OCP is one monolithic extension plus stub packages; fast_simplification ships a
# compiled extension that the import analysis does not find.
for package in ("OCP", "fast_simplification"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

# importlib.metadata lookups at runtime.
datas += copy_metadata("trimesh") + copy_metadata("cadquery-ocp")

# Commands and feature types are discovered with pkgutil at runtime.
hiddenimports += collect_submodules("m2c_kernel")


def delvewheel_dependencies(extension: Path, folders: list[Path]) -> list[Path]:
    """DLLs of delvewheel `.libs` folders that `extension` needs, transitively.

    OCP links VTK through TKIVtk, but only 47 of the 209 VTK DLLs are reachable from
    OCP's imports. Copying just those keeps about 140 MB out of the installation.
    """
    available = {dll.name.lower(): dll for folder in folders for dll in folder.glob("*.dll")}
    needed: dict[str, Path] = {}
    pending = [extension]
    while pending:
        for name, _resolved in get_imports(str(pending.pop())):
            key = Path(name).name.lower()
            dll = available.get(key)
            if dll is not None and key not in needed:
                needed[key] = dll
                pending.append(dll)
    return sorted(needed.values())


ocp_spec = importlib.util.find_spec("OCP")
assert ocp_spec is not None and ocp_spec.origin is not None, "OCP is not installed"
ocp_package = Path(ocp_spec.origin).parent
site_packages = ocp_package.parent
ocp_extension = next(ocp_package.glob("OCP*.pyd"))
libs_folders = [site_packages / "cadquery_ocp.libs", site_packages / "vtk.libs"]

# OCP/__init__.py calls os.add_dll_directory on both folders next to the package, so
# they must exist in the build even though PyInstaller would flatten their DLLs.
for dll in delvewheel_dependencies(ocp_extension, libs_folders):
    binaries.append((str(dll), dll.parent.name))

# Modules the kernel never imports. Each exclusion is covered by the frozen tests.
EXCLUDES = [
    "IPython",
    "matplotlib",
    "PIL",
    "pytest",
    "tkinter",
    "vtkmodules",
    "vtk",
    "PyInstaller",
    "setuptools",
    "pip",
]

analysis = Analysis(  # noqa: F821
    [str(KERNEL / "entry.py")],
    pathex=[str(KERNEL)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)  # noqa: F821
executable = EXE(  # noqa: F821
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="m2c-kernel",
    console=True,
    debug=False,
    strip=False,
    upx=False,
    icon=str(KERNEL.parent / "resources" / "icons" / "icon.ico"),
)
# The folder is named "kernel": electron-builder copies release/kernel into the
# installation's resources folder, where the application looks for m2c-kernel.exe.
COLLECT(  # noqa: F821
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="kernel",
)
