# Changelog
All notable changes to this project will be documented in this file.

## [v1.203] - 2026-06-09
### Fixed
- **Components are now fully protected in both modes.** The script never added or removed components, but `layer.applyTransform()` cascades onto every element of the layer — including components — so the slant/unslant, horizontal scale and Preserve-Height/Width rescales were silently stretching and shifting composite references. Two cascading problems followed from that:
  - **Weight mode** added no weight to components (OffsetCurve only acts on outline paths), but the applyTransform steps still squashed them. Composite glyphs (`ñ`, `ä`, `Ω̃`, …) came out with un-thickened, mis-positioned references.
  - **Width mode** condensed components horizontally without the closed-form vertical-stem compensation that the outline pipeline relies on — so the components' vertical stems lost weight, defeating the whole point of Width mode for composites.
  - **Fix:** `_capture_layer` now snapshots each component's `transform` tuple, and both `_apply_weight` and `_apply_width` re-seat the components from that snapshot in their per-layer `finally` block — the same pattern already used for background images and background paths. `_restore` and `_restore_pristine` also restore the component transforms, so Reset and Cancel return composites to their true original state. Run Weightor on the **base glyphs** and the composites will inherit the change automatically through their references — the previous behaviour silently broke that workflow.
- **Reset / Cancel now restore the correct original after navigating away and back.** The pristine snapshot was keyed by the live ObjC layer pointer, which Glyphs can replace with a fresh pointer when the same logical layer is re-selected (e.g. switching from `A` to `B` and back to `A`). The `if layer not in self._pristine` guard then missed the existing entry and re-snapshotted the *already-modified* working layer as the new "pristine" — so Reset and Cancel restored a corrupted baseline. The backup dictionaries (`_orig`, `_pristine`) are now keyed by the stable tuple `(glyph_name, masterId)`, the same identity used by the layer-change watcher, so a re-selected layer always hits its original pristine entry.
- **Manual-edit detection now sees component moves.** The path fingerprint used to detect mid-session hand-edits only sampled node and anchor positions. Moving a component by hand was therefore not recognised and would have been overwritten by the next slider tick. Components (name + 6-float transform) are now part of the fingerprint, so manual component edits trigger the same new-baseline snapshot as node or anchor edits.

### Internal
- Removed the diagnostic stem-dump prints that ran on every dialog open (`font.stems` / `master.stems` introspection) — they only existed to debug the stem selector during Width-mode development.

## [v1.202] - 2026-06-01
### Fixed
- **Background layer (Cmd+B) stays put — images *and* paths.** Two cascade effects neutralised in one `try / finally` block per layer:
  - **Reference images.** `GSLayer.applyTransform()` transforms every element of the layer, including reference images. The script now snapshots the affine transforms of both `layer.backgroundImage` *and* `layer.background.backgroundImage` and restores them after each per-layer pass.
  - **Background paths.** In some Glyphs versions `layer.LSB / RSB / width` setters and `applyTransform` translate the *paths* of the background layer on the X axis along with the foreground (their geometry is untouched, but the whole path moves). The script now re-seats the background paths from the captured snapshot in the same `finally`, so paths on the Cmd+B layer never drift even after dozens of slider changes.
### Internal
- Normalised the inconsistent 8-space indent inside the `_apply_weight` per-layer loop to the standard 4-space step. Purely cosmetic, no behavioural change.

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
