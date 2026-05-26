# Changelog
All notable changes to this project will be documented in this file.

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

## [v1.100] - 2026-05-25
### Added
- **Preserve outer width (grow inward)** — scales the outline back into its original horizontal bounding box after the offset, keeping the left and right outer edges pinned and letting the added weight grow inward only. Pairs with *Preserve glyph height* to lock the complete bounding box. *Adjust sidebearings* is automatically disabled while this option is active.
- New preference key `preserveWidth` included in Copy / Paste Parameters.

## [v1.001] - 2026-05-19
### Added
- Adjust sidebearing on/off
### Fixed
- Prevent re-execution if script is still active
