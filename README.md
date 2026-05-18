# CAPE Weightor

Cape Arcona Type Foundry
by Thomas Schostok

---

## What it does

CAPE Weightor lets you make **selected glyphs bolder or lighter on the fly**, directly in Glyphs. It uses the OffsetCurve filter under the hood to expand or contract outlines, and gives you live feedback as you adjust the values.

You get independent control over two axes:

- **X** — expands strokes horizontally, making vertical stems thicker or thinner
- **Y** — expands strokes vertically, affecting horizontal strokes like crossbars and serifs (the overall glyph height is preserved automatically)

You can also control whether the expansion happens more towards the **outer** or **inner** edge of the strokes — useful if you want a slightly more optical result.

There is an optional **Preserve Height** setting that keeps the overall glyph height constant after the Y offset is applied. It is on by default — disable it when working on purely horizontal glyphs like *minus* or *macron*, where the stroke height and the glyph height are the same thing.

<img width="1658" height="1200" alt="CapeWeightor-Screen01" src="https://github.com/user-attachments/assets/4a0f5822-da33-47cf-9567-9040d497b4e4" />

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
4. When you're happy, click **Done**
5. Clicking **Reset (0)** restores the original outlines at any point

**Tip:** Hold **Shift** while clicking `+` / `−` to step in increments of 5 instead of 1.

### Auto-switch
While the dialog is open in the Edit tab, you can click on a different glyph and the script will automatically reset the previous glyph and apply the current settings to the new one.

### Sync X and Y
Enable the **Sync X and Y** checkbox to lock both axes together — handy when you want uniform expansion in all directions.

### Preserve Height
When checked (default), the script rescales the glyph vertically after applying the Y offset so the overall height stays the same. This keeps cap heights and descenders consistent across the font.

Uncheck it when you're working on a glyph whose entire vertical extent *is* the stroke — like a *minus*, *macron*, or similar flat shape. With height preservation on, the rescaling would completely cancel the Y offset for those glyphs, making the slider appear to do nothing.

The **Strength** control (0–100 %) sets how strongly the height correction is applied. At 100 % (default) the glyph is fully scaled back to its original height. At 0 % the correction is disabled entirely — equivalent to unchecking Preserve Height. Values in between give a partial correction.

This is especially useful for glyphs with diagonal strokes (A, V, K, X, diagonals in general). The OffsetCurve filter offsets along path normals, so a Y offset also produces a small horizontal component on diagonal strokes. The full vertical rescale at 100 % compensates the Y component but leaves that horizontal residue, which can change the angle of diagonals slightly. Reducing Strength to 50–70 % on those glyphs lets the height shift slightly but avoids the angular distortion. The trade-off is that the overall glyph height will no longer be exactly at its original value — treat it as a starting point and adjust manually.

### Move Anchors
When checked (default), anchors follow the horizontal expansion of the glyph. Their X position is scaled proportionally to the change in bounding box width — an anchor at the very left edge stays put (since the left edge is fixed by the sidebearing), while anchors further to the right shift proportionally. The Y position of all anchors is always kept at its original value, regardless of this setting, because font metrics (cap height, x-height, baseline) do not change when adjusting stroke weight.

**Node-snapping:** If an anchor sits exactly on a path node before the operation, it will be placed exactly on that same node's new position afterwards — both X and Y. This ensures that anchors on node positions (such as on the baseline curve of a diacritic base) remain pixel-precise rather than approximated. Anchors that are not on a node continue to use the proportional approximation.

Uncheck this if you want anchors to remain completely untouched at their original positions — useful when the automatic X movement doesn't match your expectations for a specific glyph.

### Copy / Paste Parameters
Use **Copy Parameters** and **Paste Parameters** to transfer settings between sessions or glyphs. All options including **Move Anchors** are included in the copied parameters.

https://github.com/user-attachments/assets/c367bd9e-7c86-4af0-a57a-aab98b38a868

---

## Known issues and limitations

- **Purely horizontal glyphs** (minus, macron, etc.) appear unaffected by the Y slider when **Preserve Height** is on — that's expected. The rescaling step exactly cancels the Y offset because the stroke height and the glyph height are identical. Uncheck Preserve Height to make the Y slider work on those glyphs.
- **Diagonal strokes** (X, K, R, diagonals in general) will change in unexpected ways when using the Y offset, because the OffsetCurve filter offsets along path normals — and diagonals have a horizontal component in their normal direction. Use the **Preserve Height Strength** control to reduce vertical rescaling on diagonal-heavy glyphs and minimise the angular distortion. Note that in italic styles, the diagonal lines tend to slope slightly.
- **Optical corrections** built into the original design (like overshoots, ink traps, or tapered strokes) won't scale properly. You'll likely need to clean those up by hand.
- **Anchor X movement** is a proportional approximation based on the bounding box change, not on the glyph's internal stroke structure. Exception: anchors that sit exactly on a path node are snapped back to the exact new position of that node. For all other anchors the movement is an estimate. Disable **Move Anchors** if the automatic placement is not useful for a particular glyph.
- **Components** are not affected — only paths in the active layer are modified.
- The script works with **Glyphs 3.5+** and **Python 3.11** (Glyphs built-in).
- For very large offset values, results can get messy. The slider range of ±10 is intentionally conservative — you can type larger values into the input fields, but use with caution.

---

## Requirements

- Glyphs 3.5 or later
- Python 3 (built into Glyphs)
- `vanilla` (included with Glyphs)

---

*Cape Arcona Type Foundry — [www.capearcona.com](https://www.capearcona.com)*
