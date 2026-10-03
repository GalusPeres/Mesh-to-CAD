# Getting started

This guide turns the bundled example scan of a bracket into a STEP file. It takes about
20 minutes and uses the main tools once. The German version is
[getting-started.de.md](getting-started.de.md).

The bracket is an L-shaped part of 80 × 50 × 60 mm with two holes in the base, one hole in
the upright and rounded edges. The scan has about 167,000 triangles and a noise of 0.03 mm,
and it lies tilted in space, as a real scan does.

## Mouse and keyboard

- Right drag rotates the view, middle drag pans, the wheel zooms to the cursor. A middle
  double-click shows everything.
- The left button selects and paints; it never moves the view.
- `F1` opens the help page of the active tool, `Ctrl+/` lists every shortcut.
- `Enter` confirms a tool (OK), `Esc` cancels it. `Ctrl+Z` undoes the last step.

## 1. Open the example

1. Start Mesh-to-CAD. The viewport shows _No scan loaded_.
2. Click **Open example** (or _Help > Open example: bracket_).
3. The _Import scan_ panel shows the file, its size and the measured scan noise. Keep the unit
   _mm_ and the proposed tolerance, then click **OK**.

The project tree now shows _Scan_ with the file name and the triangle count. The status bar
shows the triangle count and the project tolerance.

## 2. Prepare the scan

Stage _Prepare_. **Repair** checks the scan for duplicate points, faces without area and
inconsistent orientation. The example has no such defects, so the panel reports that there is
nothing to do. With a real scan, run it first, then remove loose parts with _Remove small
parts_ and close small holes with _Fill holes_.

## 3. Align the scan

Stage _Align_, tool **Align automatically**. The largest plane (the underside of the base)
becomes the XY plane, the largest plane perpendicular to it becomes XZ, and the origin moves
to a corner of the scan. Check in _Result_ that the largest plane is within a few hundredths
of a degree of XY. Use _Flip_ or _Rotate 90°_ if the part lies upside down, then click **OK**.

The alignment is the first entry under _History_. Double-click it to change it later; every
step after it is updated.

## 4. Find the surfaces

**Segment** splits the scan into regions of planes, cylinders and other shapes. They appear
under _Regions_ in the project tree, grouped by type. Pointing at a region highlights its
triangles in the viewport.

## 5. Fit the holes

Stage _Model_, tool **Fit shape** (`A`).

1. Choose _Smart select_ (`W`) in the tool row and click the wall of one hole in the base.
2. The panel shows _Cylinder_ with the scan noise, the RMS, the maximum and the share of
   triangles within the tolerance. The radius snaps to 4.500 mm and the axis to Z; each snap
   shows the measured value it replaced.
3. Click **OK**. _Cylinder 1_ appears in the history, and the used triangles leave the
   selection.

Repeat for the second hole and for the hole in the upright (radius 6.000 mm, axis parallel to
Y).

## 6. Sketch the side profile

Tool **Sketch** (`S`). Choose the plane _YZ_ and move the section to the middle of the part.
The section through the scan appears in the sketch plane. Click **OK** to fit lines and arcs:
the L-shaped outline with the inner fillet of R6. Values snap to design values such as
8.000 mm. The profile must be closed; the panel lists gaps if there are any. Click
**Finish sketch**.

## 7. Extrude the body

Tool **Extrude** (`E`). Choose _Sketch 1_ and _Symmetric_. The distance is taken from the scan
extent (80 mm). Keep _New body_ and click **OK**. _Body 1_ appears under _Bodies_; its volume
and validity are shown in the properties when it is selected.

## 8. Cut the holes and round the edges

1. Create a sketch on the top face of the base with two circles at the fitted hole axes, and
   extrude it with _Subtract_ through the base. Do the same for the hole in the upright.
2. Tool **Fillet**: click the two vertical front edges of the base. _Radius from scan_ fits a
   cylinder to the scan along the edges and proposes 8.000 mm. Click **OK**.

## 9. Check the deviation

Stage _Inspect_, tool **Deviation** (`D`). The scan is coloured by its distance to the body:
green within the tolerance, warmer colours where the scan lies outside, cooler colours where
it lies inside. The legend shows the share of points within the tolerance. Large coloured
areas mean that a feature is missing or a value is wrong; edit the feature in the history and
check again.

## 10. Export STEP

Tool **Export STEP …** (`Ctrl+E`). Select _Body 1_, keep _AP214_ and save the file. The file is
read back and compared with the model before it replaces an existing file. The status bar
confirms the file name and size.

Save the project with `Ctrl+S` to continue later. The project file keeps the scan, the regions,
the alignment and every step of the history.
