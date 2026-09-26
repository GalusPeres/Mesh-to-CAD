### Added

- _Abweichung_ colours the scan by its signed distance to the bodies (positive: excess material)
  with three steps per side around the tolerance band, a colour-blind safe scheme, an automatic or
  manual scale range and a maximum search distance. The legend at the right edge shows the band
  limits, the tolerance bracket and mean, σ, RMS, extremes and the share within tolerance; the
  value under the cursor appears next to it, and `D` switches the colours on and off. The status
  bar shows the share within tolerance while the colours are on.
- The deviation is exact to better than 0.001 mm against brute force, its signs agree with the
  solid classifier, and a million scan points take about 6 s, cancellable with progress.
- _Messen_ shows distances, angles and diameters between fitted shapes, reference geometry, origin
  planes and axes, and body faces picked in the viewport or the tree. Values of fitted shapes carry
  their measurement uncertainty from the scan ("20,001 mm ± 0,002").
- The tolerance in the status bar opens a popover with the value, the scan noise, the proposal
  from the noise and _Fangwerte: metrisch / Zoll_; it is the only place to change them.
- _STEP exportieren …_ (`Ctrl+E`) writes AP214 or AP242 in millimetres, one product per body named
  after the project, reads the file back and compares validity, solid count and volume before it
  replaces an existing file. _STL exportieren …_ writes a watertight binary STL with a chosen
  accuracy. Both check the bodies first and name the feature that caused a problem; umlauts in
  folder and product names work.
