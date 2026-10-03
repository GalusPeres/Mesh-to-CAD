# Measured results

Measured on 2026-09-26 on the development machine (AMD Ryzen 7 7800X3D, 32 GB RAM, NVIDIA
GeForce RTX 4080, Windows 11) with the development kernel (Python 3.12, OCCT through OCP).
The kernel scenarios run through a real kernel process and the same protocol the application
uses; reproduce them with

```powershell
node scripts/py.mjs scripts/verify_scenarios.py plate armadillo
```

(the Armadillo scan is not part of the repository; the script expects it at
`.work/samples/stanford-armadillo.ply`, the Stanford 3D Scanning Repository model.)

Every STEP file is read back independently with plain OCCT (`STEPControl_Reader`,
`BRepCheck_Analyzer`), not only by the kernel's own export check.

## 1. Organic scan: Stanford Armadillo → automatic surfaces → hole → STEP

| Step                                                                                                         | Result                                                                                                                          |
| ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------- |
| Scan                                                                                                         | 345 944 triangles, diagonal 228.8 mm (file units taken as mm)                                                                   |
| Import (read, repair, commit)                                                                                | 1.2 s                                                                                                                           |
| Auto-Flächen, detail _Mittel_, smoothing _Gering_                                                            | 21.1 s, 3 000 B-spline patches, one closed valid solid, 237 550.5 mm³                                                           |
| Deviation scan ↔ surface body (per scan vertex)                                                              | RMS **0.29 mm** (0.13 % of the diagonal), 95 % within ±0.30 mm, 99 % within 1.18 mm, max **4.63 mm** (thin tips and deep folds) |
| Cylindrical hole ⌀ 12 mm through the torso (fit with fixed axis and radius → primitive body → combine _cut_) | 61.2 s, result valid, 1 solid, 6 037 mm³ removed                                                                                |
| STEP AP214 export incl. read-back check                                                                      | 57.3 s, 36 MB                                                                                                                   |
| STEP read back                                                                                               | **valid**, 1 solid, 2 998 faces: 2 997 B-spline surfaces + 1 cylinder (the hole); volume identical to the model (231 513.2 mm³) |
| Whole scenario                                                                                               | 173 s                                                                                                                           |

All freeform faces in the exported STEP are B-spline surfaces. The 0.1 mm project tolerance
is met by 51 % of the scan points only: at _Mittel_ the surface is a smooth approximation of
the scan (the scales and fine creases of the Armadillo are smaller than the patches). The
module tests of Auto-Flächen give the trade-off (same scan):

| Detail | Patches | Time   | RMS     | Max    |
| ------ | ------- | ------ | ------- | ------ |
| Grob   | 1 200   | 4.3 s  | 0.81 mm | 9.6 mm |
| Mittel | 3 000   | 9.6 s  | 0.28 mm | 4.3 mm |
| Fein   | 7 500   | 20.9 s | 0.12 mm | 2.1 mm |

(The module table uses the in-process decimator; the scenario above uses the application's
child-process decimator, which explains 21 s instead of 9.6 s for _Mittel_.)

## 2. Technical part: noisy flange plate → fits → section sketch → extrusion → STEP

Synthetic 100 × 60 × 10 mm plate with an 8 mm chamfer, three R8 corner fillets and holes
⌀ 20, ⌀ 12, ⌀ 12, tessellated to 261 841 triangles and disturbed with Gaussian scanner noise
σ = 0.03 mm along the normals. Workflow: fit plane (top), fit plane (bottom), fit cylinder
(⌀ 20 hole) → section sketch on the bottom-plane fit, cut at mid-height, automatic line/arc
fit → extrude up to the top-plane fit → STEP.

| Quantity                                    | True                       | Measured before snapping | Model after design-intent snapping | Error                        |
| ------------------------------------------- | -------------------------- | ------------------------ | ---------------------------------- | ---------------------------- |
| Top plane height                            | 10.000 mm                  | 10.0001 mm               | 10.000 mm                          | 0.0001 mm (0.000 after snap) |
| Bottom plane height                         | 0.000 mm                   | 0.0001 mm                | 0.000 mm                           | 0.0001 mm (0.000)            |
| Plane normals                               | Z                          | 0.0004° / 0.0003° off    | exactly Z                          | –                            |
| Hole radius                                 | 10.000 mm                  | 10.0005 mm ± 0.0007      | 10.000 mm                          | 0.0005 mm (0.000)            |
| Hole axis                                   | Z                          | 0.020° off               | exactly Z                          | –                            |
| Sketch radii (2 holes, 3 fillets, big hole) | 6, 6, 8, 8, 8, 10          | –                        | 6, 6, 8, 8, 8, 10                  | 0.000 mm                     |
| Sketch topology                             | 6 lines, 4 arcs, 2 circles | –                        | 6 lines, 4 arcs, 2 circles         | exact                        |
| Solid volume                                | 55 435.221 mm³             | –                        | 55 435.224 mm³                     | < 0.0001 %                   |

- Fit quality: RMS 0.030 mm on every fitted face (= the injected noise), 100 % of the points
  within the 0.1 mm tolerance.
- Deviation scan ↔ extruded solid: RMS **0.030 mm**, max 0.156 mm, 99.9 % within ±0.1 mm.
- STEP read back: **valid**, 1 solid, 14 faces (8 planes, 6 cylinders), 0.05 MB, export 0.04 s.
- Whole workflow in the kernel (import to solid): 4.2 s.

The measured values match the true design values to within 0.001 mm and 0.02°; snapping to
design values makes them exact, as intended for a technical part.

## 3. Viewport

`tests/e2e/viewport-perf.spec.ts` with the real GPU (`M2C_E2E_GPU=1`), 2 000 000-triangle scan:

| Quantity                                 | Budget     | Measured                  |
| ---------------------------------------- | ---------- | ------------------------- |
| Scan interactive after the kernel commit | < 3 000 ms | 789 ms                    |
| Longest main-thread task during loading  | < 100 ms   | 57 ms                     |
| Frame time while orbiting                | –          | 6.1 ms median (≈ 160 fps) |
| Brush selection sample                   | < 8 ms     | < 0.1 ms median           |

With software rendering (SwiftShader, which the other end-to-end tests use so they also run
without a GPU) the same scan needs 4.6 s and orbits at about 2 fps.

## 4. Test suites

| Suite                                                                                                     | Result                                                                                                                                                                                                             |
| --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `npm run check` (ESLint, Prettier, tsc, Vitest, ruff, mypy, pytest without slow tests, codegen, versions) | green: 314 Vitest tests, 470 kernel tests (29 skipped: frozen-kernel gate without `M2C_KERNEL_EXE`)                                                                                                                |
| `npx playwright test`                                                                                     | 13 passed; skipped: packaged-app test (needs `M2C_APP_BINARY`), documentation screenshots (opt-in) and five workflow steps still marked `fixme` (sketch, extrude, fillet, deviation, export in the UI walkthrough) |
| Frozen-kernel gate (`M2C_KERNEL_EXE=release\kernel\m2c-kernel.exe`, `-m frozen`)                          | 29 passed: protocol plus one call per method group, including decimation in a child process                                                                                                                        |
| Packaged app (`M2C_APP_BINARY=release\win-unpacked\Mesh-to-CAD.exe npx playwright test packaged`)         | passed: bundled kernel starts, example, help and licences are installed, renderer sandboxed, example scan opens                                                                                                    |

## 5. Windows package

| Quantity                                        | Target   | Measured                                                   |
| ----------------------------------------------- | -------- | ---------------------------------------------------------- |
| Installer `release\Mesh-to-CAD-0.1.0-Setup.exe` | < 200 MB | 210.7 MB (201 MiB), slightly above the target              |
| Unpacked kernel                                 | < 450 MB | 419.3 MB (largest parts: VTK libraries 129 MB, OCP 103 MB) |

The installer is not code-signed, so Windows SmartScreen asks for confirmation on the first start.
