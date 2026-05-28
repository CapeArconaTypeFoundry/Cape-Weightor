#MenuTitle: CAPE Weightor
# -*- coding: utf-8 -*-
#
# CAPE Weightor
# Version 1.201 - 28-May-2026
#
# Cape Arcona Type Foundry
# Written by Thomas Schostok

__doc__ = """
Adjusts the weight OR width of selected glyphs. In Weight mode it uses the OffsetCurve filter with independent X/Y offsets, outer/inner distribution and outer-width/height preservation. In Width mode it condenses or expands a glyph horizontally while keeping the vertical stem thickness constant (horizontal scale + closed-form stem compensation). Live preview with automatic glyph switching in the edit tab.
"""

import json
import math
import objc
import vanilla
from AppKit import NSApp, NSClickGestureRecognizer, NSEvent, NSPasteboard, NSPasteboardTypeString, NSScreen, NSTimer
from Foundation import NSObject, NSPoint

STEP       = 1
STEP_SHIFT = 5
WIN_W      = 270
WIN_H      = 470

PREF_PREFIX          = "com.cape.makeMeBolder."
PREF_VALUE           = PREF_PREFIX + "value"
PREF_VALUE_Y         = PREF_PREFIX + "valueY"
PREF_POS             = PREF_PREFIX + "position"
PREF_KEEP            = PREF_PREFIX + "keepCompatible"
PREF_SYNC            = PREF_PREFIX + "syncXY"
PREF_PRESERVE_H      = PREF_PREFIX + "preserveHeight"
PREF_STRENGTH        = PREF_PREFIX + "preserveStrength"
PREF_MOVE_ANCHORS    = PREF_PREFIX + "moveAnchors"
PREF_ADJ_SB          = PREF_PREFIX + "adjustSidebearings"
PREF_PRESERVE_W      = PREF_PREFIX + "preserveWidth"
PREF_MODE            = PREF_PREFIX + "mode"
PREF_WIDTH_PCT       = PREF_PREFIX + "widthPct"
PREF_WIDTH_STEM      = PREF_PREFIX + "widthStemIdx"
PREF_W_ITALIC        = PREF_PREFIX + "widthKeepItalic"
PREF_KEEP_ITAL_W     = PREF_PREFIX + "weightKeepItalic"
PREF_W_ADJ_SB        = PREF_PREFIX + "widthAdjustSidebearings"
PREF_WIN_POS         = PREF_PREFIX + "winPos"


def _frame_on_screen(x, y):
    """Return True if the window at (x, y) overlaps enough with at least one screen."""
    for screen in NSScreen.screens():
        sf = screen.visibleFrame()
        ox = min(x + WIN_W, sf.origin.x + sf.size.width)  - max(x, sf.origin.x)
        oy = min(y + WIN_H, sf.origin.y + sf.size.height) - max(y, sf.origin.y)
        if ox > 50 and oy > 30:
            return True
    return False


try:
    _DoubleClickTarget = objc.lookUpClass("_DoubleClickTarget")
except objc.nosuchclass_error:
    class _DoubleClickTarget(NSObject):
        """ObjC-compatible target for NSClickGestureRecognizer (double-click → reset slider)."""

        def fire_(self, sender):
            if hasattr(self, "_py_callback") and self._py_callback:
                self._py_callback()

        @objc.python_method
        def set_callback(self, cb):
            self._py_callback = cb


class BolderDialog:
    def __init__(self):
        self.font = Glyphs.font
        if not self.font:
            print("No font open.")
            return

        # Collect selected layers — works in font overview and edit tab
        self.layers = list(self.font.selectedLayers or [])
        if not self.layers and self.font.currentTab:
            layer = self.font.currentTab.activeLayer()
            if layer:
                self.layers = [layer]

        if not self.layers:
            print("No glyphs selected.")
            return

        self.value      = 0   # X offset — thickens vertical stems
        self.value_y    = 0   # Y offset — thickens horizontal strokes (height preserved)
        self.mode       = "weight"   # "weight" | "width"
        self.width_pct  = 100.0      # target width in % of original (Width mode)
        self._vstem_list = self._vertical_stem_metrics()  # [(font.stems index, name), ...]
        self.width_stem_idx = self._vstem_list[0][0] if self._vstem_list else None
        self._committed = False
        self._pristine  = {}  # true original per layer — never overwritten (Reset / Cancel)
        self._save()

        title = (f"CAPE Weightor: {self.layers[0].parent.name}"
                 if len(self.layers) == 1
                 else f"CAPE Weightor: {len(self.layers)} Glyphs")

        # Compute centered position as fallback
        screen = NSScreen.mainScreen().visibleFrame()
        cx = int(screen.origin.x + (screen.size.width  - WIN_W) / 2)
        cy = int(screen.origin.y + (screen.size.height - WIN_H) / 2)

        self.w = vanilla.FloatingWindow((WIN_W, WIN_H), title)

        # ── Mode switch (Weight / Width) ─────────────────────────────────────
        self.w.mode_seg = vanilla.SegmentedButton(
            (10, 10, 250, 24),
            [dict(title="Weight"), dict(title="Width")],
            callback=self._mode_changed,
        )
        self.w.mode_seg.set(0)

        # ── X offset (vertical stems) ────────────────────────────────────────
        self.w.minus   = vanilla.Button(   (10,  46,  40, 30), "−",                callback=self._minus)
        self.w.field   = vanilla.EditText( (55,  46,  90, 30), "0",                callback=self._field_changed)
        self.w.plus    = vanilla.Button(   (150, 46,  40, 30), "+",                callback=self._plus)
        self.w.label   = vanilla.TextBox(  (196, 52,  65, 18), f"X  ±{STEP}",      sizeStyle="small")

        self.w.hint    = vanilla.TextBox(  (10,  78, 250, 14), "Hold SHIFT for ±5 steps",
                                           sizeStyle="small")

        self.w.slider  = vanilla.Slider(   (10,  96, 250, 20), minValue=-10, maxValue=10, value=0,
                                           tickMarkCount=21, stopOnTickMarks=True,
                                           callback=self._slider_changed)

        # ── Y offset (horizontal strokes, height preserved) ──────────────────
        self.w.minus_y  = vanilla.Button(   (10,  124,  40, 30), "−",               callback=self._minus_y)
        self.w.field_y  = vanilla.EditText( (55,  124,  90, 30), "0",               callback=self._field_y_changed)
        self.w.plus_y   = vanilla.Button(   (150, 124,  40, 30), "+",               callback=self._plus_y)
        self.w.label_y  = vanilla.TextBox(  (196, 130,  65, 18), f"Y  ±{STEP}",     sizeStyle="small")

        self.w.slider_y = vanilla.Slider(   (10, 158, 250, 20), minValue=-10, maxValue=10, value=0,
                                            tickMarkCount=21, stopOnTickMarks=True,
                                            callback=self._slider_y_changed)

        # Double-click on either slider knob → reset that axis to 0
        self._x_dbl = _DoubleClickTarget.alloc().init()
        self._x_dbl.set_callback(self._reset_x_slider)
        rec_x = NSClickGestureRecognizer.alloc().initWithTarget_action_(self._x_dbl, "fire:")
        rec_x.setNumberOfClicksRequired_(2)
        self.w.slider.getNSSlider().addGestureRecognizer_(rec_x)

        self._y_dbl = _DoubleClickTarget.alloc().init()
        self._y_dbl.set_callback(self._reset_y_slider)
        rec_y = NSClickGestureRecognizer.alloc().initWithTarget_action_(self._y_dbl, "fire:")
        rec_y.setNumberOfClicksRequired_(2)
        self.w.slider_y.getNSSlider().addGestureRecognizer_(rec_y)

        self.w.hint_y   = vanilla.TextBox(  (10, 182, 250, 14), "Hold SHIFT for ±5 steps",
                                            sizeStyle="small")

        self.w.xy_sync  = vanilla.CheckBox( (10, 200, 250, 20), "Sync X and Y",
                                            value=False, callback=self._xy_sync_toggled,
                                            sizeStyle="small")

        # ── Weight distribution (outer / inner edge of strokes) ─────────────
        self.w.pos_lbl_l  = vanilla.TextBox(  (10,  225,  35, 14), "Outer", sizeStyle="small")
        self.w.pos_slider = vanilla.Slider(   (48,  224, 118, 18), minValue=0, maxValue=100, value=50,
                                              callback=self._pos_changed)
        self.w.pos_field  = vanilla.EditText( (170, 221,  42, 22), "50",
                                              callback=self._pos_field_changed)
        self.w.pos_lbl_r  = vanilla.TextBox(  (216, 225,  38, 14), "Inner", sizeStyle="small")

        # ── Options ─────────────────────────────────────────────────────────
        self.w.cleanup      = vanilla.CheckBox( (10, 252, 250, 20), "Keep node count (no new nodes)",
                                                value=True, callback=self._cleanup_toggled,
                                                sizeStyle="small")
        self.w.preserve_h      = vanilla.CheckBox( (10, 274, 250, 20), "Preserve glyph height",
                                                   value=True, callback=self._preserve_h_toggled,
                                                   sizeStyle="small")
        self.w.strength_lbl    = vanilla.TextBox(  (22,  298,  58, 14), "Strength",  sizeStyle="small")
        self.w.strength_slider = vanilla.Slider(   (80,  297, 130, 18), minValue=0, maxValue=100, value=100,
                                                   callback=self._strength_slider_changed)
        self.w.strength_field  = vanilla.EditText( (214, 294,  36, 22), "100",
                                                   callback=self._strength_field_changed)
        self.w.strength_pct    = vanilla.TextBox(  (252, 298,  16, 14), "%",         sizeStyle="small")

        # Double-click to reset pos slider → 50, strength slider → 100
        self._pos_dbl = _DoubleClickTarget.alloc().init()
        self._pos_dbl.set_callback(self._reset_pos_slider)
        rec_pos = NSClickGestureRecognizer.alloc().initWithTarget_action_(self._pos_dbl, "fire:")
        rec_pos.setNumberOfClicksRequired_(2)
        self.w.pos_slider.getNSSlider().addGestureRecognizer_(rec_pos)

        self._str_dbl = _DoubleClickTarget.alloc().init()
        self._str_dbl.set_callback(self._reset_strength_slider)
        rec_str = NSClickGestureRecognizer.alloc().initWithTarget_action_(self._str_dbl, "fire:")
        rec_str.setNumberOfClicksRequired_(2)
        self.w.strength_slider.getNSSlider().addGestureRecognizer_(rec_str)

        self.w.move_anchors    = vanilla.CheckBox( (10, 318, 250, 20), "Move anchors with glyph",
                                                   value=True, callback=self._move_anchors_toggled,
                                                   sizeStyle="small")
        self.w.adjust_sb       = vanilla.CheckBox( (10, 340, 250, 20), "Adjust sidebearings",
                                                   value=True, callback=self._adjust_sb_toggled,
                                                   sizeStyle="small")
        self.w.preserve_w      = vanilla.CheckBox( (10, 362, 250, 20), "Preserve outer width (grow inward)",
                                                   value=False, callback=self._preserve_w_toggled,
                                                   sizeStyle="small")
        # Italic-angle checkbox placeholder; label/enable state set after first_master
        # is resolved (right after the Width-mode block).
        self.w.weight_italic   = vanilla.CheckBox( (10, 384, 250, 20), "Keep italic angle (0°)",
                                                   value=False, callback=self._weight_italic_toggled,
                                                   sizeStyle="small")

        # ── Width mode controls (shown only in Width mode) ───────────────────
        first_master = self._resolve_master(self.layers[0])
        # Diagnostic: dump what the font/master actually expose for stems
        try:
            print("CAPE Weightor — font.stems:",
                  [(i, m.name, bool(m.horizontal)) for i, m in enumerate(self.font.stems)])
            print("CAPE Weightor — master.stems:",
                  list(first_master.stems) if first_master else None,
                  "| master:", first_master.name if first_master else None)
        except Exception as e:
            print(f"CAPE Weightor — stem dump failed: {e}")

        stem_items = []
        for gidx, sname in self._vstem_list:
            val = self._stem_value(first_master, gidx)
            stem_items.append(sname if val is None else f"{sname} ({val:g})")
        if not stem_items:
            stem_items = ["(no vertical stems)"]

        self.w.wmode_stem_lbl = vanilla.TextBox(    (10, 50, 40, 18), "Stem", sizeStyle="small")
        self.w.wmode_stem     = vanilla.PopUpButton((50, 47, 210, 22), stem_items,
                                                    callback=self._width_stem_changed)

        self.w.wmode_minus  = vanilla.Button(   (10,  88,  40, 30), "−",   callback=self._width_minus)
        self.w.wmode_field  = vanilla.EditText( (55,  88,  90, 30), "100", callback=self._width_field_changed)
        self.w.wmode_plus   = vanilla.Button(   (150, 88,  40, 30), "+",   callback=self._width_plus)
        self.w.wmode_lbl    = vanilla.TextBox(  (196, 94,  70, 18), "Width %", sizeStyle="small")

        self.w.wmode_slider = vanilla.Slider(   (10, 126, 250, 20), minValue=50, maxValue=150, value=100,
                                                callback=self._width_slider_changed)
        self.w.wmode_hint   = vanilla.TextBox(  (10, 150, 250, 14),
                                                "Double-click slider → 100 %   ·   SHIFT for ±5",
                                                sizeStyle="small")

        ital = self._italic_angle(first_master)
        self._has_italic = abs(ital) > 1e-6
        self.w.wmode_italic = vanilla.CheckBox( (10, 176, 250, 20),
                                                f"Keep italic angle ({ital:g}°)",
                                                value=self._has_italic,
                                                callback=self._width_italic_toggled,
                                                sizeStyle="small")
        self.w.wmode_italic.enable(self._has_italic)

        self.w.wmode_adj_sb = vanilla.CheckBox( (10, 200, 250, 20),
                                                "Adjust sidebearings",
                                                value=False,
                                                callback=self._width_adj_sb_toggled,
                                                sizeStyle="small")

        # Mirror label + enabled state onto the weight-mode italic checkbox
        try:
            self.w.weight_italic.getNSButton().setTitle_(f"Keep italic angle ({ital:g}°)")
        except Exception:
            pass
        self.w.weight_italic.set(self._has_italic)
        self.w.weight_italic.enable(self._has_italic)

        # Double-click on width slider → reset to 100 %
        self._w_dbl = _DoubleClickTarget.alloc().init()
        self._w_dbl.set_callback(self._reset_width_slider)
        rec_w = NSClickGestureRecognizer.alloc().initWithTarget_action_(self._w_dbl, "fire:")
        rec_w.setNumberOfClicksRequired_(2)
        self.w.wmode_slider.getNSSlider().addGestureRecognizer_(rec_w)

        # ── Copy / Paste parameters ─────────────────────────────────────────
        self.w.copy_btn  = vanilla.Button( (10,  414, 120, 22), "Copy Parameters",  callback=self._copy_params)
        self.w.paste_btn = vanilla.Button( (140, 414, 120, 22), "Paste Parameters", callback=self._paste_params)

        # ── Reset / Done ─────────────────────────────────────────────────────
        self.w.reset = vanilla.Button( (10,  442, 115, 25), "Reset", callback=self._reset)
        self.w.done  = vanilla.Button( (140, 442, 120, 25), "Apply",      callback=self._done)
        self.w.setDefaultButton(self.w.done)

        # Control groups for mode-dependent show/hide
        self._weight_controls = [
            self.w.minus, self.w.field, self.w.plus, self.w.label, self.w.hint, self.w.slider,
            self.w.minus_y, self.w.field_y, self.w.plus_y, self.w.label_y, self.w.slider_y, self.w.hint_y,
            self.w.xy_sync,
            self.w.pos_lbl_l, self.w.pos_slider, self.w.pos_field, self.w.pos_lbl_r,
            self.w.cleanup, self.w.preserve_h, self.w.strength_lbl, self.w.strength_slider,
            self.w.strength_field, self.w.strength_pct,
            self.w.move_anchors, self.w.adjust_sb, self.w.preserve_w,
            self.w.weight_italic,
        ]
        self._width_controls = [
            self.w.wmode_stem_lbl, self.w.wmode_stem,
            self.w.wmode_minus, self.w.wmode_field, self.w.wmode_plus, self.w.wmode_lbl,
            self.w.wmode_slider, self.w.wmode_hint, self.w.wmode_italic,
            self.w.wmode_adj_sb,
        ]
        self._update_mode_ui()

        # Restore last-used values before opening
        self._load_prefs()

        self.w.bind("close", self._on_close)
        self.w.open()

        # Restore last window position if it's still on screen, else center
        wx, wy = cx, cy
        saved_win = Glyphs.defaults.get(PREF_WIN_POS)
        if saved_win:
            try:
                sx, sy = map(int, str(saved_win).split(","))
                if _frame_on_screen(sx, sy):
                    wx, wy = sx, sy
            except Exception:
                pass
        self.w.getNSWindow().setFrameOrigin_((wx, wy))

        # Start layer-change watcher (fires every 0.3 s on the main run loop)
        self._layer_sig = self._compute_layer_sig(self.layers)
        self._path_sig  = self._compute_path_sig(self.layers)
        self._timer = NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            0.3, True, lambda t: self._check_layer_change()
        )

        print(f"Dialog opened for {title}.")

    # ── Layer watcher ──────────────────────────────────────────────────────

    def _compute_layer_sig(self, layers):
        """Stable fingerprint for a list of layers (glyph name + master ID)."""
        return frozenset(
            (l.parent.name, l.associatedMasterId) for l in layers
        )

    def _compute_path_sig(self, layers):
        """Fingerprint of all node and anchor positions — used to detect manual edits."""
        parts = []
        for l in layers:
            try:
                for p in l.paths:
                    for n in p.nodes:
                        parts.append(int(round(n.position.x)))
                        parts.append(int(round(n.position.y)))
                for a in l.anchors:
                    parts.append(int(round(a.position.x)))
                    parts.append(int(round(a.position.y)))
            except Exception:
                pass
        return hash(tuple(parts))

    def _check_manual_edit(self):
        """If the user moved nodes by hand, adopt the current outline as the new
        baseline so the next _apply() won't wipe the manual change."""
        if self._path_sig is None:
            return
        current_sig = self._compute_path_sig(self.layers)
        if current_sig == self._path_sig:
            return
        # Manual edit detected → snapshot the current state and reset offsets to 0,
        # so subsequent adjustments build on the hand-edited outline.
        self._save()
        self.value   = 0
        self.value_y = 0
        self.w.field.set("0")
        self._sync_slider()
        self.w.field_y.set("0")
        self._sync_slider_y()
        self.width_pct = 100.0
        self._sync_width_ui()
        self._path_sig = self._compute_path_sig(self.layers)
        print("Manual outline edit detected — new baseline snapshot taken.")

    def _get_current_layers(self):
        """Return the layers that should currently be active."""
        try:
            layers = list(self.font.selectedLayers or [])
            if not layers and self.font.currentTab:
                layer = self.font.currentTab.activeLayer()
                if layer:
                    layers = [layer]
        except Exception:
            layers = []
        return layers

    def _check_layer_change(self):
        new_layers = self._get_current_layers()
        if not new_layers:
            return
        new_sig = self._compute_layer_sig(new_layers)
        if new_sig == self._layer_sig:
            # Same selection — watch for manual node edits on the active glyph(s)
            self._check_manual_edit()
            return

        # Reset the old layers to their original state
        self._restore_pristine()
        self._redraw()

        # Switch to the new selection and apply current values immediately
        self.layers     = new_layers
        self._layer_sig = new_sig
        self._save()
        self._apply()

        # Update window title
        if len(self.layers) == 1:
            new_title = f"CAPE Weightor: {self.layers[0].parent.name}"
        else:
            new_title = f"CAPE Weightor: {len(self.layers)} Glyphs"
        self.w.getNSWindow().setTitle_(new_title)

    # ── Mode (Weight / Width) ────────────────────────────────────────────────

    def _vertical_stem_metrics(self):
        """List of (font.stems index, name) for the font's vertical stems."""
        out = []
        try:
            for i, m in enumerate(self.font.stems):
                if not m.horizontal:
                    out.append((i, m.name or f"vStem{i}"))
        except Exception:
            pass
        return out

    def _resolve_master(self, layer):
        """Best-effort master for a layer, with a font-level fallback."""
        m = None
        try:
            m = layer.associatedMaster
        except Exception:
            m = None
        if m is None:
            try:
                m = layer.master
            except Exception:
                m = None
        if m is None:
            try:
                m = self.font.masters[0]
            except Exception:
                m = None
        return m

    def _stem_value(self, master, global_idx):
        """Read the stem value at font.stems[global_idx] from a master, robustly.
        Returns a float, or None if it cannot be determined."""
        if master is None or global_idx is None:
            return None
        try:
            stems = master.stems
        except Exception:
            stems = None
        if not stems:
            return None
        try:
            if not (0 <= global_idx < len(stems)):
                return None
            raw = stems[global_idx]
        except Exception:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            # Some Glyphs versions return objects rather than plain numbers
            for attr in ("value", "size", "position"):
                v = getattr(raw, attr, None)
                if v is not None:
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        pass
        return None

    def _stem_value_for_layer(self, layer, global_idx):
        """Nominal vertical-stem value of the layer's own master at font.stems[idx]."""
        v = self._stem_value(self._resolve_master(layer), global_idx)
        return v if v is not None else 0.0

    def _italic_angle(self, master):
        """Italic angle (degrees) of a master, 0.0 for upright/unknown."""
        try:
            return float(master.italicAngle or 0.0)
        except Exception:
            return 0.0

    def _update_mode_ui(self):
        """Show the control set for the active mode, hide the other."""
        is_weight = (self.mode != "width")
        for c in self._weight_controls:
            c.show(is_weight)
        for c in self._width_controls:
            c.show(not is_weight)

    def _mode_changed(self, sender):
        self.mode = "width" if int(sender.get()) == 1 else "weight"
        self._update_mode_ui()
        self._apply()

    # Width controls
    def _sync_width_slider(self):
        self.w.wmode_slider.set(max(50, min(150, self.width_pct)))

    def _sync_width_ui(self):
        self.w.wmode_field.set(str(int(round(self.width_pct))))
        self._sync_width_slider()

    def _width_minus(self, _):
        self.width_pct -= self._current_step()
        self._sync_width_ui()
        self._apply()

    def _width_plus(self, _):
        self.width_pct += self._current_step()
        self._sync_width_ui()
        self._apply()

    def _width_field_changed(self, sender):
        try:
            self.width_pct = float(sender.get())
            self._sync_width_slider()
            self._apply()
        except ValueError:
            pass

    def _width_slider_changed(self, sender):
        self.width_pct = float(round(sender.get()))
        self.w.wmode_field.set(str(int(self.width_pct)))
        self._apply()

    def _width_stem_changed(self, _):
        sel = self.w.wmode_stem.get()
        if 0 <= sel < len(self._vstem_list):
            self.width_stem_idx = self._vstem_list[sel][0]
        self._apply()

    def _width_italic_toggled(self, _):
        self._apply()

    def _weight_italic_toggled(self, _):
        self._apply()

    def _width_adj_sb_toggled(self, _):
        self._apply()

    def _reset_width_slider(self):
        self.width_pct = 100.0
        self._sync_width_ui()
        self._apply()

    # ── Preferences ────────────────────────────────────────────────────────

    def _load_prefs(self):
        saved_value      = Glyphs.defaults.get(PREF_VALUE)
        saved_value_y    = Glyphs.defaults.get(PREF_VALUE_Y)
        saved_pos        = Glyphs.defaults.get(PREF_POS)
        saved_keep         = Glyphs.defaults.get(PREF_KEEP)
        saved_sync         = Glyphs.defaults.get(PREF_SYNC)
        saved_preserve_h   = Glyphs.defaults.get(PREF_PRESERVE_H)
        saved_strength     = Glyphs.defaults.get(PREF_STRENGTH)
        saved_move_anchors = Glyphs.defaults.get(PREF_MOVE_ANCHORS)

        if saved_value is not None:
            self.value = int(saved_value)
            self.w.field.set(str(self.value))
            self._sync_slider()

        if saved_value_y is not None:
            self.value_y = int(saved_value_y)
            self.w.field_y.set(str(self.value_y))
            self._sync_slider_y()

        pos_str = str(saved_pos) if saved_pos is not None else "50"
        self.w.pos_field.set(pos_str)
        try:
            self.w.pos_slider.set(max(0, min(100, float(pos_str))))
        except ValueError:
            self.w.pos_slider.set(50)

        if saved_keep is not None:
            self.w.cleanup.set(bool(saved_keep))

        if saved_sync is not None:
            self.w.xy_sync.set(bool(saved_sync))

        # Default True — only override when an explicit False has been saved
        if saved_preserve_h is not None:
            self.w.preserve_h.set(bool(saved_preserve_h))

        if saved_strength is not None:
            val = max(0, min(100, int(saved_strength)))
            self.w.strength_slider.set(val)
            self.w.strength_field.set(str(val))

        # Grey out strength controls when preserve_h is off
        ph_on = bool(self.w.preserve_h.get())
        self.w.strength_slider.enable(ph_on)
        self.w.strength_field.enable(ph_on)

        if saved_move_anchors is not None:
            self.w.move_anchors.set(bool(saved_move_anchors))

        saved_adj_sb = Glyphs.defaults.get(PREF_ADJ_SB)
        if saved_adj_sb is not None:
            self.w.adjust_sb.set(bool(saved_adj_sb))

        saved_preserve_w = Glyphs.defaults.get(PREF_PRESERVE_W)
        if saved_preserve_w is not None:
            self.w.preserve_w.set(bool(saved_preserve_w))
        self.w.adjust_sb.enable(not bool(self.w.preserve_w.get()))

        # Width mode
        saved_width_pct = Glyphs.defaults.get(PREF_WIDTH_PCT)
        if saved_width_pct is not None:
            try:
                self.width_pct = float(saved_width_pct)
            except (TypeError, ValueError):
                self.width_pct = 100.0
        self._sync_width_ui()

        saved_width_stem = Glyphs.defaults.get(PREF_WIDTH_STEM)
        if saved_width_stem is not None:
            try:
                gidx = int(saved_width_stem)
                for pos, (g, _name) in enumerate(self._vstem_list):
                    if g == gidx:
                        self.width_stem_idx = g
                        self.w.wmode_stem.set(pos)
                        break
            except (TypeError, ValueError):
                pass

        saved_keep_ital = Glyphs.defaults.get(PREF_W_ITALIC)
        if self._has_italic and saved_keep_ital is not None:
            self.w.wmode_italic.set(bool(saved_keep_ital))

        saved_keep_ital_w = Glyphs.defaults.get(PREF_KEEP_ITAL_W)
        if self._has_italic and saved_keep_ital_w is not None:
            self.w.weight_italic.set(bool(saved_keep_ital_w))

        saved_w_adj_sb = Glyphs.defaults.get(PREF_W_ADJ_SB)
        if saved_w_adj_sb is not None:
            self.w.wmode_adj_sb.set(bool(saved_w_adj_sb))

        saved_mode = Glyphs.defaults.get(PREF_MODE)
        if saved_mode in ("weight", "width"):
            self.mode = saved_mode
            self.w.mode_seg.set(1 if saved_mode == "width" else 0)
        self._update_mode_ui()

        self._apply()

    def _save_prefs(self):
        Glyphs.defaults[PREF_VALUE]      = self.value
        Glyphs.defaults[PREF_VALUE_Y]    = self.value_y
        Glyphs.defaults[PREF_POS]        = self.w.pos_field.get()
        Glyphs.defaults[PREF_KEEP]         = bool(self.w.cleanup.get())
        Glyphs.defaults[PREF_SYNC]         = bool(self.w.xy_sync.get())
        Glyphs.defaults[PREF_PRESERVE_H]   = bool(self.w.preserve_h.get())
        Glyphs.defaults[PREF_STRENGTH]     = int(self.w.strength_slider.get())
        Glyphs.defaults[PREF_MOVE_ANCHORS] = bool(self.w.move_anchors.get())
        Glyphs.defaults[PREF_ADJ_SB]       = bool(self.w.adjust_sb.get())
        Glyphs.defaults[PREF_PRESERVE_W]   = bool(self.w.preserve_w.get())
        Glyphs.defaults[PREF_MODE]         = self.mode
        Glyphs.defaults[PREF_WIDTH_PCT]    = self.width_pct
        Glyphs.defaults[PREF_W_ITALIC]     = bool(self.w.wmode_italic.get())
        Glyphs.defaults[PREF_KEEP_ITAL_W]   = bool(self.w.weight_italic.get())
        Glyphs.defaults[PREF_W_ADJ_SB]      = bool(self.w.wmode_adj_sb.get())
        if self.width_stem_idx is not None:
            Glyphs.defaults[PREF_WIDTH_STEM] = self.width_stem_idx
        nswin = self.w.getNSWindow()
        if nswin:
            o = nswin.frame().origin
            Glyphs.defaults[PREF_WIN_POS] = f"{int(o.x)},{int(o.y)}"

    # ── Copy / Paste parameters ─────────────────────────────────────────────

    def _copy_params(self, _):
        params = {
            "value":               self.value,
            "valueY":              self.value_y,
            "position":            self.w.pos_field.get(),
            "keepCompatible":      bool(self.w.cleanup.get()),
            "preserveHeight":      bool(self.w.preserve_h.get()),
            "preserveStrength":    int(self.w.strength_slider.get()),
            "moveAnchors":         bool(self.w.move_anchors.get()),
            "adjustSidebearings":  bool(self.w.adjust_sb.get()),
            "preserveWidth":       bool(self.w.preserve_w.get()),
            "mode":                self.mode,
            "widthPct":            self.width_pct,
            "widthStemIdx":        self.width_stem_idx,
            "widthKeepItalic":     bool(self.w.wmode_italic.get()),
            "weightKeepItalic":    bool(self.w.weight_italic.get()),
            "widthAdjustSidebearings": bool(self.w.wmode_adj_sb.get()),
        }
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(json.dumps(params), NSPasteboardTypeString)
        print(f"Parameters copied: {params}")

    def _paste_params(self, _):
        pb  = NSPasteboard.generalPasteboard()
        raw = pb.stringForType_(NSPasteboardTypeString)
        if not raw:
            print("Clipboard is empty.")
            return
        try:
            params = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as e:
            print(f"Could not read parameters from clipboard: {e}")
            return

        self.value = int(params.get("value", 0))
        self.w.field.set(str(self.value))
        self._sync_slider()

        self.value_y = int(params.get("valueY", 0))
        self.w.field_y.set(str(self.value_y))
        self._sync_slider_y()

        pos_str = str(params.get("position", "50"))
        self.w.pos_field.set(pos_str)
        try:
            self.w.pos_slider.set(max(0, min(100, float(pos_str))))
        except ValueError:
            self.w.pos_slider.set(50)

        self.w.cleanup.set(bool(params.get("keepCompatible", True)))

        ph = bool(params.get("preserveHeight", True))
        self.w.preserve_h.set(ph)
        strength = max(0, min(100, int(params.get("preserveStrength", 100))))
        self.w.strength_slider.set(strength)
        self.w.strength_field.set(str(strength))
        self.w.strength_slider.enable(ph)
        self.w.strength_field.enable(ph)

        self.w.move_anchors.set(bool(params.get("moveAnchors", True)))
        self.w.adjust_sb.set(bool(params.get("adjustSidebearings", True)))
        pw = bool(params.get("preserveWidth", False))
        self.w.preserve_w.set(pw)
        self.w.adjust_sb.enable(not pw)

        try:
            self.width_pct = float(params.get("widthPct", 100.0))
        except (TypeError, ValueError):
            self.width_pct = 100.0
        self._sync_width_ui()

        wsi = params.get("widthStemIdx", None)
        if wsi is not None:
            try:
                gidx = int(wsi)
                for pos, (g, _name) in enumerate(self._vstem_list):
                    if g == gidx:
                        self.width_stem_idx = g
                        self.w.wmode_stem.set(pos)
                        break
            except (TypeError, ValueError):
                pass

        if self._has_italic and "widthKeepItalic" in params:
            self.w.wmode_italic.set(bool(params.get("widthKeepItalic")))
        if self._has_italic and "weightKeepItalic" in params:
            self.w.weight_italic.set(bool(params.get("weightKeepItalic")))
        if "widthAdjustSidebearings" in params:
            self.w.wmode_adj_sb.set(bool(params.get("widthAdjustSidebearings")))

        mode = params.get("mode", "weight")
        if mode in ("weight", "width"):
            self.mode = mode
            self.w.mode_seg.set(1 if mode == "width" else 0)
        self._update_mode_ui()

        self._apply()
        print(f"Parameters pasted: {params}")

    # ── Data backup ────────────────────────────────────────────────────────

    def _capture_layer(self, layer):
        """Snapshot a single layer's outlines, metrics, anchors and guides."""
        # Detect which anchors sit exactly on a node (path_idx, node_idx)
        anchor_nodes = {}
        for anchor in layer.anchors:
            ax, ay = round(anchor.position.x), round(anchor.position.y)
            for pi, path in enumerate(layer.paths):
                for ni, node in enumerate(path.nodes):
                    if round(node.position.x) == ax and round(node.position.y) == ay:
                        anchor_nodes[anchor.name] = (pi, ni)
                        break
                else:
                    continue
                break

        bg     = layer.background
        bounds = layer.bounds
        return {
            "paths":        [p.copy() for p in layer.paths],
            "anchors":      [(a.name, a.position.x, a.position.y) for a in layer.anchors],
            "anchor_nodes": anchor_nodes,
            "guides":       [(g.position.x, g.position.y, g.angle, g.name)
                             for g in layer.guides],
            "lsb":          layer.LSB,
            "rsb":          layer.RSB,
            "width":        layer.width,
            "bounds_x":     bounds.origin.x,
            "bounds_w":     bounds.size.width,
            "bg_paths":     [p.copy() for p in bg.paths] if bg else [],
        }

    def _save(self):
        self._orig = {}
        for layer in self.layers:
            self._orig[layer] = self._capture_layer(layer)
            # Capture the pristine original only once per layer — this is the
            # state Reset and Cancel restore to, regardless of later snapshots.
            if layer not in self._pristine:
                self._pristine[layer] = self._capture_layer(layer)

    def _restore(self, source=None):
        src = source if source is not None else self._orig
        for layer in self.layers:
            if layer not in src:
                continue
            data = src[layer]
            for path in list(layer.paths):
                layer.shapes.remove(path)
            for p in data["paths"]:
                layer.shapes.append(p.copy())
            layer.width = data["width"]
            self._restore_anchors(layer, src)
            self._restore_guides(layer, src)
            bg = layer.background
            if bg and data["bg_paths"]:
                for path in list(bg.paths):
                    bg.shapes.remove(path)
                for p in data["bg_paths"]:
                    bg.shapes.append(p.copy())

    def _restore_pristine(self):
        """Restore the true original state captured before Weightor touched anything."""
        self._restore(self._pristine)

    def _restore_anchors(self, layer, source=None):
        data = (source if source is not None else self._orig)[layer]
        layer.anchors = []
        for name, x, y in data["anchors"]:
            a = GSAnchor()
            a.name = name
            a.x = x
            a.y = y
            layer.anchors.append(a)

    def _restore_guides(self, layer, source=None):
        data = (source if source is not None else self._orig)[layer]
        layer.guides = []
        for x, y, angle, name in data["guides"]:
            g = GSGuide()
            g.position = NSPoint(x, y)
            g.angle = angle
            g.name = name or ""
            layer.guides.append(g)

    # ── Apply (dispatch by mode) ─────────────────────────────────────────────

    def _apply(self):
        if self.mode == "width":
            self._apply_width()
        else:
            self._apply_weight()

    def _place_anchors(self, layer, data, orig_x, orig_w):
        """Move anchors to follow the horizontal change (proportional, with
        node-snapping), keeping their original Y. Honors the Move anchors box."""
        if not self.w.move_anchors.get():
            self._restore_anchors(layer)
            return
        final_bbox   = layer.bounds
        orig_map     = {name: (ax, ay) for name, ax, ay in data["anchors"]}
        anchor_nodes = data.get("anchor_nodes", {})
        for anchor in layer.anchors:
            if anchor.name not in orig_map:
                continue
            if anchor.name in anchor_nodes:
                pi, ni = anchor_nodes[anchor.name]
                try:
                    node = layer.paths[pi].nodes[ni]
                    anchor.x = node.position.x
                    anchor.y = node.position.y
                    continue
                except (IndexError, AttributeError):
                    pass
            orig_ax, orig_ay = orig_map[anchor.name]
            if orig_w > 0 and final_bbox.size.width > 0:
                s_x      = final_bbox.size.width / orig_w
                anchor.x = final_bbox.origin.x + (orig_ax - orig_x) * s_x
            else:
                anchor.x = orig_ax
            anchor.y = orig_ay

    # ── Width logic (condense / expand, weight preserved) ────────────────────

    def _apply_width(self):
        self._restore()
        if abs(self.width_pct - 100.0) < 1e-6:
            self._redraw()
            self._path_sig = self._compute_path_sig(self.layers)
            return

        OffsetCurve = objc.lookUpClass("GlyphsFilterOffsetCurve")
        keep      = bool(self.w.cleanup.get())
        keep_ital = bool(self.w.wmode_italic.get())
        f         = self.width_pct / 100.0

        for layer in self.layers:
            data = self._orig[layer]

            # Italic slant of this layer's master (0 when disabled / upright).
            angle = self._italic_angle(self._resolve_master(layer)) if keep_ital else 0.0
            t     = math.tan(math.radians(angle)) if abs(angle) > 1e-6 else 0.0

            # Original (slanted) bbox — reference for anchor placement.
            sl_bounds = layer.bounds
            osl_x = sl_bounds.origin.x
            osl_w = sl_bounds.size.width

            # 0. Unslant to the upright coordinate system (identity when t == 0).
            #    Scaling + stem compensation happen on truly vertical stems, which
            #    keeps the offset geometrically clean and the slant angle intact.
            if t:
                layer.applyTransform((1, 0, -t, 1, 0, 0))

            up_bounds = layer.bounds
            up_x = up_bounds.origin.x
            up_w = up_bounds.size.width

            n = self._stem_value_for_layer(layer, self.width_stem_idx) \
                if self.width_stem_idx is not None else 0.0

            do_scale        = up_w > 0
            s               = 1.0
            offset_per_side = 0.0
            if do_scale:
                W        = up_w
                W_target = W * f
                if n <= 0:
                    # No usable stem reference → plain scale (weight will change).
                    s = f
                elif (W - n) > 0:
                    # Closed form: after stem compensation the outer width is
                    # exactly W_target and the vertical stem is restored to n.
                    s = (W_target - n) / (W - n)
                    if s < 0.05:
                        s = 0.05  # guard near-all-stem glyphs from collapsing
                    offset_per_side = n * (1.0 - s) / 2.0
                else:
                    # Essentially all stem (l, i, |) — cannot narrow without
                    # changing weight; leave untouched (still reslant below).
                    do_scale = False

            if do_scale:
                # 1. Horizontal scale, upright left edge pinned
                tx = up_x * (1.0 - s)
                layer.applyTransform((s, 0, 0, 1, tx, 0))

                # 2. Restore vertical-stem thickness with an X-only offset.
                #    offsetY = 0 leaves horizontal stems (crossbars) untouched.
                if abs(offset_per_side) > 1e-6:
                    applied = False
                    try:
                        OffsetCurve.offsetLayer_offsetX_offsetY_makeStroke_autoStroke_position_metrics_error_shadow_capStyleStart_capStyleEnd_keepCompatibleOutlines_(
                            layer, offset_per_side, 0.0,
                            False, False, 0.5, None, None, None, 0, 0, keep
                        )
                        applied = True
                    except AttributeError:
                        pass
                    if not applied:
                        try:
                            OffsetCurve.offsetLayer_offsetX_offsetY_makeStroke_position_(
                                layer, offset_per_side, 0.0, False, 0.5
                            )
                        except Exception as e:
                            print(f"Width offset error ({layer.parent.name}): {e}")

            # 3. Reslant back to the original italic angle (identity when t == 0).
            if t:
                layer.applyTransform((1, 0, t, 1, 0, 0))

            if do_scale:
                # 4. Sidebearings
                if self.w.wmode_adj_sb.get():
                    # Keep LSB and RSB at their original values — only the outline
                    # condenses/expands, spacing stays where it was.
                    layer.LSB = data["lsb"]
                    layer.RSB = data["rsb"]
                else:
                    # Default: scale spacing with the glyph
                    layer.LSB = data["lsb"] * f
                    layer.RSB = data["rsb"] * f

            # 5. Anchors follow the horizontal change; guides restored
            self._place_anchors(layer, data, osl_x, osl_w)
            self._restore_guides(layer)

        self._redraw()
        self._path_sig = self._compute_path_sig(self.layers)
        print(f"Width: {self.width_pct:.0f}%  (scale {f:.3f})  keep_italic={keep_ital}")

    # ── Contour classification + distributed offset ──────────────────────────

    def _is_off_curve(self, node):
        """Robust off-curve detection across Glyphs versions."""
        try:
            t = node.type
        except Exception:
            return False
        try:
            if t == GSOFFCURVE:
                return True
        except NameError:
            pass
        try:
            return str(t).lower() == "offcurve"
        except Exception:
            return False

    def _path_is_closed(self, path):
        """Return True if the path is closed, False if open. Falls back to a
        first/last-node coincidence test on Glyphs builds that don't expose
        the .closed attribute."""
        try:
            return bool(path.closed)
        except AttributeError:
            pass
        try:
            nodes = list(path.nodes)
            if len(nodes) < 2:
                return False
            a, b = nodes[0].position, nodes[-1].position
            return abs(a.x - b.x) < 0.01 and abs(a.y - b.y) < 0.01
        except Exception:
            return True

    def _inside_point_for_path(self, path):
        """Return an NSPoint usable as a *classification reference* for this
        path, or None if no useful point can be found.

        For **closed** paths the point lies inside the enclosed area (strategy
        below). For **open** paths there is no enclosure, but we still need to
        decide whether the path sits inside another (closed) contour — so we
        return a point ON the path itself (a mid-stream on-curve node). The
        nesting test in `_classify_contours` then checks how many OTHER paths
        enclose this point.

        Closed-path strategy: for every on-curve node, take the tangent from
        its previous to its next neighbour (those may be off-curve handles,
        which is fine for the direction) and step ±ε along its perpendicular.
        The side that lands inside the path's bezierPath is the interior side.
        This avoids two traps the simpler "edge midpoint" approach falls into
        for ring shapes such as an O:
          • chord midpoints between an anchor and its tangent handle lie
            *outside* the curve;
          • a bbox-centre fallback lands in the counter, inside the *inner*
            contour, which would flip the classification.
        """
        bp = path.bezierPath
        if bp is None:
            return None
        nodes = list(path.nodes)
        n = len(nodes)
        if n < 2:
            return None

        # Open paths: take a midway on-curve node as the reference point.
        if not self._path_is_closed(path):
            on_curve = [nn for nn in nodes if not self._is_off_curve(nn)]
            picks = on_curve if on_curve else nodes
            mid = picks[len(picks) // 2]
            return NSPoint(mid.position.x, mid.position.y)

        # Closed paths: tangent + perpendicular ε offset, both directions.
        eps = 1.0
        for i, node in enumerate(nodes):
            if self._is_off_curve(node):
                continue
            prev_n = nodes[(i - 1) % n]
            next_n = nodes[(i + 1) % n]
            dx = next_n.position.x - prev_n.position.x
            dy = next_n.position.y - prev_n.position.y
            L = (dx * dx + dy * dy) ** 0.5
            if L < 1e-6:
                continue
            # Perpendicular unit vector
            px, py = -dy / L, dx / L
            nx, ny = node.position.x, node.position.y
            for sign in (1.0, -1.0):
                cand = NSPoint(nx + sign * eps * px, ny + sign * eps * py)
                try:
                    if bp.containsPoint_(cand):
                        return cand
                except Exception:
                    pass

        # No bbox-centre fallback on purpose — for ring-shaped outers it would
        # land inside a counter and flip the classification. Returning None
        # makes the caller treat this path as outer (safe default).
        return None

    def _classify_contours(self, layer):
        """Return (outer_paths, inner_paths) using even-odd containment.
        A path is INNER iff an odd number of *other* paths enclose its interior."""
        paths = list(layer.paths)
        if not paths:
            return [], []

        inside_pts = [self._inside_point_for_path(p) for p in paths]
        bezier_ps  = []
        for p in paths:
            try:
                bezier_ps.append(p.bezierPath)
            except Exception:
                bezier_ps.append(None)

        outer, inner = [], []
        for i, path in enumerate(paths):
            point = inside_pts[i]
            if point is None:
                # Classification failed → treat as outer (safe default, matches
                # the pre-distribution behaviour for this path).
                outer.append(path)
                continue
            nesting = 0
            for j, other_bp in enumerate(bezier_ps):
                if j == i or other_bp is None:
                    continue
                try:
                    if other_bp.containsPoint_(point):
                        nesting += 1
                except Exception:
                    pass
            if nesting % 2 == 0:
                outer.append(path)
            else:
                inner.append(path)
        return outer, inner

    def _offset_layer_distributed(self, layer, offset_x, offset_y, keep, p):
        """Apply OffsetCurve with true outer / inner distribution.

        p = 0   → all weight on outer (silhouette grows, counters unchanged)
        p = 0.5 → symmetric (== classic OffsetCurve with position 0.5)
        p = 1   → all weight on inner (silhouette unchanged, counters shrink)

        Total stem growth stays at 2·offset regardless of p.
        """
        if abs(offset_x) < 1e-6 and abs(offset_y) < 1e-6:
            return True
        if not list(layer.paths):
            return True

        outer_paths, inner_paths = self._classify_contours(layer)
        outer_originals = [pp.copy() for pp in outer_paths]
        inner_originals = [pp.copy() for pp in inner_paths]

        # Per-group offsets. The doubling makes the sum equal 2·offset at any p,
        # matching the per-side movement OffsetCurve produces at position 0.5.
        f_outer = 2.0 * (1.0 - p)
        f_inner = 2.0 * p

        OffsetCurve = objc.lookUpClass("GlyphsFilterOffsetCurve")

        def _do_offset(ox, oy):
            try:
                OffsetCurve.offsetLayer_offsetX_offsetY_makeStroke_autoStroke_position_metrics_error_shadow_capStyleStart_capStyleEnd_keepCompatibleOutlines_(
                    layer, ox, oy,
                    False, False, 0.5, None, None, None, 0, 0, keep
                )
                return True
            except AttributeError:
                pass
            try:
                OffsetCurve.offsetLayer_offsetX_offsetY_makeStroke_position_(
                    layer, ox, oy, False, 0.5
                )
                return True
            except Exception as e:
                print(f"Offset error ({layer.parent.name}): {e}")
                return False

        def _process(originals, fx, fy):
            """Replace layer.paths with `originals`, offset, return copies of the result."""
            for pp in list(layer.paths):
                layer.shapes.remove(pp)
            if not originals:
                return []
            for pp in originals:
                layer.shapes.append(pp.copy())
            if abs(fx) > 1e-6 or abs(fy) > 1e-6:
                if not _do_offset(fx, fy):
                    return None  # signals failure
            return [pp.copy() for pp in layer.paths]

        offset_outer = _process(outer_originals, offset_x * f_outer, offset_y * f_outer)
        if offset_outer is None:
            return False
        offset_inner = _process(inner_originals, offset_x * f_inner, offset_y * f_inner)
        if offset_inner is None:
            return False

        # Combine: outer first, then inner. Original interleaved order is not
        # strictly preserved — acceptable for live preview; document the caveat.
        for pp in list(layer.paths):
            layer.shapes.remove(pp)
        for pp in offset_outer:
            layer.shapes.append(pp.copy())
        for pp in offset_inner:
            layer.shapes.append(pp.copy())
        return True

    # ── Bold logic ─────────────────────────────────────────────────────────

    def _apply_weight(self):
        self._restore()
        if self.value == 0 and self.value_y == 0:
            self._redraw()
            self._path_sig = self._compute_path_sig(self.layers)
            return

        keep      = bool(self.w.cleanup.get())
        keep_ital = bool(self.w.weight_italic.get())
        try:
            pos = max(0.0, min(1.0, float(self.w.pos_field.get()) / 100.0))
        except ValueError:
            pos = 0.5

        for layer in self.layers:
                data = self._orig[layer]

                # Italic slant of this layer's master (0 when disabled / upright).
                angle = self._italic_angle(self._resolve_master(layer)) if keep_ital else 0.0
                t     = math.tan(math.radians(angle)) if abs(angle) > 1e-6 else 0.0

                # Slanted reference bbox (for anchor placement).
                sl_bounds = layer.bounds
                osl_x = sl_bounds.origin.x
                osl_w = sl_bounds.size.width

                # 0. Unslant to upright space so the offset and rescales operate
                #    on truly vertical / horizontal stems (identity when t == 0).
                if t:
                    layer.applyTransform((1, 0, -t, 1, 0, 0))

                # Upright pre-offset measurements drive preserve-height / preserve-width.
                up_bounds = layer.bounds
                orig_x = up_bounds.origin.x
                orig_y = up_bounds.origin.y
                orig_w = up_bounds.size.width
                orig_h = up_bounds.size.height

                ok = self._offset_layer_distributed(layer, self.value, self.value_y, keep, pos)
                if not ok:
                    if t:
                        layer.applyTransform((1, 0, t, 1, 0, 0))  # reslant before bailing
                    continue

                # Rescale vertically to preserve original height (upright Y unchanged
                # by the shear, so the math is identical with or without italic).
                if self.w.preserve_h.get():
                    nb = layer.bounds
                    if nb.size.height > 0 and orig_h > 0:
                        try:
                            strength = max(0.0, min(1.0, float(self.w.strength_field.get()) / 100.0))
                        except ValueError:
                            strength = 1.0
                        s_full  = orig_h / nb.size.height
                        ty_full = orig_y - nb.origin.y * s_full
                        s  = 1.0 + (s_full  - 1.0) * strength
                        ty =        ty_full          * strength
                        layer.applyTransform((1, 0, 0, s, 0, ty))

                # Preserve outer width: scale the outline back into its original
                # *upright* horizontal extent. After reslant, the original SLANTED
                # outer width is restored too (slant term tan(α)·H is unchanged).
                if self.w.preserve_w.get() and orig_w > 0:
                    nb = layer.bounds
                    if nb.size.width > 0:
                        sx = orig_w / nb.size.width
                        tx = orig_x - nb.origin.x * sx
                        layer.applyTransform((sx, 0, 0, 1, tx, 0))

                # 1. Reslant back to the original italic angle (identity when t == 0).
                if t:
                    layer.applyTransform((1, 0, t, 1, 0, 0))

                # Width / sidebearings
                if self.w.preserve_w.get():
                    layer.width = data["width"]
                elif self.w.adjust_sb.get():
                    layer.LSB = data["lsb"]
                    layer.RSB = data["rsb"]

                # Anchors + guides (use slanted reference bbox)
                self._place_anchors(layer, data, osl_x, osl_w)
                self._restore_guides(layer)

        self._redraw()
        self._path_sig = self._compute_path_sig(self.layers)
        print(f"X: {self.value}  Y: {self.value_y}  Position: {pos:.2f}  keep_italic={keep_ital}")

    def _redraw(self):
        if self.font.currentTab:
            self.font.currentTab.redraw()
            gv = self.font.currentTab.graphicView()
            if gv:
                gv.display()

    # ── Callbacks ──────────────────────────────────────────────────────────

    def _current_step(self):
        shift = NSEvent.modifierFlags() & (1 << 17)  # NSShiftKeyMask
        return STEP_SHIFT if shift else STEP

    # X controls
    def _sync_slider(self):
        r  = max(10, abs(self.value))
        ns = self.w.slider.getNSSlider()
        ns.setMinValue_(-r)
        ns.setMaxValue_(r)
        if r == 10:
            ns.setNumberOfTickMarks_(21)
            ns.setAllowsTickMarkValuesOnly_(True)
        else:
            ns.setNumberOfTickMarks_(0)
            ns.setAllowsTickMarkValuesOnly_(False)
        self.w.slider.set(self.value)
        self.w.label.set(f"X  ±{r}")

    def _mirror_to_y(self):
        """Copy X value to Y when sync is active."""
        if self.w.xy_sync.get():
            self.value_y = self.value
            self.w.field_y.set(str(self.value_y))
            self._sync_slider_y()

    def _minus(self, _):
        self.value -= self._current_step()
        self.w.field.set(str(self.value))
        self._sync_slider()
        self._mirror_to_y()
        self._apply()

    def _plus(self, _):
        self.value += self._current_step()
        self.w.field.set(str(self.value))
        self._sync_slider()
        self._mirror_to_y()
        self._apply()

    def _field_changed(self, sender):
        try:
            self.value = int(sender.get())
            self._sync_slider()
            self._mirror_to_y()
            self._apply()
        except ValueError:
            pass

    def _slider_changed(self, sender):
        self.value = int(round(sender.get()))
        self.w.field.set(str(self.value))
        self._mirror_to_y()
        self._apply()

    # Y controls
    def _sync_slider_y(self):
        r  = max(10, abs(self.value_y))
        ns = self.w.slider_y.getNSSlider()
        ns.setMinValue_(-r)
        ns.setMaxValue_(r)
        if r == 10:
            ns.setNumberOfTickMarks_(21)
            ns.setAllowsTickMarkValuesOnly_(True)
        else:
            ns.setNumberOfTickMarks_(0)
            ns.setAllowsTickMarkValuesOnly_(False)
        self.w.slider_y.set(self.value_y)
        self.w.label_y.set(f"Y  ±{r}")

    def _mirror_to_x(self):
        """Copy Y value to X when sync is active."""
        if self.w.xy_sync.get():
            self.value = self.value_y
            self.w.field.set(str(self.value))
            self._sync_slider()

    def _minus_y(self, _):
        self.value_y -= self._current_step()
        self.w.field_y.set(str(self.value_y))
        self._sync_slider_y()
        self._mirror_to_x()
        self._apply()

    def _plus_y(self, _):
        self.value_y += self._current_step()
        self.w.field_y.set(str(self.value_y))
        self._sync_slider_y()
        self._mirror_to_x()
        self._apply()

    def _field_y_changed(self, sender):
        try:
            self.value_y = int(sender.get())
            self._sync_slider_y()
            self._mirror_to_x()
            self._apply()
        except ValueError:
            pass

    def _slider_y_changed(self, sender):
        self.value_y = int(round(sender.get()))
        self.w.field_y.set(str(self.value_y))
        self._mirror_to_x()
        self._apply()

    def _xy_sync_toggled(self, _):
        """When sync is enabled, immediately align Y to X."""
        if self.w.xy_sync.get():
            self.value_y = self.value
            self.w.field_y.set(str(self.value_y))
            self._sync_slider_y()
            self._apply()

    # Outer/Inner distribution
    def _pos_changed(self, sender):
        self.w.pos_field.set(str(int(round(sender.get()))))
        self._apply()

    def _pos_field_changed(self, sender):
        try:
            val = float(sender.get())
            self.w.pos_slider.set(max(0, min(100, val)))
            self._apply()
        except ValueError:
            pass

    def _cleanup_toggled(self, _):
        self._apply()

    def _preserve_h_toggled(self, _):
        ph_on = bool(self.w.preserve_h.get())
        self.w.strength_slider.enable(ph_on)
        self.w.strength_field.enable(ph_on)
        self._apply()

    def _strength_slider_changed(self, sender):
        self.w.strength_field.set(str(int(round(sender.get()))))
        self._apply()

    def _strength_field_changed(self, sender):
        try:
            val = max(0, min(100, int(float(sender.get()))))
            self.w.strength_slider.set(val)
            self._apply()
        except ValueError:
            pass

    def _move_anchors_toggled(self, _):
        self._apply()

    def _adjust_sb_toggled(self, _):
        self._apply()

    def _preserve_w_toggled(self, _):
        pw_on = bool(self.w.preserve_w.get())
        self.w.adjust_sb.enable(not pw_on)
        self._apply()

    def _reset(self, _):
        self.value   = 0
        self.value_y = 0
        self.w.field.set("0")
        self._sync_slider()
        self.w.field_y.set("0")
        self._sync_slider_y()
        self.w.pos_slider.set(50)
        self.w.pos_field.set("50")
        self.width_pct = 100.0
        self._sync_width_ui()
        self._restore_pristine()   # back to the true original, discarding manual edits
        self._save()               # working baseline = original again
        self._redraw()
        self._path_sig = self._compute_path_sig(self.layers)

    def _reset_x_slider(self):
        self.value = 0
        self.w.field.set("0")
        self._sync_slider()
        self._mirror_to_y()
        self._apply()

    def _reset_y_slider(self):
        self.value_y = 0
        self.w.field_y.set("0")
        self._sync_slider_y()
        self._mirror_to_x()
        self._apply()

    def _reset_pos_slider(self):
        self.w.pos_slider.set(50)
        self.w.pos_field.set("50")
        self._apply()

    def _reset_strength_slider(self):
        self.w.strength_slider.set(100)
        self.w.strength_field.set("100")
        self._apply()

    def _on_close(self, sender):
        self._timer.invalidate()
        if not self._committed:
            # Cancel: restore the true original (incl. discarding any manual edits
            # made during the session), but keep the UI values as reference for
            # the next time the dialog opens.
            self._restore_pristine()
            self._redraw()
        self._save_prefs()

    def _done(self, _):
        self._committed = True
        self._save_prefs()
        self.w.close()


# Bring existing window to front if already running, otherwise start fresh
_existing_win = None
for _win in NSApp.windows():
    try:
        if _win.isVisible() and (_win.title() or "").startswith("CAPE Weightor"):
            _existing_win = _win
            break
    except Exception:
        pass

if _existing_win:
    _existing_win.makeKeyAndOrderFront_(None)
else:
    _dialog = BolderDialog()
    try:
        Glyphs.scriptStorage["_bolderDialog"] = _dialog
    except AttributeError:
        pass
