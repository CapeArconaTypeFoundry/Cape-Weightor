#MenuTitle: CAPE Weightor
# -*- coding: utf-8 -*-
#
# CAPE Weightor
# Version 1.100 - 25-May-2026
#
# Cape Arcona Type Foundry
# Written by Thomas Schostok

__doc__ = """
Adjusts the weight of selected glyphs using the OffsetCurve filter. Supports independent X/Y offsets, outer/inner distribution, live preview with automatic glyph switching in the edit tab, and an option to preserve the outer width — the left/right edges stay fixed and the added weight grows inward only (pairs with "Preserve glyph height").
"""

import json
import objc
import vanilla
from AppKit import NSApp, NSClickGestureRecognizer, NSEvent, NSPasteboard, NSPasteboardTypeString, NSScreen, NSTimer
from Foundation import NSObject, NSPoint

STEP       = 1
STEP_SHIFT = 5
WIN_W      = 270
WIN_H      = 412

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
        self._committed = False
        self._save()

        title = (f"CAPE Weightor: {self.layers[0].parent.name}"
                 if len(self.layers) == 1
                 else f"CAPE Weightor: {len(self.layers)} Glyphs")

        # Compute centered position as fallback
        screen = NSScreen.mainScreen().visibleFrame()
        cx = int(screen.origin.x + (screen.size.width  - WIN_W) / 2)
        cy = int(screen.origin.y + (screen.size.height - WIN_H) / 2)

        self.w = vanilla.FloatingWindow((WIN_W, WIN_H), title)

        # ── X offset (vertical stems) ────────────────────────────────────────
        self.w.minus   = vanilla.Button(   (10,  12,  40, 30), "−",                callback=self._minus)
        self.w.field   = vanilla.EditText( (55,  12,  90, 30), "0",                callback=self._field_changed)
        self.w.plus    = vanilla.Button(   (150, 12,  40, 30), "+",                callback=self._plus)
        self.w.label   = vanilla.TextBox(  (196, 18,  65, 18), f"X  ±{STEP}",      sizeStyle="small")

        self.w.hint    = vanilla.TextBox(  (10,  44, 250, 14), "Hold SHIFT for ±5 steps",
                                           sizeStyle="small")

        self.w.slider  = vanilla.Slider(   (10,  62, 250, 20), minValue=-10, maxValue=10, value=0,
                                           tickMarkCount=21, stopOnTickMarks=True,
                                           callback=self._slider_changed)

        # ── Y offset (horizontal strokes, height preserved) ──────────────────
        self.w.minus_y  = vanilla.Button(   (10,  90,  40, 30), "−",               callback=self._minus_y)
        self.w.field_y  = vanilla.EditText( (55,  90,  90, 30), "0",               callback=self._field_y_changed)
        self.w.plus_y   = vanilla.Button(   (150, 90,  40, 30), "+",               callback=self._plus_y)
        self.w.label_y  = vanilla.TextBox(  (196, 96,  65, 18), f"Y  ±{STEP}",     sizeStyle="small")

        self.w.slider_y = vanilla.Slider(   (10, 124, 250, 20), minValue=-10, maxValue=10, value=0,
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

        self.w.hint_y   = vanilla.TextBox(  (10, 148, 250, 14), "Hold SHIFT for ±5 steps",

                                            sizeStyle="small")

        self.w.xy_sync  = vanilla.CheckBox( (10, 166, 250, 20), "Sync X and Y",
                                            value=False, callback=self._xy_sync_toggled,
                                            sizeStyle="small")

        # ── Weight distribution (outer / inner edge of strokes) ─────────────
        self.w.pos_lbl_l  = vanilla.TextBox(  (10,  191,  35, 14), "Outer", sizeStyle="small")
        self.w.pos_slider = vanilla.Slider(   (48,  190, 118, 18), minValue=0, maxValue=97, value=50,
                                              callback=self._pos_changed)
        self.w.pos_field  = vanilla.EditText( (170, 187,  42, 22), "50",
                                              callback=self._pos_field_changed)
        self.w.pos_lbl_r  = vanilla.TextBox(  (216, 191,  38, 14), "Inner", sizeStyle="small")

        # ── Options ─────────────────────────────────────────────────────────
        self.w.cleanup      = vanilla.CheckBox( (10, 218, 250, 20), "Keep node count (no new nodes)",
                                                value=True, callback=self._cleanup_toggled,
                                                sizeStyle="small")
        self.w.preserve_h      = vanilla.CheckBox( (10, 240, 250, 20), "Preserve glyph height",
                                                   value=True, callback=self._preserve_h_toggled,
                                                   sizeStyle="small")
        self.w.strength_lbl    = vanilla.TextBox(  (22,  264,  58, 14), "Strength",  sizeStyle="small")
        self.w.strength_slider = vanilla.Slider(   (80,  263, 130, 18), minValue=0, maxValue=100, value=100,
                                                   callback=self._strength_slider_changed)
        self.w.strength_field  = vanilla.EditText( (214, 260,  36, 22), "100",
                                                   callback=self._strength_field_changed)
        self.w.strength_pct    = vanilla.TextBox(  (252, 264,  16, 14), "%",         sizeStyle="small")

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

        self.w.move_anchors    = vanilla.CheckBox( (10, 284, 250, 20), "Move anchors with glyph",
                                                   value=True, callback=self._move_anchors_toggled,
                                                   sizeStyle="small")
        self.w.adjust_sb       = vanilla.CheckBox( (10, 306, 250, 20), "Adjust sidebearings",
                                                   value=True, callback=self._adjust_sb_toggled,
                                                   sizeStyle="small")
        self.w.preserve_w      = vanilla.CheckBox( (10, 328, 250, 20), "Preserve outer width (grow inward)",
                                                   value=False, callback=self._preserve_w_toggled,
                                                   sizeStyle="small")

        # ── Copy / Paste parameters ─────────────────────────────────────────
        self.w.copy_btn  = vanilla.Button( (10,  356, 120, 22), "Copy Parameters",  callback=self._copy_params)
        self.w.paste_btn = vanilla.Button( (140, 356, 120, 22), "Paste Parameters", callback=self._paste_params)

        # ── Reset / Done ─────────────────────────────────────────────────────
        self.w.reset = vanilla.Button( (10,  384, 115, 25), "Reset (0)", callback=self._reset)
        self.w.done  = vanilla.Button( (140, 384, 120, 25), "Apply",      callback=self._done)
        self.w.setDefaultButton(self.w.done)

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
            return

        # Reset the old layers to their original state
        self._restore()
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
        self._apply()
        print(f"Parameters pasted: {params}")

    # ── Data backup ────────────────────────────────────────────────────────

    def _save(self):
        self._orig = {}
        for layer in self.layers:
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
            self._orig[layer] = {
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

    def _restore(self):
        for layer in self.layers:
            data = self._orig[layer]
            for path in list(layer.paths):
                layer.shapes.remove(path)
            for p in data["paths"]:
                layer.shapes.append(p.copy())
            layer.width = data["width"]
            self._restore_anchors(layer)
            self._restore_guides(layer)
            bg = layer.background
            if bg and data["bg_paths"]:
                for path in list(bg.paths):
                    bg.shapes.remove(path)
                for p in data["bg_paths"]:
                    bg.shapes.append(p.copy())

    def _restore_anchors(self, layer):
        data = self._orig[layer]
        layer.anchors = []
        for name, x, y in data["anchors"]:
            a = GSAnchor()
            a.name = name
            a.x = x
            a.y = y
            layer.anchors.append(a)

    def _restore_guides(self, layer):
        data = self._orig[layer]
        layer.guides = []
        for x, y, angle, name in data["guides"]:
            g = GSGuide()
            g.position = NSPoint(x, y)
            g.angle = angle
            g.name = name or ""
            layer.guides.append(g)

    # ── Bold logic ─────────────────────────────────────────────────────────

    def _apply(self):
        self._restore()
        if self.value == 0 and self.value_y == 0:
            self._redraw()
            return

        OffsetCurve = objc.lookUpClass("GlyphsFilterOffsetCurve")
        keep = bool(self.w.cleanup.get())
        try:
            pos = max(0.01, float(self.w.pos_field.get()) / 100.0)
        except ValueError:
            pos = 0.5

        for layer in self.layers:
                data   = self._orig[layer]
                bounds = layer.bounds
                orig_y = bounds.origin.y
                orig_h = bounds.size.height
                orig_x = bounds.origin.x
                orig_w = bounds.size.width

                applied = False
                try:
                    OffsetCurve.offsetLayer_offsetX_offsetY_makeStroke_autoStroke_position_metrics_error_shadow_capStyleStart_capStyleEnd_keepCompatibleOutlines_(
                        layer, self.value, self.value_y,
                        False, False, pos, None, None, None, 0, 0, keep
                    )
                    applied = True
                except AttributeError:
                    pass

                if not applied:
                    try:
                        OffsetCurve.offsetLayer_offsetX_offsetY_makeStroke_position_(
                            layer, self.value, self.value_y, False, pos
                        )
                        applied = True
                    except Exception as e:
                        print(f"Offset error ({layer.parent.name}): {e}")
                        continue

                # Rescale vertically to preserve original height
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
                # horizontal bounds so the left/right edges stay pinned and the
                # added weight grows inward only.
                if self.w.preserve_w.get() and data["bounds_w"] > 0:
                    nb = layer.bounds
                    if nb.size.width > 0:
                        sx = data["bounds_w"] / nb.size.width
                        tx = data["bounds_x"] - nb.origin.x * sx
                        layer.applyTransform((sx, 0, 0, 1, tx, 0))
                    layer.width = data["width"]
                # Restore sidebearings (skip when user wants natural OffsetCurve spacing)
                elif self.w.adjust_sb.get():
                    layer.LSB = data["lsb"]
                    layer.RSB = data["rsb"]

                # Anchors
                if self.w.move_anchors.get():
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
                else:
                    self._restore_anchors(layer)

                self._restore_guides(layer)

        self._redraw()
        print(f"X: {self.value}  Y: {self.value_y}  Position: {pos:.2f}")

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
        self._restore()
        self._redraw()

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
            # Cancel: restore the glyph but keep the UI values so they're
            # available as reference the next time the dialog opens.
            self._restore()
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
