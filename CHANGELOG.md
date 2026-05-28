# Changelog
All notable changes to this project will be documented in this file.

## [v1.201] - 2026-05-28
### Fixed
- **Outer/Inner contour classification** — the heuristic that decides which paths in a layer are *outer* and which are *inner counters* was rewritten:
  - **Ring shapes such as `O` and `o` are now classified correctly.** The previous version relied on edge midpoints between consecutive nodes plus a bbox-centre fallback. For Bézier circles consecutive nodes are *anchor ↔ tangent handle*, whose midpoints lie *outside* the curve — every candidate failed, the algorithm fell back to the bbox centre, and the bbox centre of the outer ring lands in the counter, *inside* the inner contour. The outer was then misclassified as inner. Visible effect: slider 0 did nothing, slider 100 produced a double-strength symmetric offset.
  - **The new approach uses only on-curve nodes.** At each on-curve node the algorithm computes the local tangent from `prev → next` (handles included for direction) and steps ±ε along its perpendicular. The side that lands inside the path's `bezierPath` is the interior side. The bbox-centre fallback was removed — paths that still can't be classified now fall back to *outer* (safe default).
  - **Open paths** (open inner apertures, e.g. in some designs of `e` or `a`) get a classification reference point at a midway on-curve node. The even-odd nesting test then correctly identifies them as *inner* when they sit geometrically inside a closed outer contour. *Caveat:* an open path's offset direction follows its drawn path direction — if it deviates from the usual Glyphs PS convention (CCW for inner), reverse it via *Path → Reverse Contours*.
- Robust off-curve detection across Glyphs versions (`GSOFFCURVE` constant with string fallback).

### Notes
- The distribution slider operates **per contour**. Counters that are geometrically *part of the outer contour* (e.g. the lower aperture of an `e` drawn as an inward notch in a single outer path, rather than as a separate inner contour) cannot be controlled independently — they follow the outer's distribution share. To get independent control of such a counter, redraw it as a separate closed inner contour. See the README section *Weight distribution* for details.

## [v1.200] - 2026-05-26
### Added
- **WIDTH mode** — a new mode (selected via the *Weight / Width* switch at the top of the window) that condenses or expands a glyph horizontally **without changing its weight**. The outline is scaled horizontally and the vertical stems are restored to their nominal thickness with an X-only OffsetCurve, using a closed-form solution `s = (W_target − n) / (W − n)` so the target width and full stem restoration are hit in a single pass. Horizontal stems (crossbars) are untouched. **You need at least one Stem in the Font Info of your master.**
  - **Stem selector** — a pop-up lists the master's vertical stems as `name (value)`; the chosen value is used as the compensation reference. When a glyph belongs to a different master, that master's stem value is used automatically.
  - **Target width** — percentage field + slider (50–150 %), double-click the slider to reset to 100 %, hold SHIFT for ±5 steps.
  - Sidebearings are scaled proportionally so the spacing condenses/expands with the glyph; anchors follow the horizontal change (with node-snapping), exactly as in Weight mode.
  - Glyphs that are essentially all stem (`l`, `i`, `|`) are left untouched, since they cannot be narrowed without changing weight.
  - **Keep italic angle** — for slanted masters the italic angle from Font Info is shown and held constant: the glyph is unslanted, scaled + stem-compensated in upright space, then re-slanted, so condensing/expanding no longer flattens or steepens the slant. The checkbox label shows the actual angle (e.g. *Keep italic angle (12°)*); on upright masters it reads *(0°)* and is greyed out. Doing the stem compensation in upright space also makes the X-offset geometrically exact for italics.
  - **Adjust sidebearings** — by default Width mode scales LSB and RSB proportionally so that the spacing condenses/expands with the glyph. When this option is enabled, LSB and RSB are restored to their original values instead; only the outline width changes, spacing stays exactly where it was. Mirrors the weight-mode option.
- **Keep italic angle in Weight mode** — the same checkbox is available when bolding/lightening. The OffsetCurve, *Preserve glyph height* and *Preserve outer width* steps now run inside an unslant → work → reslant sandwich on italic masters. This eliminates the slant-steepening that *Preserve glyph height* otherwise introduces (vertical rescale changes `tan α` to `tan α / s`) and lets the X-offset thicken truly vertical stems cleanly. On upright masters the checkbox is greyed out and the behaviour is byte-identical to before.
- New preference keys `mode`, `widthPct`, `widthStemIdx`, `widthKeepItalic`, `weightKeepItalic` and `widthAdjustSidebearings`, all included in Copy / Paste Parameters.
- **Manual-edit detection** — while the dialog is open, moving nodes or anchors by hand is detected automatically via a position fingerprint. The script takes a new baseline snapshot from the edited outline and resets the sliders to 0, so subsequent adjustments build on the hand-edited version rather than overwriting it.
- **True original (pristine) backup** — the glyph state at the moment the script opens is now preserved separately from the working baseline. *Reset* and *Cancel* always restore this true original, even if manual edits were made mid-session.
### Fixed
- Anchor positions are now included in the manual-edit fingerprint, so moving an anchor by hand triggers a new baseline snapshot in the same way that moving a path node does.
- **Weight distribution (Outer / Inner) now does what the label says.** The previous slider was wired straight to the `position` parameter of `GlyphsFilterOffsetCurve`, which in this API actually controls *offset intensity* (0 → 2× the per-side offset, 0.5 → normal, 1 → no offset), not the distribution between outer and inner edges. The slider has been re-implemented as a true distribution:
  - Outer and inner contours are classified per layer via NSBezierPath containment (even-odd nesting), so nested counters such as in **B**, **g**, **8** are handled correctly. Contours that cannot be classified fall back to *outer*.
  - Each group is offset separately with `OffsetCurve` at `position = 0.5`. Per-group offsets are `D_outer = 2·X·(1 − p)` and `D_inner = 2·X·p`, so the **total stem growth stays at 2·X regardless of `p`** — only its location changes.
  - At `p = 0` the silhouette grows outward and counters are preserved; at `p = 1` the silhouette is preserved and counters shrink inward; at `p = 0.5` the result is identical to the previous symmetric default.
  - Slider range widened from 0–97 to 0–100. Paths within a layer may be re-ordered after the operation (outer first, then inner); this has no visual effect but can matter for compatibility-locked interpolation — reorder manually if needed.

## [v1.100] - 2026-05-25
### Added
- **Preserve outer width (grow inward)** — scales the outline back into its original horizontal bounding box after the offset, keeping the left and right outer edges pinned and letting the added weight grow inward only. Pairs with *Preserve glyph height* to lock the complete bounding box. *Adjust sidebearings* is automatically disabled while this option is active.
- New preference key `preserveWidth` included in Copy / Paste Parameters.

## [v1.001] - 2026-05-19
### Added
- Adjust sidebearing on/off
### Fixed
- Prevent re-execution if script is still active
