#!/usr/bin/env python3
"""
sequence_visualiser - interval sequence visualizer for guitar in perfect fourth tuning.

Generates a PDF chart of all standard fingerings of an interval sequence
(e.g. "P1 M3 P5") on a fretboard tuned in perfect fourths, and optionally
saves every shape as a PNG or SVG image.

Terminal-only. Run with --help for usage and the full interval table.
"""

import argparse
import os
import re
import sys
from collections import defaultdict

# ----------------------------------------------------------------------------
# Intervals
# ----------------------------------------------------------------------------

# Interval name -> semitones from the root. Case matters.
INTERVALS = {
    "P1": 0,
    "m2": 1, "M2": 2,
    "A2": 3, "m3": 3,
    "M3": 4,
    "A3": 5, "P4": 5,
    "A4": 6, "d5": 6, "TT": 6,
    "P5": 7,
    "A5": 8, "m6": 8,
    "M6": 9,
    "A6": 10, "m7": 10,
    "M7": 11,
    "P8": 12,
}

VALID_NAMES = "P1 m2 M2 A2 m3 M3 A3 P4 A4 d5 TT P5 A5 m6 M6 A6 m7 M7"


def fail(msg):
    print("error: " + msg, file=sys.stderr)
    sys.exit(1)


def parse_intervals(text):
    """Parse and validate the interval sequence; return list of names."""
    tokens = [t for t in re.split(r"[,\s]+", text.strip()) if t]
    if not tokens:
        fail("no intervals given. Run with --help for the interval table.")
    for t in tokens:
        if t == "P8":
            fail("'P8' (the octave) is not allowed in the input - "
                 "it is added automatically as the finish note.")
        if t not in INTERVALS:
            fail("unknown interval name '%s' (case matters).\n"
                 "       valid names: %s" % (t, VALID_NAMES))
    if tokens[0] != "P1":
        fail("the sequence must start with P1 (got '%s')." % tokens[0])
    if len(tokens) < 2:
        fail("the sequence must have more than one interval "
             "(P1 plus at least one more).")
    semis = [INTERVALS[t] for t in tokens]
    for i in range(1, len(tokens)):
        if semis[i] <= semis[i - 1]:
            fail("intervals must strictly increase: '%s' (%d semitones) does not "
                 "follow '%s' (%d semitones)."
                 % (tokens[i], semis[i], tokens[i - 1], semis[i - 1]))
    if semis[-1] >= 12:
        fail("the last interval must be smaller than an octave (P8).")
    if len(tokens) > 12:
        fail("the sequence may contain at most 12 intervals.")
    return tokens


# ----------------------------------------------------------------------------
# Shape enumeration
# ----------------------------------------------------------------------------
#
# Perfect fourths tuning: the next higher-sounding string is 5 semitones above
# the current one at the same fret. A note s semitones above the root, played
# on string row 0 + r (r negative = higher-sounding string), sits at fret
# offset  f = s + 5*r.
#
# A fingering ("standard box") is a monotone path: as the pitch ascends, each
# note either stays on its string or moves to the next higher-sounding string.
# With N notes (root, intervals, octave) there are 2^(N-1) fingerings; the
# number of strings used is (string moves + 1). The pattern is transposable,
# so frets are normalized to the shape's own bounding box (min fret = 0).

STRING_SEMITONES = 5  # perfect fourth


class Shape:
    __slots__ = ("rows", "frets", "labels", "strings", "width")

    def __init__(self, rows, frets, labels):
        self.rows = rows          # string row per note, 0 = root string, negative = higher
        self.frets = frets        # fret inside the bounding box (min = 0)
        self.labels = labels      # interval name per note
        self.strings = 1 - min(rows)  # rows span 0 .. -(strings-1)
        self.width = max(frets) + 1   # fret spaces in the bounding box


def enumerate_shapes(names):
    """All fingerings of the sequence, grouped by number of strings used."""
    notes = [INTERVALS[n] for n in names] + [12]  # append the octave
    labels = list(names) + ["P8"]
    n = len(notes)
    groups = defaultdict(list)
    for mask in range(1 << (n - 1)):
        rows = [0]
        for i in range(n - 1):
            rows.append(rows[-1] - (1 if (mask >> i) & 1 else 0))
        frets = [notes[i] + STRING_SEMITONES * rows[i] for i in range(n)]
        base = min(frets)
        frets = [f - base for f in frets]
        shape = Shape(rows, frets, labels)
        groups[shape.strings].append(shape)
    for shapes in groups.values():
        shapes.sort(key=lambda s: (s.width, tuple(s.frets), tuple(s.rows)))
    return groups


# ----------------------------------------------------------------------------
# Drawing: shape -> display list
# ----------------------------------------------------------------------------
# Primitives (coordinates in pt, y grows downward):
#   ("rect",   x, y, w, h, color)
#   ("line",   x1, y1, x2, y2, width, color)
#   ("circle", cx, cy, r, color)
#   ("text",   x, y, string, size, color, anchor)   bold; anchor 'c','l','r'

BLACK = (0, 0, 0)
WHITE = (1, 1, 1)
RED = (208 / 255, 2 / 255, 27 / 255)   # from example.png
GRAY = (0.35, 0.35, 0.35)

FRET_W = 40.0       # width of one fret space
STRING_GAP = 50.0   # vertical distance between strings
DOT_D = 33.0        # dot diameter (as in example.png)
LABEL_SIZE = 15.0   # interval name inside the dot
LINE_STRING = 3.0   # string line weight
LINE_FRET = 2.0     # fret line weight


def draw_shape(shape):
    """Return (display_list, width, height) for one shape, tightly cropped."""
    n, w = shape.strings, shape.width
    mx = FRET_W / 2
    my = STRING_GAP / 2
    W = 2 * mx + w * FRET_W
    H = 2 * my + (n - 1) * STRING_GAP
    dl = [("rect", 0, 0, W, H, WHITE)]
    # strings (horizontal; higher-sounding strings at the top)
    for i in range(n):
        y = my + i * STRING_GAP
        dl.append(("line", mx, y, W - mx, y, LINE_STRING, BLACK))
    # frets (vertical)
    if n == 1:
        # a single string has no string band: draw the frets as ladder ticks
        # crossing the string instead of between two outer strings
        fy0, fy1 = 4.0, H - 4.0
    else:
        fy0, fy1 = my, H - my
    for j in range(w + 1):
        x = mx + j * FRET_W
        dl.append(("line", x, fy0, x, fy1, LINE_FRET, BLACK))
    # dots
    for row, fret, label in zip(shape.rows, shape.frets, shape.labels):
        cx = mx + (fret + 0.5) * FRET_W
        cy = my + ((n - 1) + row) * STRING_GAP
        dl.append(("circle", cx, cy, DOT_D / 2, RED if label in ("P1", "P8") else BLACK))
        dl.append(("text", cx, cy, label, LABEL_SIZE, WHITE, "c"))
    return dl, W, H


def transform(dl, ox, oy, s):
    """Place a display list at (ox, oy), scaled by s."""
    out = []
    for p in dl:
        if p[0] == "rect":
            _, x, y, w, h, c = p
            out.append(("rect", ox + x * s, oy + y * s, w * s, h * s, c))
        elif p[0] == "line":
            _, x1, y1, x2, y2, w, c = p
            out.append(("line", ox + x1 * s, oy + y1 * s, ox + x2 * s, oy + y2 * s, w * s, c))
        elif p[0] == "circle":
            _, cx, cy, r, c = p
            out.append(("circle", ox + cx * s, oy + cy * s, r * s, c))
        elif p[0] == "text":
            _, x, y, t, sz, c, a = p
            out.append(("text", ox + x * s, oy + y * s, t, sz * s, c, a))
    return out


# ----------------------------------------------------------------------------
# SVG backend
# ----------------------------------------------------------------------------

def _hexcolor(c):
    return "#%02X%02X%02X" % tuple(max(0, min(255, round(v * 255))) for v in c)


def svg_bytes(dl, w, h):
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="%.2f" height="%.2f" '
        'viewBox="0 0 %.2f %.2f">' % (w, h, w, h),
        '<rect x="0" y="0" width="%.2f" height="%.2f" fill="#FFFFFF"/>' % (w, h),
    ]
    for p in dl:
        if p[0] == "rect":
            _, x, y, rw, rh, c = p
            parts.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="%s"/>'
                         % (x, y, rw, rh, _hexcolor(c)))
        elif p[0] == "line":
            _, x1, y1, x2, y2, lw, c = p
            parts.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" '
                         'stroke-width="%.2f" stroke-linecap="round"/>'
                         % (x1, y1, x2, y2, _hexcolor(c), lw))
        elif p[0] == "circle":
            _, cx, cy, r, c = p
            parts.append('<circle cx="%.2f" cy="%.2f" r="%.2f" fill="%s"/>'
                         % (cx, cy, r, _hexcolor(c)))
        elif p[0] == "text":
            _, x, y, t, sz, c, a = p
            t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            anchor = {"c": "middle", "l": "start", "r": "end"}[a]
            parts.append('<text x="%.2f" y="%.2f" font-family="Helvetica, Arial, '
                         'sans-serif" font-weight="bold" font-size="%.2f" fill="%s" '
                         'text-anchor="%s" dominant-baseline="central">%s</text>'
                         % (x, y, sz, _hexcolor(c), anchor, t))
    parts.append("</svg>")
    return "\n".join(parts).encode("utf-8")


# ----------------------------------------------------------------------------
# PNG backend (Pillow)
# ----------------------------------------------------------------------------

_FONT_CANDIDATES = [
    "DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]
_font_cache = {}


def _load_font(size):
    if size in _font_cache:
        return _font_cache[size]
    from PIL import ImageFont
    font = None
    for path in _FONT_CANDIDATES:
        try:
            font = ImageFont.truetype(path, size=size)
            break
        except Exception:
            continue
    if font is None:
        try:
            font = ImageFont.load_default(size=size)  # Pillow >= 10.1
        except TypeError:
            font = ImageFont.load_default()
    _font_cache[size] = font
    return font


def png_bytes(dl, w, h, out_scale=2.0, supersample=3):
    """Render the display list to PNG bytes (antialiased via supersampling)."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        fail("PNG output requires Pillow (python3 -m pip install Pillow), "
             "or use --format svg.")
    import io
    ss = int(supersample * out_scale)
    W = max(1, int(round(w * out_scale)))
    H = max(1, int(round(h * out_scale)))
    img = Image.new("RGB", (int(round(w)) * ss, int(round(h)) * ss), (255, 255, 255))
    d = ImageDraw.Draw(img)

    def col(c):
        return tuple(max(0, min(255, round(v * 255))) for v in c)

    for p in dl:
        if p[0] == "rect":
            _, x, y, rw, rh, c = p
            d.rectangle([x * ss, y * ss, (x + rw) * ss, (y + rh) * ss], fill=col(c))
        elif p[0] == "line":
            _, x1, y1, x2, y2, lw, c = p
            d.line([x1 * ss, y1 * ss, x2 * ss, y2 * ss],
                   fill=col(c), width=max(1, int(round(lw * ss))))
        elif p[0] == "circle":
            _, cx, cy, r, c = p
            d.ellipse([(cx - r) * ss, (cy - r) * ss, (cx + r) * ss, (cy + r) * ss],
                      fill=col(c))
        elif p[0] == "text":
            _, x, y, t, sz, c, a = p
            f = _load_font(max(1, int(round(sz * ss))))
            d.text((x * ss, y * ss), t, font=f, fill=col(c),
                   anchor={"c": "mm", "l": "lm", "r": "rm"}[a])
    img = img.resize((W, H), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ----------------------------------------------------------------------------
# PDF backend (pure Python, PDF 1.4, base-14 Helvetica-Bold)
# ----------------------------------------------------------------------------

# AFM advance widths (1/1000 em) for Helvetica-Bold, chars 32..126.
_HELVB = {
    " ": 278, "!": 333, '"': 474, "#": 556, "$": 556, "%": 889, "&": 722, "'": 238,
    "(": 333, ")": 333, "*": 389, "+": 584, ",": 278, "-": 333, ".": 278, "/": 278,
    "0": 556, "1": 556, "2": 556, "3": 556, "4": 556, "5": 556, "6": 556, "7": 556,
    "8": 556, "9": 556, ":": 333, ";": 333, "<": 584, "=": 584, ">": 584, "?": 611,
    "@": 975, "A": 722, "B": 722, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778,
    "H": 722, "I": 278, "J": 556, "K": 722, "L": 611, "M": 833, "N": 722, "O": 778,
    "P": 667, "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722, "V": 667, "W": 944,
    "X": 667, "Y": 667, "Z": 611, "[": 333, "\\": 278, "]": 333, "^": 584, "_": 556,
    "`": 333, "a": 556, "b": 611, "c": 556, "d": 611, "e": 556, "f": 333, "g": 611,
    "h": 611, "i": 278, "j": 278, "k": 556, "l": 278, "m": 889, "n": 611, "o": 611,
    "p": 611, "q": 611, "r": 389, "s": 556, "t": 333, "u": 611, "v": 556, "w": 778,
    "x": 556, "y": 556, "z": 500, "{": 389, "|": 280, "}": 389, "~": 584,
}


def _text_width(s, size):
    return sum(_HELVB.get(ch, 556) for ch in s) / 1000.0 * size


def _pdf_escape(s):
    out = []
    for ch in s:
        if ch in "()\\":
            out.append("\\" + ch)
        else:
            try:
                ch.encode("cp1252")
                out.append(ch)
            except UnicodeEncodeError:
                out.append("?")
    return "".join(out)


def _n(v):
    s = ("%.2f" % float(v)).rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def _rgb(col):
    return "%s %s %s" % (_n(col[0]), _n(col[1]), _n(col[2]))


class PdfWriter:
    """Minimal vector PDF: one font (Helvetica-Bold), pages of primitives."""

    def __init__(self, page_w, page_h):
        self.page_w = page_w
        self.page_h = page_h
        self.pages = []  # content streams (bytes), one per page

    def add_page(self, dl):
        self.pages.append(self._content(dl))

    def _content(self, dl):
        H = self.page_h
        c = []
        for p in dl:
            if p[0] == "rect":
                _, x, y, w, h, col = p
                c.append("q %s rg %s %s %s %s re f Q" %
                         (_rgb(col), _n(x), _n(H - y - h), _n(w), _n(h)))
            elif p[0] == "line":
                _, x1, y1, x2, y2, lw, col = p
                c.append("q %s RG %s w %s %s m %s %s l S Q" %
                         (_rgb(col), _n(lw), _n(x1), _n(H - y1), _n(x2), _n(H - y2)))
            elif p[0] == "circle":
                _, cx, cy, r, col = p
                cy = H - cy
                k = 0.5523 * r
                c.append(
                    "q %s rg %s %s m "
                    "%s %s %s %s %s %s c "
                    "%s %s %s %s %s %s c "
                    "%s %s %s %s %s %s c "
                    "%s %s %s %s %s %s c f Q" % (
                        _rgb(col),
                        _n(cx + r), _n(cy),
                        _n(cx + r), _n(cy + k), _n(cx + k), _n(cy + r), _n(cx), _n(cy + r),
                        _n(cx - k), _n(cy + r), _n(cx - r), _n(cy + k), _n(cx - r), _n(cy),
                        _n(cx - r), _n(cy - k), _n(cx - k), _n(cy - r), _n(cx), _n(cy - r),
                        _n(cx + k), _n(cy - r), _n(cx + r), _n(cy - k), _n(cx + r), _n(cy)))
            elif p[0] == "text":
                _, x, y, t, sz, col, a = p
                tw = _text_width(t, sz)
                bx = x - {"c": tw / 2.0, "l": 0.0, "r": tw}[a]
                by = H - y - sz * 0.35  # baseline for vertical centering
                c.append("BT /F1 %s Tf %s rg 1 0 0 1 %s %s Tm (%s) Tj ET" %
                         (_n(sz), _rgb(col), _n(bx), _n(by), _pdf_escape(t)))
        return "\n".join(c).encode("cp1252", "replace")

    def render(self):
        # Object numbering: 1 catalog, 2 pages tree, 3 font, then per page
        # i (0-based): page object 4+2i, content stream 5+2i.
        widths = "[" + " ".join(str(_HELVB.get(chr(i), 556)) for i in range(32, 127)) + "]"
        objects = [b"<< /Type /Catalog /Pages 2 0 R >>", None]  # obj 1, 2 (2 filled later)
        font_obj = (b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
                    b"/Encoding /WinAnsiEncoding /FirstChar 32 /LastChar 126 /Widths "
                    + widths.encode("ascii") + b" >>")
        objects.append(font_obj)  # obj 3
        kids = []
        for i, content in enumerate(self.pages):
            content_num = 5 + 2 * i
            page_num = 4 + 2 * i
            kids.append("%d 0 R" % page_num)
            objects.append(("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %s %s] "
                            "/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>"
                            % (_n(self.page_w), _n(self.page_h), content_num)).encode("ascii"))
            objects.append(b"<< /Length " + str(len(content)).encode("ascii") +
                           b" >>\nstream\n" + content + b"\nendstream")
        objects[1] = ("<< /Type /Pages /Kids [%s] /Count %d >>"
                      % (" ".join(kids), len(self.pages))).encode("ascii")
        return self._assemble(objects)

    @staticmethod
    def _assemble(objects):
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for num, data in enumerate(objects, 1):
            offsets.append(len(out))
            out += ("%d 0 obj\n" % num).encode("ascii")
            out += data
            out += b"\nendobj\n"
        xref_pos = len(out)
        n = len(objects) + 1
        out += ("xref\n0 %d\n" % n).encode("ascii")
        out += b"0000000000 65535 f \n"
        for off in offsets:
            out += ("%010d 00000 n \n" % off).encode("ascii")
        out += ("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
                % (n, xref_pos)).encode("ascii")
        return bytes(out)


# ----------------------------------------------------------------------------
# PDF layout
# ----------------------------------------------------------------------------

PAGE_W, PAGE_H = 842.0, 595.0  # A4 landscape, points
MARGIN = 40.0
GAP = 18.0            # gutter between shapes in a row
CAPTION_H = 16.0      # space reserved under each shape for the caption
CAPTION_SIZE = 9.5
SECTION_SIZE = 15.0
TITLE_SIZE = 26.0
SUBTITLE_SIZE = 11.5
MIN_ROW_SCALE = 0.8   # shapes may be shrunk to this factor to share a row


def build_pdf(title, names, groups):
    """Assemble the multi-page chart PDF; return bytes."""
    total = sum(len(v) for v in groups.values())
    doc = PdfWriter(PAGE_W, PAGE_H)
    pages = []       # each: list of primitives (page coordinates)
    cur = []         # current page primitives
    y = MARGIN       # cursor, top of next free space

    def new_page():
        nonlocal cur, y
        pages.append(cur)
        cur = []
        y = MARGIN

    def need(h):
        nonlocal y
        if y + h > PAGE_H - MARGIN:
            new_page()

    # Chapter-style title block on the first page.
    cur.append(("text", PAGE_W / 2, MARGIN + TITLE_SIZE * 0.6, title, TITLE_SIZE,
                BLACK, "c"))
    rule_y = MARGIN + TITLE_SIZE * 0.6 + TITLE_SIZE * 0.55
    cur.append(("line", MARGIN, rule_y, PAGE_W - MARGIN, rule_y, 1.5, BLACK))
    sub = '"%s"  -  perfect fourths tuning  -  %d fingering%s in %d group%s' % (
        " ".join(names), total,
        "" if total == 1 else "s", len(groups),
        "" if len(groups) == 1 else "s")
    cur.append(("text", PAGE_W / 2, rule_y + SUBTITLE_SIZE * 1.6, sub, SUBTITLE_SIZE,
                GRAY, "c"))
    y = rule_y + SUBTITLE_SIZE * 1.6 + SECTION_SIZE + 14

    usable_w = PAGE_W - 2 * MARGIN
    usable_h = PAGE_H - 2 * MARGIN

    def pack_rows(items):
        """Greedy packing; several shapes share a row while the row keeps a
        reasonable scale, and no shape may outgrow the page vertically."""
        rows = []
        i = 0
        while i < len(items):
            row = [items[i]]
            i += 1
            while i < len(items):
                trial = row + [items[i]]
                nat_w = sum(it[1] for it in trial) + GAP * (len(trial) - 1)
                scale = min(1.0, usable_w / nat_w,
                            usable_h / max(it[2] for it in trial))
                if scale >= MIN_ROW_SCALE:
                    row = trial
                    i += 1
                else:
                    break
            rows.append(row)
        return rows

    def row_scale(row):
        nat_w = sum(it[1] for it in row) + GAP * (len(row) - 1)
        return min(1.0, usable_w / nat_w, usable_h / max(it[2] for it in row))

    for n_strings in sorted(groups):
        shapes = groups[n_strings]
        heading = "On %d string%s" % (n_strings, "" if n_strings == 1 else "s")
        heading_h = SECTION_SIZE * 1.4
        items = []
        for idx, sh in enumerate(shapes, 1):
            dl, w, h = draw_shape(sh)
            cap = "%d string%s  -  %d fret%s  -  fingering %d of %d" % (
                n_strings, "" if n_strings == 1 else "s", sh.width,
                "" if sh.width == 1 else "s", idx, len(shapes))
            items.append((dl, w, h + CAPTION_H, cap))

        rows = pack_rows(items)

        first_h = rows[0][0][2] * row_scale(rows[0]) if rows else 0.0
        need(heading_h + first_h)  # keep the heading with its first row
        cur.append(("text", MARGIN, y + SECTION_SIZE * 0.7, heading, SECTION_SIZE,
                    BLACK, "l"))
        y += heading_h

        for r in rows:
            scale = row_scale(r)
            nat_w = sum(it[1] for it in r) + GAP * (len(r) - 1)
            row_h = max(it[2] * scale for it in r)
            need(row_h)
            x = MARGIN + (usable_w - nat_w * scale) / 2
            for dl, w, h, cap in r:
                cur.extend(transform(dl, x, y, scale))
                cap_y = y + h * scale - CAPTION_SIZE * 0.6
                cur.append(("text", x + (w * scale) / 2, cap_y, cap, CAPTION_SIZE,
                            GRAY, "c"))
                x += w * scale + GAP * scale
            y += row_h + GAP * 0.6
        y += GAP * 0.8

    pages.append(cur)
    for pg in pages:
        doc.add_page(pg)
    return doc.render()


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

HELP_EPILOG = """\
interval names by semitones from the root (case matters!):
  0   P1
  1   m2
  2   M2
  3   A2  m3
  4   M3
  5   A3  P4
  6   A4  d5  TT
  7   P5
  8   A5  m6
  9   M6
  10  A6  m7
  11  M7
  12  P8   (the octave - never part of the input; added automatically)

examples:
  %(prog)s "P1 M3 P5" --title "Major chord arpeggio"
  %(prog)s P1 m3 P5 -t "Minor triad" --images --format svg
  %(prog)s "P1 M2 M3 P4 P5 M6 M7" -t "Major scale" --images

output: <dir>/<title>/<title>.pdf plus <dir>/<title>/images/ when --images is given.
by default <dir> is the folder containing this executable.
"""


def sanitize_title(title):
    """Filesystem-safe version of the title; keeps spaces and word characters."""
    t = re.sub(r'[\\/:%*?"<>|\x00-\x1f]', "_", title.strip())
    t = re.sub(r"\s+", " ", t).strip(" .-")
    return t[:120] or "chart"


def main(argv=None):
    exe_dir = os.path.dirname(os.path.realpath(__file__))
    ap = argparse.ArgumentParser(
        prog="sequence_visualiser",
        description="Chart every fingering of an interval sequence on a "
                    "guitar fretboard in perfect fourth tuning.",
        epilog=HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("intervals", nargs="+", metavar="INTERVALS",
                    help='interval sequence, e.g. "P1 M3 P5" (space or comma separated)')
    ap.add_argument("-t", "--title", required=True, metavar="TITLE",
                    help="chart title; also names the output folder and PDF")
    ap.add_argument("--images", action="store_true",
                    help="also save every shape as an image in an images/ subfolder")
    ap.add_argument("-f", "--format", choices=("png", "svg"), default="png",
                    help="image format for --images (default: png)")
    ap.add_argument("-o", "--dir", default=exe_dir, metavar="DIR",
                    help="output root folder (default: folder of the executable)")
    args = ap.parse_args(argv)

    names = parse_intervals(" ".join(args.intervals))
    groups = enumerate_shapes(names)
    total = sum(len(v) for v in groups.values())

    safe = sanitize_title(args.title)
    folder = os.path.join(args.dir, safe)
    os.makedirs(folder, exist_ok=True)
    pdf_path = os.path.join(folder, safe + ".pdf")

    pdf = build_pdf(args.title.strip(), names, groups)
    with open(pdf_path, "wb") as f:
        f.write(pdf)

    print('chart "%s"' % " ".join(names))
    for n in sorted(groups):
        print("  on %d string%s: %d fingering%s" %
              (n, "" if n == 1 else "s", len(groups[n]),
               "" if len(groups[n]) == 1 else "s"))
    print("  total: %d fingerings" % total)
    print("  pdf:   %s" % pdf_path)

    if args.images:
        img_dir = os.path.join(folder, "images")
        os.makedirs(img_dir, exist_ok=True)
        count = 0
        npad = max(2, len(str(max(groups))))
        for n in sorted(groups):
            shapes = groups[n]
            pad = max(2, len(str(len(shapes))))
            for idx, sh in enumerate(shapes, 1):
                dl, w, h = draw_shape(sh)
                name = "%0*dstrings-%0*d.%s" % (npad, n, pad, idx, args.format)
                path = os.path.join(img_dir, name)
                with open(path, "wb") as f:
                    if args.format == "svg":
                        f.write(svg_bytes(dl, w, h))
                    else:
                        f.write(png_bytes(dl, w, h))
                count += 1
        print("  images: %d files (%s) in %s" % (count, args.format, img_dir))


if __name__ == "__main__":
    main()
