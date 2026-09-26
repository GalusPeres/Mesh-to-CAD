"""Collect the licence texts of every bundled component into resources/licenses/.

The installer ships this folder next to THIRD_PARTY_NOTICES.md. The script fails
when a bundled package has no licence text or when a component that must be
named in THIRD_PARTY_NOTICES.md is missing there, so a new dependency cannot be
released without its notice.

    .venv/Scripts/python scripts/collect-licenses.py
"""

from __future__ import annotations

import html
import importlib.metadata as metadata
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "resources" / "licenses"
NOTICES = ROOT / "THIRD_PARTY_NOTICES.md"
LICENSE_FILE = re.compile(r"(LICEN[CS]E|COPYING|NOTICE|AUTHORS)", re.IGNORECASE)

# Packages bundled without their Python dependencies: vtk only for the DLLs that
# OCP links (its modules and matplotlib are excluded from the kernel build), and
# PyInstaller only for the bootloader of the frozen kernel.
WITHOUT_DEPENDENCIES = {"vtk", "pyinstaller"}
BUILD_COMPONENTS = ["pyinstaller"]
# Packages whose wheel carries its licence outside the dist-info folder.
LICENSE_FALLBACK = {
    "cadquery-ocp": "cadquery_ocp/LICENSE",
    "cadquery-ocp-proxy": "cadquery_ocp/LICENSE",
}
# npm packages that declare their licence only in package.json and ship no text;
# the index records the declaration and the source repository instead.
DECLARED_ONLY = {"react-remove-scroll-bar"}
# How THIRD_PARTY_NOTICES.md names the components whose names differ from the package.
NOTICE_NAMES = {
    "cadquery-ocp": "OCP (cadquery-ocp)",
    "cadquery-ocp-proxy": "OCP (cadquery-ocp)",
    "fast-simplification": "fast-simplification",
    "pyinstaller": "PyInstaller bootloader",
    "rtree": "Rtree",
    "scipy": "SciPy",
    "networkx": "NetworkX",
    "react-dom": "React DOM",
    "react-i18next": "react-i18next",
    "lucide-react": "lucide-react",
    "electron": "Electron",
    "@radix-ui/*": "Radix UI",
}


@dataclass
class Component:
    ecosystem: str
    name: str
    version: str
    license: str
    files: list[Path] = field(default_factory=list)
    direct: bool = False

    @property
    def folder(self) -> str:
        return f"{self.name.replace('/', '+')}-{self.version}"


def normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def python_components() -> list[Component]:
    roots = [
        Requirement(line).name
        for line in (ROOT / "kernel" / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    found: dict[str, Component] = {}

    def visit(name: str, direct: bool) -> None:
        key = normalise(name)
        if key in found:
            return
        distribution = metadata.distribution(name)
        found[key] = Component(
            "python",
            key,
            distribution.version,
            license_of(distribution),
            files=python_license_files(distribution, key),
            direct=direct,
        )
        if key in WITHOUT_DEPENDENCIES:
            return
        for requirement in distribution.requires or []:
            parsed = Requirement(requirement)
            if parsed.marker is None or parsed.marker.evaluate({"extra": ""}):
                visit(parsed.name, False)

    for root in roots:
        visit(root, True)
    for name in BUILD_COMPONENTS:
        visit(name, True)
    return list(found.values())


def license_of(distribution: metadata.Distribution) -> str:
    """The SPDX expression, else the first line of the free-text licence field."""
    expression = distribution.metadata.get("License-Expression")
    if expression:
        return expression
    lines = (distribution.metadata.get("License") or "").strip().splitlines()
    return lines[0][:60] if lines else "see the licence files"


def python_license_files(distribution: metadata.Distribution, key: str) -> list[Path]:
    files = [
        Path(str(distribution.locate_file(entry)))
        for entry in distribution.files or []
        if ".dist-info" in str(entry) and LICENSE_FILE.search(entry.name)
    ]
    if not files and key in LICENSE_FALLBACK:
        files = [Path(str(distribution.locate_file(LICENSE_FALLBACK[key])))]
    return [file for file in files if file.is_file()]


def npm_components() -> list[Component]:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    direct = set(package["dependencies"])
    lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
    components = []
    for location, entry in lock["packages"].items():
        if not location or entry.get("dev") or entry.get("devOptional"):
            continue
        name = location.split("node_modules/")[-1]
        folder = ROOT / location
        files = sorted(file for file in folder.iterdir() if LICENSE_FILE.search(file.name))
        components.append(
            Component(
                "npm",
                name,
                entry["version"],
                entry.get("license", "see files"),
                files,
                name in direct,
            )
        )
    electron = ROOT / "node_modules" / "electron"
    version = json.loads((electron / "package.json").read_text(encoding="utf-8"))["version"]
    components.append(
        Component(
            "npm",
            "electron",
            version,
            "MIT; Chromium: BSD-3-Clause and others",
            # LICENSES.chromium.html (15 MB) is installed next to Mesh-to-CAD.exe by
            # electron-builder, so only Electron's own licence is copied here.
            [electron / "dist" / "LICENSE"],
            True,
        )
    )
    return components


def python_runtime() -> Component:
    version = ".".join(str(part) for part in sys.version_info[:3])
    return Component(
        "python", "python", version, "PSF-2.0", [Path(sys.base_prefix) / "LICENSE.txt"], True
    )


def lgpl_text() -> str:
    """The LGPL-2.1 text, taken from the Chromium licence file that Electron ships."""
    source = (ROOT / "node_modules" / "electron" / "dist" / "LICENSES.chromium.html").read_text(
        encoding="utf-8"
    )
    start = source.find("GNU LESSER GENERAL PUBLIC LICENSE")
    while start >= 0 and "Version 2.1, February 1999" not in source[start : start + 300]:
        start = source.find("GNU LESSER GENERAL PUBLIC LICENSE", start + 1)
    end = source.find("END OF TERMS AND CONDITIONS", start)
    if start < 0 or end < 0:
        raise SystemExit("LGPL-2.1 text not found in LICENSES.chromium.html")
    return html.unescape(source[start : end + len("END OF TERMS AND CONDITIONS")]) + "\n"


OCCT_NOTICE = """Open CASCADE Technology (OCCT)

The geometry process links Open CASCADE Technology dynamically through OCP
(cadquery-ocp). OCCT is licensed under the GNU Lesser General Public License,
version 2.1, with the Open CASCADE exception, version 1.0:
https://dev.opencascade.org/resources/licensing

The OCCT libraries are installed as separate DLL files in the application's
resources\\kernel\\_internal\\cadquery_ocp.libs folder and can be replaced with
modified versions. The source code is available from https://dev.opencascade.org/
and https://github.com/Open-Cascade-SAS/OCCT. The full LGPL-2.1 text is in
LGPL-2.1.txt next to this file.
"""


def declaration(component: Component) -> str:
    manifest = json.loads(
        (ROOT / "node_modules" / component.name / "package.json").read_text(encoding="utf-8")
    )
    repository = manifest.get("repository")
    if isinstance(repository, dict):
        repository = repository.get("url")
    return (
        f"{component.name} {component.version} declares the licence {component.license} in its"
        f" package.json and ships no licence text. Source: {repository}\n"
    )


def check_notices(components: list[Component]) -> list[str]:
    text = NOTICES.read_text(encoding="utf-8").lower()
    missing = []
    for component in components:
        if not component.direct:
            continue
        name = NOTICE_NAMES.get(component.name)
        if component.name.startswith("@radix-ui/"):
            name = NOTICE_NAMES["@radix-ui/*"]
        if (name or component.name).lower() not in text:
            missing.append(component.name)
    return missing


def main() -> None:
    components = [python_runtime(), *python_components(), *npm_components()]
    without_text = [
        f"{c.ecosystem}:{c.name}" for c in components if not c.files and c.name not in DECLARED_ONLY
    ]
    if without_text:
        raise SystemExit(f"No licence text found for: {', '.join(without_text)}")
    missing = check_notices(components)
    if missing:
        raise SystemExit(f"Not named in THIRD_PARTY_NOTICES.md: {', '.join(missing)}")

    shutil.rmtree(OUTPUT, ignore_errors=True)
    for component in components:
        target = OUTPUT / component.ecosystem / component.folder
        target.mkdir(parents=True, exist_ok=True)
        for file in component.files:
            shutil.copyfile(file, target / file.name)
        if not component.files:
            (target / "DECLARED.txt").write_text(declaration(component), encoding="utf-8")
    occt = OUTPUT / "occt"
    occt.mkdir(parents=True)
    (occt / "NOTICE.txt").write_text(OCCT_NOTICE, encoding="utf-8")
    (occt / "LGPL-2.1.txt").write_text(lgpl_text(), encoding="utf-8")
    shutil.copyfile(NOTICES, OUTPUT / "THIRD_PARTY_NOTICES.md")

    lines = ["Licences of the components bundled with Mesh-to-CAD", ""]
    for component in sorted(components, key=lambda c: (c.ecosystem, c.name)):
        lines.append(
            f"{component.ecosystem:<7} {component.name} {component.version}: "
            f"{component.license} ({component.ecosystem}/{component.folder})"
        )
    lines.append("occt    Open CASCADE Technology: LGPL-2.1 with exception (occt)")
    (OUTPUT / "INDEX.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Collected licences of {len(components)} components into {OUTPUT}")


if __name__ == "__main__":
    main()
