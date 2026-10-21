"""The Glance translation card - an Apple-flavoured popover.

Rounded corners are done with a native Win32 window region so there is no
transparent-colour fringe.  Everything else is plain Tkinter.
"""

import ctypes
import math
import re
import tkinter as tk
import tkinter.font as tkfont

try:
    from PIL import Image, ImageDraw, ImageTk
    _PIL = True
except Exception:  # noqa: BLE001
    _PIL = False

from config import APP_NAME, AUTHOR_TIP


def _rgba(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (255,)

# Segoe MDL2 Assets glyphs - fallback only, when Pillow is unavailable.
IC_PIN = "\uE718"     # Pin
IC_UNPIN = "\uE77A"   # Unpin
IC_SPEAK = "\uE767"   # Volume

# Icon buttons (speaker + pin). "Geometric Line" handoff: 24x24 viewBox glyph,
# rendered 20px inside a 32px square button. config icon_scale tweaks the size.
_PLACEHOLDER = "翻译中…"   # shown in the CN line while the online sentence is pending
IC_BASE = (32, 32, 9)     # square button (w, h, corner radius)
IC_GLYPH = 21.0 / 32.0    # glyph keyline, px inside the button
IC_STROKE = 2.5           # stroke in the 24-unit viewBox (heavier than the
                          # handoff's 1.75 - reads too faint at this size)

# SVG paths from the handoff (viewBox 0 0 24 24).
_SVG_SPEAK_CONE = ("M13 4.8 L7.6 9.4 H4.4 A1.4 1.4 0 0 0 3 10.8 V13.2 "
                   "A1.4 1.4 0 0 0 4.4 14.6 H7.6 L13 19.2 Z")
_SVG_SPEAK_ARCS = ("M16.2 9.4a3.6 3.6 0 0 1 0 5.2", "M18.8 7a7.2 7.2 0 0 1 0 10")
_SVG_PIN_DOME = ("M10.2 6.2C10.2 10.6 8.8 11.8 6.8 13 5.6 13.7 5 14.3 5 14.9"
                 "A0.9 0.9 0 0 0 5.9 15.8H18.1a0.9 0.9 0 0 0 0.9-0.9"
                 "c0-0.6-0.6-1.2-1.8-1.9C15.2 11.8 13.8 10.6 13.8 6.2Z")

_SVG_TOK = re.compile(r"[MmLlHhVvCcAaZz]|-?\d*\.?\d+(?:e-?\d+)?")


def _arc_pts(x0, y0, r, fA, fS, x1, y1, n=14):
    """SVG elliptical-arc (circle only, no rotation) -> sampled points."""
    dx, dy = x1 - x0, y1 - y0
    half = math.hypot(dx, dy) / 2.0
    if half < 1e-6:
        return [(x1, y1)]
    r = max(r, half)
    c = math.sqrt(max(0.0, r * r - half * half))
    ux, uy = -dy, dx
    ul = math.hypot(ux, uy) or 1.0
    sign = 1 if fA != fS else -1
    cxc = (x0 + x1) / 2.0 + sign * c * ux / ul
    cyc = (y0 + y1) / 2.0 + sign * c * uy / ul
    a0 = math.atan2(y0 - cyc, x0 - cxc)
    a1 = math.atan2(y1 - cyc, x1 - cxc)
    da = a1 - a0
    if fS == 0 and da > 0:
        da -= 2 * math.pi
    if fS == 1 and da < 0:
        da += 2 * math.pi
    return [(cxc + r * math.cos(a0 + da * k / n),
             cyc + r * math.sin(a0 + da * k / n)) for k in range(1, n + 1)]


def _svg_subpaths(dstr):
    """Very small SVG-path reader: M L H V C A Z (+ relative). Curves/arcs are
    sampled into points. Returns a list of point lists (one per subpath)."""
    toks = _SVG_TOK.findall(dstr)
    i, n = 0, len(toks)
    subs, cur = [], []
    x = y = sx = sy = 0.0
    cmd = "M"
    while i < n:
        if toks[i].isalpha():
            cmd = toks[i]
            i += 1
        rel, C = cmd.islower(), cmd.upper()

        def g():
            nonlocal i
            v = float(toks[i])
            i += 1
            return v

        if C == "M":
            if cur:
                subs.append(cur)
            nx, ny = g(), g()
            x, y = (x + nx, y + ny) if rel else (nx, ny)
            sx, sy = x, y
            cur = [(x, y)]
            cmd = "l" if rel else "L"
        elif C == "L":
            nx, ny = g(), g()
            x, y = (x + nx, y + ny) if rel else (nx, ny)
            cur.append((x, y))
        elif C == "H":
            nx = g()
            x = x + nx if rel else nx
            cur.append((x, y))
        elif C == "V":
            ny = g()
            y = y + ny if rel else ny
            cur.append((x, y))
        elif C == "C":
            x1, y1, x2, y2, nx, ny = (g() for _ in range(6))
            if rel:
                x1, y1, x2, y2, nx, ny = (x + x1, y + y1, x + x2, y + y2,
                                          x + nx, y + ny)
            for t in (k / 14.0 for k in range(1, 15)):
                u = 1 - t
                cur.append((u**3 * x + 3 * u * u * t * x1 + 3 * u * t * t * x2
                            + t**3 * nx,
                            u**3 * y + 3 * u * u * t * y1 + 3 * u * t * t * y2
                            + t**3 * ny))
            x, y = nx, ny
        elif C == "A":
            rx, _ry, _rot, large, sweep, nx, ny = (g() for _ in range(7))
            if rel:
                nx, ny = x + nx, y + ny
            cur.extend(_arc_pts(x, y, rx, int(large), int(sweep), nx, ny))
            x, y = nx, ny
        elif C == "Z":
            cur.append((sx, sy))
            subs.append(cur)
            cur = []
            x, y = sx, sy
    if cur:
        subs.append(cur)
    return subs

LIGHT = {
    "border": "#E4E4E7", "card": "#FFFFFF",
    "word": "#1D1D1F", "phon": "#86868B", "label": "#9A9AA0",
    "accent": "#0A84FF", "primary": "#0A6CE0",
    "chip_bg": "#EEEEF1", "chip_fg": "#2E2E33",
    "pos_bg": "#E4EFFE", "pos_fg": "#0A63D6",
    "sent": "#3C3C43", "sent_dim": "#3A3A40",
    "icon": "#5A5A60", "icon_hi": "#1D1D1F",
    "icon_bg": "#EDEDF0", "icon_hover_bg": "#DEDEE3",
    "sep": "#EEEEF1", "name": "#B8B8BE",
}
DARK = {
    "border": "#3A3A3C", "card": "#262629",
    "word": "#F5F5F7", "phon": "#9A9AA0", "label": "#8A8A8F",
    "accent": "#0A84FF", "primary": "#4C9EFF",
    "chip_bg": "#3A3A3E", "chip_fg": "#E6E6EA",
    "pos_bg": "#123A63", "pos_fg": "#7ABBFF",
    "sent": "#D6D6DB", "sent_dim": "#CDCDD3",
    "icon": "#BFBFC5", "icon_hi": "#FFFFFF",
    "icon_bg": "#333338", "icon_hover_bg": "#454549",
    "sep": "#333336", "name": "#6E6E73",
}


_u32 = ctypes.windll.user32
_gdi = ctypes.windll.gdi32
_u32.GetAncestor.restype = ctypes.c_void_p
_u32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
_gdi.CreateRoundRectRgn.restype = ctypes.c_void_p
_gdi.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
_u32.SetWindowRgn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool]


def _root_hwnd(win):
    h = _u32.GetAncestor(win.winfo_id(), 2)  # GA_ROOT
    return h or win.winfo_id()


class Popup:
    def __init__(self, root, cfg, on_speak=None, on_unpin=None, on_pin=None,
                 on_copy=None):
        self.root = root
        self.cfg = cfg
        self.on_speak = on_speak or (lambda w: None)
        # on_copy(text) -> False on failure; None/True counts as success
        self.on_copy = on_copy or (lambda text: True)
        self.on_unpin = on_unpin or (lambda: None)
        self.on_pin = on_pin or (lambda pinned: None)
        self.pal = DARK if str(cfg.get("theme", "light")).lower() == "dark" else LIGHT
        self.radius = int(cfg.get("corner_radius", 16))
        self.pinned = False
        self._word = ""
        self._phon_text = ""     # what l_phon shows when no "copied" flash is up
        self._flash_job = None
        self._drag = None
        self._imgs = {}          # rounded-rect PhotoImage cache
        self._imgrefs = []       # keep per-chip images alive
        self._anim_job = None
        self._anim_t = 0

        fs = int(cfg.get("font_size", 12))
        cjk = "Microsoft YaHei UI"
        self.f_word = tkfont.Font(family="Segoe UI Semibold", size=fs + 4, weight="bold")
        self.f_phon = tkfont.Font(family="Segoe UI", size=fs)
        self.f_label = tkfont.Font(family="Segoe UI", size=fs - 3)
        # CJK glyphs read ~1pt larger than Latin at the same size -> shrink 1pt;
        # bump weight where it carries meaning (headline + highlight).
        self.f_primary = tkfont.Font(family=cjk, size=fs + 1, weight="bold")
        self.f_chip = tkfont.Font(family=cjk, size=fs - 3)
        self.f_pos = tkfont.Font(family="Segoe UI Semibold", size=fs - 3, weight="bold")
        # both the English source line and the Chinese translation are bold
        self.f_sent = tkfont.Font(family="Segoe UI Semibold", size=fs - 1,
                                  weight="bold")
        self.f_sent_cn = tkfont.Font(family=cjk, size=fs - 2, weight="bold")
        self.f_sent_b = tkfont.Font(family="Segoe UI Semibold", size=fs - 1, weight="bold")
        self.f_sent_cn_b = tkfont.Font(family=cjk, size=fs - 2, weight="bold")
        # bigger glyph inside a fixed-size button = heavier look, same footprint
        self.f_icon = tkfont.Font(family="Segoe MDL2 Assets", size=fs + 6)
        self.f_name = tkfont.Font(family="Segoe UI", size=fs - 4)

        self.card_w_min = max(300, int(cfg.get("card_width", 380)))
        self.card_w_max = max(self.card_w_min,
                              int(cfg.get("card_width_max", 560)))
        self.sent_max_lines = max(3, int(cfg.get("sentence_max_lines", 16)))
        self.content_w = self.card_w_min

        sc = max(0.4, min(1.4, float(cfg.get("icon_scale", 0.75))))
        self.ic_w = max(16, round(IC_BASE[0] * sc))
        self.ic_h = max(14, round(IC_BASE[1] * sc))
        self.ic_r = max(3, round(IC_BASE[2] * sc))
        self.ic_stroke = IC_STROKE * max(0.85, sc)

        self.win = tk.Toplevel(root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-alpha", float(cfg.get("opacity", 1.0)))
        except Exception:
            pass

        p = self.pal
        self.outer = tk.Frame(self.win, bg=p["border"])
        self.outer.pack(fill="both", expand=True)
        self.card = tk.Frame(self.outer, bg=p["card"], padx=16, pady=13)
        self.card.pack(fill="both", expand=True, padx=1, pady=1)

        self._build_header()
        self.l_section = tk.Label(self.card, text="常用释义", bg=p["card"],
                                  fg=p["label"], font=self.f_label, anchor="w")
        self.l_primary = tk.Label(self.card, bg=p["card"], fg=p["primary"],
                                  font=self.f_primary, anchor="w", justify="left",
                                  wraplength=self.content_w, pady=0)
        self.groups = tk.Frame(self.card, bg=p["card"])

        self.sep = tk.Frame(self.card, bg=p["sep"], height=1)
        self.t_en = self._make_text(p["sent"], self.f_sent, self.f_sent_b)
        self.t_cn = self._make_text(p["sent_dim"], self.f_sent_cn, self.f_sent_cn_b)

        self.l_name = tk.Label(self.card, text=APP_NAME, bg=p["card"], fg=p["name"],
                               font=self.f_name, cursor="hand2")
        self.l_name.bind("<Enter>", self._tip_show)
        self.l_name.bind("<Leave>", self._tip_hide)
        self._tip = None

        for w in (self.card, self.header, self.l_word_wrap):
            w.bind("<ButtonPress-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)

    # ---- widgets -----------------------------------------------------
    def _build_header(self):
        p = self.pal
        self.header = tk.Frame(self.card, bg=p["card"])
        self.header.pack(fill="x")

        self.l_word_wrap = tk.Frame(self.header, bg=p["card"])
        self.l_word_wrap.pack(side="left")
        self.l_word = tk.Label(self.l_word_wrap, bg=p["card"], fg=p["word"],
                               font=self.f_word, pady=0)
        self.l_word.pack(side="left")
        self.l_word.bind("<Double-Button-1>", lambda e: self._copy(self._word))
        self.l_phon = tk.Label(self.l_word_wrap, bg=p["card"], fg=p["phon"],
                               font=self.f_phon)
        self.l_phon.pack(side="left", padx=(8, 0), pady=(6, 0))
        self.loader = tk.Canvas(self.l_word_wrap, width=48,
                                height=self.f_word.metrics("linespace"),
                                bg=p["card"], highlightthickness=0)

        # right-side controls: speaker + pin, in rounded weighted chips
        tools = tk.Frame(self.header, bg=p["card"])
        tools.pack(side="right", pady=(2, 0))
        self.b_speak = self._icon_btn(tools, "speak",
                                      lambda e: self.on_speak(self._word))
        self.b_pin = self._icon_btn(tools, "pin", self._toggle_pin)
        self.b_speak.pack(side="left", padx=(0, 4))
        self.b_pin.pack(side="left")

    # ---- rounded backgrounds ---------------------------------------
    def _round_img(self, w, h, radius, fill_hex):
        key = (w, h, radius, fill_hex)
        img = self._imgs.get(key)
        if img is None and _PIL:
            s = 4
            im = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
            ImageDraw.Draw(im).rounded_rectangle(
                [0, 0, w * s - 1, h * s - 1], radius=radius * s,
                fill=_rgba(fill_hex))
            im = im.resize((w, h), Image.LANCZOS)
            img = ImageTk.PhotoImage(im)
            self._imgs[key] = img
        return img

    def _icon_img(self, kind, w, h, radius, bg_hex, fg_hex):
        """Rounded background + a hand-drawn line glyph, as one PhotoImage.
        kind: "speak" | "pin" | "pin_on". Cached by every visual parameter."""
        key = ("ico", kind, w, h, radius, bg_hex, fg_hex)
        img = self._imgs.get(key)
        if img is None and _PIL:
            s = 4
            im = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            d.rounded_rectangle([0, 0, w * s - 1, h * s - 1],
                                radius=radius * s, fill=_rgba(bg_hex))
            box = min(w, h) * IC_GLYPH * s
            self._draw_glyph(d, kind, w * s / 2.0, h * s / 2.0,
                             box, _rgba(fg_hex), self.ic_stroke)
            im = im.resize((w, h), Image.LANCZOS)
            img = ImageTk.PhotoImage(im)
            self._imgs[key] = img
        return img

    @staticmethod
    def _draw_glyph(d, kind, cx, cy, box, rgba, sw):
        """Render the handoff SVG paths. box = glyph size (px), sw = stroke in
        24-unit viewBox terms."""
        k = box / 24.0
        lw = max(1, int(round(sw * k)))

        def M(pts):
            return [(cx + (px - 12.0) * k, cy + (py - 12.0) * k)
                    for px, py in pts]

        if kind == "speak":
            for sub in _svg_subpaths(_SVG_SPEAK_CONE):
                d.line(M(sub), fill=rgba, width=lw, joint="curve")
            for pd in _SVG_SPEAK_ARCS:
                for sub in _svg_subpaths(pd):
                    d.line(M(sub), fill=rgba, width=lw, joint="curve")
        else:
            solid = kind == "pin_solid"
            for sub in _svg_subpaths(_SVG_PIN_DOME):
                if solid:
                    d.polygon(M(sub), fill=rgba)
                else:
                    d.line(M(sub), fill=rgba, width=lw, joint="curve")
            (rx0, ry0), (rx1, ry1) = M([(8.0, 3.6), (16.0, 6.2)])
            d.rounded_rectangle([rx0, ry0, rx1, ry1], radius=max(1, int(1.3 * k)),
                                outline=rgba, width=lw,
                                fill=(rgba if solid else None))
            if solid:
                d.polygon(M([(12.0, 20.6), (11.1, 15.8), (12.9, 15.8)]),
                          fill=rgba)
            else:
                d.line(M([(12.0, 15.8), (12.0, 20.4)]), fill=rgba, width=lw)

    def _chip(self, parent, text, font, fg, bg_hex, px, py, radius):
        w = font.measure(text) + px * 2
        h = font.metrics("linespace") + py * 2
        img = self._round_img(w, h, radius, bg_hex)
        if img is None:
            return tk.Label(parent, text=text, font=font, fg=fg, bg=bg_hex,
                            padx=px, pady=py)
        lbl = tk.Label(parent, text=text, font=font, fg=fg, bg=self.pal["card"],
                       image=img, compound="center", width=w, height=h,
                       borderwidth=0)
        lbl._img = img
        self._imgrefs.append(img)
        return lbl

    def _icon_btn(self, parent, kind, cb):
        b = tk.Label(parent, bg=self.pal["card"], cursor="hand2", borderwidth=0)
        b._kind = kind          # "speak" | "pin"
        b._hovered = False
        self._skin_icon(b)
        b.bind("<Enter>", lambda e: (setattr(b, "_hovered", True),
                                     self._skin_icon(b)))
        b.bind("<Leave>", lambda e: (setattr(b, "_hovered", False),
                                     self._skin_icon(b)))
        b.bind("<Button-1>", cb)
        return b

    def _skin_icon(self, b):
        p = self.pal
        pinned = (b._kind == "pin" and self.pinned)
        if pinned:
            bg, fg, kind = p["accent"], "#FFFFFF", "pin_solid"
        elif b._hovered:
            bg, fg, kind = p["icon_hover_bg"], p["icon_hi"], b._kind
        else:
            bg, fg, kind = p["icon_bg"], p["icon"], b._kind
        img = self._icon_img(kind, self.ic_w, self.ic_h, self.ic_r, bg, fg)
        if img is not None:
            b.config(image=img, text="", width=self.ic_w, height=self.ic_h)
            b._img = img
        else:                   # Pillow missing -> MDL2 glyph fallback
            glyph = {"pin": IC_UNPIN if pinned else IC_PIN,
                     "speak": IC_SPEAK}[b._kind]
            b.config(image="", text=glyph, font=self.f_icon,
                     compound="center", fg=fg, bg=bg, padx=6, pady=4)

    # ---- loading dots --------------------------------------------
    def _start_anim(self):
        self._stop_anim()
        self._anim_t = 0
        c = self.loader
        c.delete("all")
        self._dots = [c.create_oval(0, 0, 0, 0, outline="") for _ in range(3)]
        self._anim_tick()

    def _stop_anim(self):
        if self._anim_job:
            try:
                self.root.after_cancel(self._anim_job)
            except Exception:
                pass
            self._anim_job = None

    def _anim_tick(self):
        c = self.loader
        h = int(c["height"])
        base, accent = self.pal["phon"], self.pal["accent"]
        self._anim_t += 1
        for i, d in enumerate(self._dots):
            ph = self._anim_t * 0.28 - i * 0.9
            s = (math.sin(ph) + 1) / 2          # 0..1
            r = 2.4 + 2.2 * s
            cx, cy = 9 + i * 14, h / 2
            c.coords(d, cx - r, cy - r, cx + r, cy + r)
            c.itemconfig(d, fill=accent if s > 0.55 else base)
        self._anim_job = self.root.after(60, self._anim_tick)

    def _make_text(self, fg, font, font_b):
        p = self.pal
        cw = max(1, font.measure("0"))
        t = tk.Text(self.card, height=1, width=max(10, self.content_w // cw),
                    wrap="word", bd=0, highlightthickness=0,
                    bg=p["card"], fg=fg, font=font, cursor="arrow",
                    padx=0, pady=0, spacing1=1, spacing3=3)
        t.tag_config("hl", foreground=p["accent"], font=font_b)
        t._font = font
        t.bind("<ButtonPress-1>", self._drag_start)
        t.bind("<B1-Motion>", self._drag_move)
        # double-click copies the whole line; "break" stops Tk's default
        # select-one-word behaviour on a double-click
        t.bind("<Double-Button-1>", lambda e, w=t: (self._copy_text(w), "break")[1])
        return t

    def _line_count(self, font, text, width=None):
        width = width or self.content_w
        n, cur = 1, 0
        for tok in re.findall(r"\s+|\S+", text or ""):
            if "\n" in tok:
                n += tok.count("\n")
                cur = 0
                continue
            w = font.measure(tok)
            if cur + w > width and cur > 0:
                n += 1
                cur = 0 if tok.strip() == "" else w
            else:
                cur += w
            while cur > width:
                n += 1
                cur -= width
        return n

    def _target_width(self, data):
        """Widen the card toward card_width_max when a long sentence would
        otherwise wrap into many lines - wider reads easier than taller."""
        base, cap = self.card_w_min, self.card_w_max
        longest = max((data.get("sentence_en") or "",
                       data.get("sentence_cn") or "",
                       data.get("primary") or ""), key=len)
        if len(longest) < 40:
            return base
        rows = self._line_count(self.f_sent, longest, base)
        if rows <= 3:
            return base
        want = int(base * max(1.0, rows / 4.0))   # aim for ~4 rows
        return max(base, min(cap, want))

    # ---- flow layout for chips ------------------------------------
    def _fill_groups(self, pos_groups):
        for c in self.groups.winfo_children():
            c.destroy()
        self._imgrefs = []
        p = self.pal
        for label, meanings in pos_groups[:5]:
            row = tk.Frame(self.groups, bg=p["card"])
            row.pack(fill="x", pady=(3, 0), anchor="w")
            self._chip(row, label, self.f_pos, p["pos_fg"], p["pos_bg"],
                       6, 2, 5).pack(side="left", anchor="n", pady=(1, 0))
            box = tk.Frame(row, bg=p["card"])
            box.pack(side="left", padx=(6, 0))
            line = tk.Frame(box, bg=p["card"])
            line.pack(anchor="w")
            used = 0
            budget = self.content_w - 60
            for m in meanings:
                w = self.f_chip.measure(m) + 20
                if used and used + w > budget:
                    line = tk.Frame(box, bg=p["card"])
                    line.pack(anchor="w", pady=(4, 0))
                    used = 0
                self._chip(line, m, self.f_chip, p["chip_fg"], p["chip_bg"],
                           8, 3, 5).pack(side="left", padx=(0, 5))
                used += w + 5

    # ---- show --------------------------------------------------
    def _set_sentence(self, widget, text, spans):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text or "")
        for a, b in spans:
            widget.tag_add("hl", "1.0+%dc" % a, "1.0+%dc" % b)
        widget.configure(state="disabled")
        self._fit_text_height(widget, text)

    def _fit_text_height(self, widget, text):
        n = self._line_count(widget._font, text)
        widget.configure(height=max(1, min(self.sent_max_lines, n)))

    def _show_word_row(self):
        self._stop_anim()
        self.loader.pack_forget()
        if not self.l_word.winfo_ismapped():
            self.l_word.pack(side="left")
        if not self.l_phon.winfo_ismapped():
            self.l_phon.pack(side="left", padx=(8, 0), pady=(6, 0))

    def show(self, anchor, data):
        """data: dict(word, phonetic, primary, pos_groups, sentence_en,
                      sentence_cn, spans_en, spans_cn, _translating)

        Called up to twice per lookup: once with the offline data (instant),
        then again once the online sentence translation lands. On the second
        call for the same word the card keeps its position."""
        p = self.pal
        self._show_word_row()
        same = (data.get("word") == self._word and self.win.winfo_viewable())

        w = self._target_width(data)
        if w != self.content_w:
            self.content_w = w
            self.l_primary.config(wraplength=w)
            for t in (self.t_en, self.t_cn):
                cw = max(1, t._font.measure("0"))
                t.config(width=max(10, w // cw))
            same = False                      # width changed -> re-place

        self._word = data.get("word", "")
        self.l_word.config(text=self._word)
        phon = data.get("phonetic") or ""
        self._set_phon(("/%s/" % phon) if phon else "")

        self.l_section.pack_forget()
        self.l_primary.pack_forget()
        self.groups.pack_forget()
        self.sep.pack_forget()
        self.t_en.pack_forget()
        self.t_cn.pack_forget()
        self.l_name.pack_forget()

        primary = data.get("primary") or ""
        if primary:
            self.l_primary.config(text=primary)
            self.l_primary.pack(fill="x", pady=(0, 0))

        groups = data.get("pos_groups") or []
        if groups:
            self._fill_groups(groups)
            self.groups.pack(fill="x", pady=(7, 0))

        sen = data.get("sentence_en")
        if sen:
            self.sep.pack(fill="x", pady=(11, 9))
            self._set_sentence(self.t_en, sen, data.get("spans_en") or [])
            self.t_en.pack(fill="x")
            cn = data.get("sentence_cn")
            if cn:
                self._set_sentence(self.t_cn, cn, data.get("spans_cn") or [])
                self.t_cn.pack(fill="x", pady=(3, 0))
            elif data.get("_translating"):
                self._set_sentence(self.t_cn, _PLACEHOLDER, [])
                self.t_cn.pack(fill="x", pady=(3, 0))

        self.l_name.pack(anchor="e", pady=(9, 0))

        if not same:
            self._place(anchor)
        self._apply_region()

    def show_loading(self, anchor):
        self._word = ""
        self.l_word.pack_forget()
        self.l_phon.pack_forget()
        self.loader.pack(side="left", pady=(4, 0))
        self._start_anim()
        for w in (self.l_section, self.l_primary, self.groups, self.sep,
                  self.t_en, self.t_cn, self.l_name):
            w.pack_forget()
        self._place(anchor)
        self._apply_region()

    def show_message(self, anchor, text):
        self._show_word_row()
        self._word = ""
        self.l_word.config(text=text)
        self._set_phon("")
        for w in (self.l_section, self.l_primary, self.groups, self.sep,
                  self.t_en, self.t_cn, self.l_name):
            w.pack_forget()
        self._place(anchor)
        self._apply_region()

    # ---- placement / region --------------------------------------
    def _place(self, anchor):
        self.win.deiconify()
        self.win.lift()
        if anchor is None or self.pinned:
            return
        self.win.update_idletasks()
        w, h = self.win.winfo_width(), self.win.winfo_height()
        u = ctypes.windll.user32
        vx, vy = u.GetSystemMetrics(76), u.GetSystemMetrics(77)
        vw, vh = u.GetSystemMetrics(78), u.GetSystemMetrics(79)
        x, y = anchor[0] + 20, anchor[1] + 26
        if x + w > vx + vw:
            x = anchor[0] - w - 20
        if y + h > vy + vh:
            y = anchor[1] - h - 26
        x = max(vx, min(x, vx + vw - w))
        y = max(vy, min(y, vy + vh - h))
        if h > vh:                       # taller than the screen -> pin to top
            y = vy
        self.win.geometry("+%d+%d" % (int(x), int(y)))

    def _apply_region(self):
        self.win.update_idletasks()
        w, h = self.win.winfo_width(), self.win.winfo_height()
        try:
            rgn = _gdi.CreateRoundRectRgn(
                0, 0, w + 1, h + 1, self.radius * 2, self.radius * 2)
            _u32.SetWindowRgn(_root_hwnd(self.win), rgn, True)
        except Exception:
            pass

    def hide(self):
        if not self.pinned:
            self._stop_anim()
            self.win.withdraw()

    def force_hide(self):
        self.pinned = False
        self._sync_pin()
        self._stop_anim()
        self.win.withdraw()

    # ---- copy on double-click ----------------------------------
    def _set_phon(self, text):
        self._phon_text = text
        self.l_phon.config(text=text, fg=self.pal["phon"])

    def _copy_text(self, widget):
        text = widget.get("1.0", "end-1c").strip()
        if text and text != _PLACEHOLDER:
            self._copy(text)

    def _copy(self, text):
        """Put text on the clipboard and flash the result in the header."""
        text = (text or "").strip()
        if not text:
            return
        ok = self.on_copy(text) is not False
        if self._flash_job:
            self.root.after_cancel(self._flash_job)
        self.l_phon.config(text="已复制 ✓" if ok else "复制失败",
                           fg=self.pal["accent"] if ok else self.pal["label"])
        self._flash_job = self.root.after(900, self._end_flash)

    def _end_flash(self):
        self._flash_job = None
        self.l_phon.config(text=self._phon_text, fg=self.pal["phon"])

    # ---- pin / drag ------------------------------------
    def _toggle_pin(self, _=None):
        self.pinned = not self.pinned
        self._sync_pin()
        self.on_pin(self.pinned)
        if not self.pinned:
            self.on_unpin()
            self.win.withdraw()

    def _sync_pin(self):
        self._skin_icon(self.b_pin)

    def _drag_start(self, e):
        self._drag = (e.x_root, e.y_root,
                      self.win.winfo_x(), self.win.winfo_y())

    def _drag_move(self, e):
        if not self._drag:
            return
        dx = e.x_root - self._drag[0]
        dy = e.y_root - self._drag[1]
        self.win.geometry("+%d+%d" % (self._drag[2] + dx, self._drag[3] + dy))

    # ---- author tooltip --------------------------------------
    def _tip_show(self, _=None):
        if self._tip:
            return
        self._tip = tk.Toplevel(self.win)
        self._tip.overrideredirect(True)
        self._tip.attributes("-topmost", True)
        tk.Label(self._tip, text=AUTHOR_TIP, bg="#1D1D1F", fg="#FFFFFF",
                 font=self.f_name, padx=8, pady=3).pack()
        self._tip.update_idletasks()
        x = self.l_name.winfo_rootx() - self._tip.winfo_width() + self.l_name.winfo_width()
        y = self.l_name.winfo_rooty() - self._tip.winfo_height() - 5
        self._tip.geometry("+%d+%d" % (x, y))

    def _tip_hide(self, _=None):
        if self._tip:
            self._tip.destroy()
            self._tip = None
