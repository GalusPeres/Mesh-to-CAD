# Third-party notices

Mesh-to-CAD uses the components below. Installers bundle their licence texts in
`resources/licenses/`; the release build collects them from the installed packages. The versions
are pinned in `package.json` and `kernel/requirements.txt`.

## Application and user interface

| Component                    | Licence                                | Source                                      |
| ---------------------------- | -------------------------------------- | ------------------------------------------- |
| Electron (includes Chromium) | MIT; Chromium: BSD-3-Clause and others | https://github.com/electron/electron        |
| React, React DOM             | MIT                                    | https://github.com/facebook/react           |
| three.js                     | MIT                                    | https://github.com/mrdoob/three.js          |
| three-mesh-bvh               | MIT                                    | https://github.com/gkjohnson/three-mesh-bvh |
| zustand                      | MIT                                    | https://github.com/pmndrs/zustand           |
| i18next, react-i18next       | MIT                                    | https://github.com/i18next                  |
| Radix UI primitives          | MIT                                    | https://github.com/radix-ui/primitives      |
| Lucide icons (lucide-react)  | ISC                                    | https://github.com/lucide-icons/lucide      |

## Geometry process

| Component               | Licence                                           | Source                                         |
| ----------------------- | ------------------------------------------------- | ---------------------------------------------- |
| Python                  | PSF License                                       | https://www.python.org/                        |
| numpy                   | BSD-3-Clause                                      | https://github.com/numpy/numpy                 |
| SciPy                   | BSD-3-Clause                                      | https://github.com/scipy/scipy                 |
| trimesh                 | MIT                                               | https://github.com/mikedh/trimesh              |
| NetworkX                | BSD-3-Clause                                      | https://github.com/networkx/networkx           |
| fast-simplification     | MIT                                               | https://github.com/pyvista/fast-simplification |
| Rtree, libspatialindex  | MIT                                               | https://github.com/Toblerity/rtree             |
| OCP (cadquery-ocp)      | Apache-2.0                                        | https://github.com/CadQuery/OCP                |
| Open CASCADE Technology | LGPL-2.1 with the Open CASCADE exception          | https://dev.opencascade.org/                   |
| VTK (dependency of OCP) | BSD-3-Clause                                      | https://vtk.org/                               |
| PyInstaller bootloader  | GPL-2.0 with the PyInstaller bootloader exception | https://github.com/pyinstaller/pyinstaller     |

Open CASCADE Technology is linked dynamically. Its libraries are installed as separate DLL files
in the application's `resources\kernel` folder and can be replaced with modified versions, as the
LGPL requires. Its source code is available from the Open CASCADE website.
