# CAPE Weightor

---

## What it does

CAPE Weightor lets you make selected glyphs bolder or lighter on the fly, directly in Glyphs. It uses the OffsetCurve filter under the hood to expand or contract outlines, and gives you live feedback as you adjust the values.

A **Weight / Width** switch at the top of the window chooses between two modes:

- **Weight** — make glyphs bolder or lighter (the original behaviour, described below).
- **Width** — condense or expand a glyph horizontally *without changing its weight*: the glyph gets narrower or wider while the vertical stems keep their thickness. See [Width mode](#width-mode).

Only one mode is active at a time. The two pipelines are kept separate on purpose — the intended workflow is sequential (e.g. first set the width, then add weight), not both at once.

In **Weight** mode you get independent control over two axes:

- **X** — expands strokes horizontally, making vertical stems thicker or thinner
- **Y** — expands strokes vertically, affecting horizontal strokes like crossbars and serifs (the overall glyph height is preserved automatically)

You can also control whether the expansion happens more towards the **outer** or **inner** edge of the strokes — useful if you want a slightly more optical result.

There is an optional **Preserve Height** setting that keeps the overall glyph height constant after the Y offset is applied. It is on by default — disable it when working on purely horizontal glyphs like *minus* or *macron*, where the stroke height and the glyph height are the same thing.

A separate **Preserve Outer Width** setting keeps the left and right outer edges pinned in place, so the added weight grows *inward* only — the glyph keeps exactly its current width. Combined with Preserve Height it locks the entire bounding box: an *O* keeps its outer circle while the counter thickens, an *H* keeps its outer verticals while the stems and crossbar fill inward.

---

<img width="701" height="549" alt="capeweightor-screenshotv1200" src="https://github.com/user-attachments/assets/da13c748-5d79-4c05-a86c-652c088f38e9" />



---

## Why this exists

Ideally you'd have a Light and Bold master and just interpolate. But that's not always the case — sometimes you're working on a single-master font, a display face, or something where setting up a whole second master just isn't practical.

Making a typeface bolder or lighter by hand is tedious. CAPE Weightor is meant to take some of that pain away and give you a starting point you can work from.

**That said — this is not an "auto bold" button.** The results will vary a lot depending on the typeface. Geometric fonts tend to respond pretty well. Fonts with lots of diagonal strokes, optical corrections, or complex shapes will need more manual cleanup afterwards. Think of it as a useful first pass, not a finished result.

---

## Usage

1. Open a glyph in the **Edit tab**, or select one or more glyphs in the **Font Overview**
2. Run the script via the Script menu — all settings from the previous session are restored and immediately applied
3. Adjust X and Y sliders — changes are applied live
4. When you're happy, click **Apply**
5. Clicking **Reset** restores the outlines to exactly the state they were in when the script opened — any manual edits made during the session are also undone

**Tip:** Hold **Shift** while clicking `+` / `−` to step in increments of 5 instead of 1.

### Auto-switch
While the dialog is open in the Edit tab, you can click on a different glyph and the script will automatically reset the previous glyph and apply the current settings to the new one.

### Manual editing while the dialog is open
You can move nodes or anchors by hand at any point while the dialog is open. The script detects the change automatically, takes a new baseline snapshot from the edited outline, and resets both sliders to 0. Subsequent adjustments build on your hand-edited version rather than overwriting it.

**Reset** and **Cancel** always restore the true original — the state before the script was opened — regardless of how many manual edits or slider adjustments were made during the session.

### Sync X and Y
Enable the **Sync X and Y** checkbox to lock both axes together — handy when you want uniform expansion in all directions.

### Weight distribution (Outer / Inner)
The **Outer / Inner** slider chooses where the added weight ends up. The **total stem growth stays the same** in all cases — only its location moves between the outer silhouette and the inner counter:

- **0 (full Outer)** — all the weight grows *outward*. The outer silhouette gets bigger, the counters stay exactly where they were.
- **50 (middle, default)** — symmetric: outer and inner edges of every stem each grow by `X`, exactly like a classic OffsetCurve at position 0.5.
- **100 (full Inner)** — all the weight grows *inward*. The outer silhouette stays put, the counters shrink.

Internally the script classifies each contour as **outer** or **inner (counter)** via even-odd containment, then offsets the two groups separately with `D_outer = 2·X·(1 − p)` and `D_inner = 2·X·p`. Nested counters such as in **B**, **g** or **8** are handled correctly. On glyphs with no counters (`I`, `l`, `|`) the inner share has nothing to act on, so values above `0` simply do less — `100` means no growth at all on those glyphs.

A typographer's tip: values around **30–40** often look better optically than a symmetric **50**, because pushing slightly more weight toward the outer keeps counters readable and prevents the small forms from clogging up at heavy weights.

#### How the classification works (per-contour logic)
For each path in the layer the script picks a representative point that lies just inside the path's enclosed area, and counts how many *other* paths enclose that point (even-odd nesting). A nesting count of 0, 2, 4… means the path is an *outer*; 1, 3, 5… means it is an *inner counter* (or an outer-within-an-inner, e.g. in `g` or `8`). The two groups are then offset independently and recombined.

Interior points are found by taking the tangent at every on-curve node (from its previous to its next neighbour, handles included for direction) and stepping ±ε along its perpendicular — the side that lies inside the path's bezier is the interior. For **open** contours (e.g. apertures drawn as open paths in some designs of `e`/`a`) a mid-stream on-curve node serves as the reference point instead, and the same containment test decides whether the open path counts as inner or outer.

#### Counters that are part of the outer contour
The distribution slider operates **per contour**, so it can only redistribute weight between contours that exist as **separate paths** in the layer. A typical `e` is drawn with **one** outer contour (with the lower aperture as an *inward notch* in that single path) plus a separate inner contour for the upper counter. In that case:

- **Slider 0** — outer offsets fully outward; the aperture notch is part of the outer and therefore also moves outward (= the aperture *shrinks*). The upper counter is left alone.
- **Slider 100** — outer is left alone, so the aperture stays where it was. The upper counter shrinks at full strength.

In other words, an aperture drawn as a notch in the outer follows the outer's share, not the inner's. **If you want the aperture to behave like a real counter under this slider, redraw it as a separate closed inner contour** (CCW direction, like the upper counter). The classification will then pick it up as inner and it will respond to the slider in symmetry with the other counters.

For open inner paths the offset direction is determined by the *path's drawn direction*. If an open inner contour appears to move the wrong way under the slider (counter *grows* at p = 1 instead of shrinking), reverse its direction via **Path → Reverse Contours**.

> ⚠️ The slider re-orders the paths in the layer (outer first, then inner) after the operation. This has no visual effect but can matter for compatibility-locked masters used in interpolation — reorder the paths manually if you need a specific order for compatibility.

### Preserve Height
When checked (default), the script rescales the glyph vertically after applying the Y offset so the overall height stays the same. This keeps cap heights and descenders consistent across the font.

Uncheck it when you're working on a glyph whose entire vertical extent *is* the stroke — like a *minus*, *macron*, or similar flat shape. With height preservation on, the rescaling would completely cancel the Y offset for those glyphs, making the slider appear to do nothing.

The **Strength** control (0–100 %) sets how strongly the height correction is applied. At 100 % (default) the glyph is fully scaled back to its original height. At 0 % the correction is disabled entirely — equivalent to unchecking Preserve Height. Values in between give a partial correction.

This is especially useful for glyphs with diagonal strokes (A, V, K, X, diagonals in general). The OffsetCurve filter offsets along path normals, so a Y offset also produces a small horizontal component on diagonal strokes. The full vertical rescale at 100 % compensates the Y component but leaves that horizontal residue, which can change the angle of diagonals slightly. Reducing Strength to 50–70 % on those glyphs lets the height shift slightly but avoids the angular distortion. The trade-off is that the overall glyph height will no longer be exactly at its original value — treat it as a starting point and adjust manually.

### Move Anchors
When checked (default), anchors follow the horizontal expansion of the glyph. Their X position is scaled proportionally to the change in bounding box width — an anchor at the very left edge stays put (since the left edge is fixed by the sidebearing), while anchors further to the right shift proportionally. The Y position of all anchors is always kept at its original value, regardless of this setting, because font metrics (cap height, x-height, baseline) do not change when adjusting stroke weight.

**Node-snapping:** If an anchor sits exactly on a path node before the operation, it will be placed exactly on that same node's new position afterwards — both X and Y. This ensures that anchors on node positions (such as on the baseline curve of a diacritic base) remain pixel-precise rather than approximated. Anchors that are not on a node continue to use the proportional approximation.

Uncheck this if you want anchors to remain completely untouched at their original positions — useful when the automatic X movement doesn't match your expectations for a specific glyph.

### Adjust Sidebearings
When checked (default), the original LSB and RSB are restored after the offset — the advance width grows with the stroke weight and the sidebearings stay consistent. This is the expected behaviour for most use cases.

When unchecked, sidebearings are not restored and the OffsetCurve filter determines the new LSB and RSB directly. The advance width stays fixed while the outline expands, so the sidebearings shrink. Useful when you want to keep the total advance width constant and adjust spacing manually afterwards.

### Preserve Outer Width
When checked, the outline is scaled back into its original horizontal bounding box after the offset, so the **left and right outer edges stay exactly where they were** and the added weight grows inward only. The advance width is also kept at its original value. This is different from *Adjust Sidebearings*: that option only changes the metrics, leaving the black outer edges to move outward, whereas this option pins the actual outline.

Typical results:

- **O** — the outer circle stays fixed, the counter shrinks, the ring gets thicker.
- **H** — the far-left and far-right verticals stay fixed, the stems and crossbar thicken inward.

Pair it with **Preserve Height** to lock the complete bounding box (horizontal by this option, vertical by Preserve Height). While Preserve Outer Width is on, **Adjust Sidebearings** is greyed out, since the width is already fully controlled here.

**Note:** Because this is a uniform scale back into the original box, the stems end up slightly less thick than a pure offset would make them, and round forms get marginally narrower in proportion. A mathematically clean "inner edges only move, outer stem flanks keep the full offset thickness" is not possible with a uniform offset filter — that would require interpolation between two masters. For the practical goal of "same outer silhouette, more weight inside" the scale-into-box approach is the right tool.

### Keep italic angle (Weight mode)
On a slanted master, *Preserve glyph height* alone would steepen the italic: the vertical rescale turns `tan α` into `tan α / s_height`, so a 12° italic ends up noticeably steeper after bolding. The **Keep italic angle** checkbox wraps the whole operation — OffsetCurve, *Preserve Height* and *Preserve Outer Width* — in an unslant → work → reslant sandwich. Because the shear is purely horizontal, Y-values are unaffected, so the height math is unchanged. After the reslant the angle is exactly the original value.

The label shows the master's italic angle from Font Info (e.g. *Keep italic angle (12°)*). On upright masters it reads *(0°)* and is greyed out — there is nothing to compensate, and the behaviour is identical to before. A bonus on italic masters: the OffsetCurve runs on truly vertical/horizontal stems in upright space, which cleans up the small angular residue diagonal-prone italic stems pick up otherwise.

### Copy / Paste Parameters
Use **Copy Parameters** and **Paste Parameters** to transfer settings between sessions or glyphs. All options — including **Move Anchors**, **Adjust Sidebearings**, **Preserve Outer Width**, the active **mode** and the **Width mode** settings (target width and selected stem) — are included in the copied parameters.

---

## Width mode

Width mode condenses or expands a glyph **horizontally without changing its weight**. A plain horizontal scale would also thin (or thicken) the vertical stems, which *is* a weight change — so the script compensates for it.

How it works:

1. The outline is scaled horizontally to the target width.
2. The scaling also changed the vertical-stem thickness, so an **X-only OffsetCurve** restores the stems to their nominal value. Because the offset is purely horizontal, **horizontal strokes (crossbars, the bars of E/F) are not touched** — they only need vertical thickness, which the horizontal scale never changed.
3. Sidebearings are scaled by the same percentage, so the spacing condenses with the glyph, and anchors follow the horizontal change (with node-snapping, just like in Weight mode).

Because the nominal stem value is known in advance, the required scale is solved in a single pass — there is no trial-and-error:

```
s = (W_target − n) / (W − n)
offset_per_side = n · (1 − s) / 2
```

where `W` is the original outline width, `W_target` the target width and `n` the selected vertical stem.

### Stem selector
The pop-up lists the current master's vertical stems as `name (value)` (e.g. `vStem0 (60)`). Pick the one the compensation should use. If a selected glyph belongs to a different master, that master's value for the same stem is used automatically. If the font defines no vertical stems, the script falls back to a plain horizontal scale — which **will** change the weight; add a stem to the master for proper compensation.

### Target width
Set the target as a percentage (50–150 %) with the field or slider. Double-click the slider to reset to 100 %, and hold **Shift** while clicking `+` / `−` to step in increments of 5.

### Keep italic angle
A plain horizontal scale also flattens the slant of an italic: condensing by factor `s` turns the angle `α` into `arctan(s · tan α)` — at 80 % a 12° italic would drop to about 9.6°. The **Keep italic angle** checkbox prevents that. The glyph is unslanted to upright, scaled and stem-compensated there, then re-slanted to the original angle, which keeps the slant exactly constant while the width changes.

The checkbox label shows the master's italic angle straight from Font Info (e.g. *Keep italic angle (12°)*). On upright masters it reads *(0°)* and is greyed out — there is nothing to compensate. When several selected glyphs belong to different masters, each glyph uses its own master's angle. Doing the stem compensation in upright space has a bonus: the X-only offset acts on truly vertical stems, so it is geometrically exact rather than the slight approximation it would be on slanted stems.

### Adjust sidebearings (Width mode)
By default Width mode scales **LSB** and **RSB** by the same factor as the outline, so the spacing condenses or expands together with the glyph. Enable **Adjust sidebearings** to keep the sidebearings at their **original values** instead — the outline still changes width, but the left and right margins stay exactly where they were. The advance width then changes only by the same amount as the outline (not proportionally to the original advance width). Useful when you want to condense the black shape only, e.g. while keeping a custom-spaced setting intact.

### Per-glyph stem deviation (important)
Compensation uses **one** stem value for the whole selection — the master's nominal `n`. Real glyphs deviate from that nominal: round glyphs are optically thicker, diagonals and special characters differ. Where a glyph's actual stem `a` differs from `n`, a small residual weight error remains:

```
weight_error = (1 − s) · (n − a)
```

If `a = n` the result is exact. If `a > n` the stems end up a little too thin; if `a < n`, a little too thick. The effect grows with larger deviations and more extreme condensing/expansion. Treat the result as a strong starting point and touch up outliers by hand. Glyphs built only from components are scaled but **not** stem-compensated (OffsetCurve does not affect components), so composites will lose a little weight when condensed.

Glyphs that are essentially all stem (`l`, `i`, `|`) are left untouched in Width mode, since they cannot be made narrower without changing their weight.

---

## Known issues and limitations

- **Purely horizontal glyphs** (minus, macron, etc.) appear unaffected by the Y slider when **Preserve Height** is on — that's expected. The rescaling step exactly cancels the Y offset because the stroke height and the glyph height are identical. Uncheck Preserve Height to make the Y slider work on those glyphs.
- **Diagonal strokes** (X, K, R, diagonals in general) will change in unexpected ways when using the Y offset, because the OffsetCurve filter offsets along path normals — and diagonals have a horizontal component in their normal direction. Use the **Preserve Height Strength** control to reduce vertical rescaling on diagonal-heavy glyphs and minimise the angular distortion. Note that in italic styles, the diagonal lines tend to slope slightly.
- **Optical corrections** built into the original design (like overshoots, ink traps, or tapered strokes) won't scale properly. You'll likely need to clean those up by hand.
- **Anchor X movement** is a proportional approximation based on the bounding box change, not on the glyph's internal stroke structure. Exception: anchors that sit exactly on a path node are snapped back to the exact new position of that node. For all other anchors the movement is an estimate. Disable **Move Anchors** if the automatic placement is not useful for a particular glyph.
- **Preserve Outer Width** works by scaling the outline back into its original bounding box. This thickens the inside as intended, but stems become slightly thinner than a pure offset and round shapes a touch narrower. It cannot produce a true directional offset (outer flanks fixed at full offset thickness) — that needs master interpolation. On glyphs built only from components it has no visible effect, since components are not offset in the first place.
- **The Cmd+B background layer stays put — both images and paths.** Reference images on the foreground layer (`layer.backgroundImage`) and on the Cmd+B background layer (`layer.background.backgroundImage`) keep their exact position, scale and rotation across every CAPE Weightor operation. The paths on the background layer are also re-seated after every per-layer pass: foreground LSB/RSB/width changes and applyTransform calls can cascade and shift those paths on X in some Glyphs versions, but the script restores them from the snapshot in a `try / finally`, so they never drift no matter how many slider changes you make.
- **Components** are not affected — only paths in the active layer are modified. In **Width mode** components *are* scaled horizontally but cannot be stem-compensated, so composite glyphs lose a little weight when condensed.
- **Width mode** uses one nominal stem value for the whole selection. Glyphs whose real stem deviates from the master nominal (round shapes, diagonals, special characters) keep a small residual weight error — see [Per-glyph stem deviation](#per-glyph-stem-deviation-important).
- The script works with **Glyphs 3.5+** and **Python 3.11** (Glyphs built-in).
- For very large offset values, results can get messy. The slider range of ±10 is intentionally conservative — you can type larger values into the input fields, but use with caution.

https://github.com/user-attachments/assets/538f25c9-c383-4467-b085-938aa477f3f1

---

## Requirements

- Glyphs 3.5 or later
- Python 3 (built into Glyphs)
- `vanilla` (included with Glyphs)

---

## Written by
Thomas Schostok

*Cape Arcona Type Foundry — [www.capearcona.com](https://www.capearcona.com)*
