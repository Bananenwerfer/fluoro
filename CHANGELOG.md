# Changelog

## 1.1.0 (2026-11)

First public release.

- ROI proposal and measurement are identical to the version used in the original study (1.0.0). This was verified
  on all 546 approved ROIs of that study: bit-identical proposal masks and identical measured values.
- The exclusion area for the label of one specific camera was removed; it is an optional parameter of `propose_roi`.
- New lean Qt interface (PySide6) in English; images are paired by file name within one folder.
- Selectable measurement channel (red, green, blue, grayscale).
- Blind mode: fluorescence image and values stay hidden until the ROI is approved (on by default).
