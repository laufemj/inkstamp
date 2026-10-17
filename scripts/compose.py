#!/usr/bin/env python3
"""(library) Compose the annotated lecture-note PDF: original pages + professors' ink overlays (all videos)
+ handwritten-style margin notes with automatic placement that avoids the professor's ink."""
import io, re, os, json, sys
import numpy as np
import cv2
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.utils import ImageReader
from pypdf import PdfReader, PdfWriter

from paths import PDF as SRC, FONTS, PEN_FONT, FALLBACK_FONT
for _f in (PEN_FONT, FALLBACK_FONT):
    if not os.path.exists(os.path.join(FONTS, _f)):
        sys.exit(f'font {_f} not found in {FONTS} -> run: python scripts/fetch_fonts.py')
pdfmetrics.registerFont(TTFont('Pen', os.path.join(FONTS, PEN_FONT)))
pdfmetrics.registerFont(TTFont('Fb', os.path.join(FONTS, FALLBACK_FONT)))
PEN_CMAP = pdfmetrics.getFont('Pen').face.charToGlyph

PAGE_W, PAGE_H = 841.89, 1190.55
PX = 72 / 200.0
PW, PH = 2339, 3308          # 200-dpi page pixels
COL_X, COL_W = 1535, 730     # default right-margin column (px)
NOTE = HexColor('#0f5132')
STAR = HexColor('#c0392b')
BOX_BG = Color(0.93, 0.97, 0.93, alpha=0.78)
BOX_LINE = HexColor('#7aa07a')

def px(x, y):
    return x * PX, PAGE_H - y * PX

TOKEN_RE = re.compile(r'(\^\{[^}]*\}|_\{[^}]*\}|\\h\{.\})')
def _font_for(ch):
    return 'Pen' if PEN_CMAP.get(ord(ch), 0) else 'Fb'
def _runs(text):
    for part in TOKEN_RE.split(text):
        if not part:
            continue
        if part.startswith('\\h{'):
            ch = part[3:-1]
            yield ch, _font_for(ch), 1.0, 0.0, 'HAT'
            continue
        if part.startswith('^{'):
            inner, sf, rf = part[2:-1], 0.62, 0.42
        elif part.startswith('_{'):
            inner, sf, rf = part[2:-1], 0.62, -0.18
        else:
            inner, sf, rf = part, 1.0, 0.0
        cur = None; buf = ''
        for ch in inner:
            key = (_font_for(ch), STAR if ch == '★' else None)
            if key != cur and buf:
                yield buf, cur[0], sf, rf, cur[1]; buf = ''
            cur = key; buf += ch
        if buf:
            yield buf, cur[0], sf, rf, cur[1]
def _fsize(font, size, sf):
    return size * sf * (1.0 if font == 'Pen' else 0.74)
def rich_width(text, size):
    return sum(pdfmetrics.stringWidth(s, f, _fsize(f, size, sf)) for s, f, sf, rf, col in _runs(text))
def draw_rich(c, x, y, text, size, color):
    cx = x
    for s, f, sf, rf, col in _runs(text):
        fs = _fsize(f, size, sf)
        c.setFont(f, fs); c.setFillColor(color if col in (None, 'HAT') else col)
        yy = y + rf * size + (0.02 * size if (f == 'Fb' and sf == 1.0) else 0)
        c.drawString(cx, yy, s)
        w = pdfmetrics.stringWidth(s, f, fs)
        if col == 'HAT':
            hs = size * 0.75
            c.setFont('Fb', hs * 0.74)
            hw = pdfmetrics.stringWidth('^', 'Fb', hs * 0.74)
            c.drawString(cx + (w - hw) / 2, yy + size * 0.52, '^')
        cx += w
def wrap(text, size, width):
    lines = []
    for para in text.split('\n'):
        m = re.match(r'^((?:[·•※→①-⑩★]|예\)|\d\))\s*)', para)
        hang = rich_width(m.group(1), size) if m else 0
        words = para.split(' ')
        cur = ''; first = True
        for w in words:
            cand = (cur + ' ' + w) if cur else w
            avail = width if first else width - hang
            if rich_width(cand, size) <= avail:
                cur = cand
            elif not cur:
                piece = ''
                for ch in cand:
                    if rich_width(piece + ch, size) > avail and piece:
                        lines.append((piece, 0 if first else hang)); first = False; piece = ''
                        avail = width - hang
                    piece += ch
                cur = piece
            else:
                lines.append((cur, 0 if first else hang)); first = False
                cur = w
                if rich_width(cur, size) > width - hang:
                    piece = ''
                    for ch in cur:
                        if rich_width(piece + ch, size) > width - hang and piece:
                            lines.append((piece, hang)); piece = ''
                        piece += ch
                    cur = piece
        lines.append((cur, 0 if first else hang))
    return lines

LEADING = 1.3
def note_height_px(text, size, width_px, box=False, title=None):
    width = width_px * PX
    lines = wrap(text, size, width - (14 if box else 0))
    h = len(lines) * size * LEADING + (size * 1.5 if title else 0) + (12 if box else 0) + size * 0.3
    return h / PX

def draw_note(c, x_px, y_px, text, size, width_px, color=NOTE, box=False, title=None):
    x, ytop = px(x_px, y_px)
    width = width_px * PX
    lines = wrap(text, size, width - (14 if box else 0))
    lh = size * LEADING
    total_h = len(lines) * lh + (size * 1.5 if title else 0) + (12 if box else 0)
    if box:
        c.saveState(); c.setFillColor(BOX_BG); c.setStrokeColor(BOX_LINE); c.setLineWidth(1.1); c.setDash(5, 3)
        c.roundRect(x - 4, ytop - total_h, width + 8, total_h, 8, stroke=1, fill=1); c.restoreState()
    y = ytop - size * 0.95 - (6 if box else 0)
    xx = x + (7 if box else 0)
    if not box and len(lines) > 1:
        c.saveState(); c.setStrokeColor(color); c.setLineWidth(1.0); c.setLineCap(1)
        c.line(x - 7, ytop - 2, x - 7, ytop - total_h + 4)
        c.line(x - 7, ytop - 2, x - 2, ytop - 2); c.line(x - 7, ytop - total_h + 4, x - 2, ytop - total_h + 4)
        c.restoreState()
    if title:
        draw_rich(c, xx, y, title, size * 1.15, color)
        c.setStrokeColor(color); c.setLineWidth(0.9)
        c.line(xx, y - 3, xx + rich_width(title, size * 1.15), y - 3)
        y -= size * 1.5
    for ln, ind in lines:
        draw_rich(c, xx + ind, y, ln, size, color)
        y -= lh

class PagePlacer2D:
    """2-D occupancy map (200-dpi px, downsampled by DS) seeded from the ink overlay."""
    DS = 8
    def __init__(self, ink_png, page_png=None):
        self.occ = np.zeros((PH // self.DS + 1, PW // self.DS + 1), dtype=bool)
        if page_png and os.path.exists(page_png):   # the PDF's own text/figures are occupied too
            g = cv2.imread(page_png, cv2.IMREAD_GRAYSCALE)
            m = cv2.dilate((g < 200).astype(np.uint8), np.ones((25, 25), np.uint8))
            self.occ |= cv2.resize(m, (self.occ.shape[1], self.occ.shape[0]), interpolation=cv2.INTER_AREA) > 0
        if ink_png and os.path.exists(ink_png):
            a = cv2.imread(ink_png, cv2.IMREAD_UNCHANGED)[:, :, 3]
            m = (a > 60).astype(np.uint8)
            m = cv2.dilate(m, np.ones((21, 21), np.uint8))
            small = cv2.resize(m, (self.occ.shape[1], self.occ.shape[0]), interpolation=cv2.INTER_AREA) > 0
            self.occ |= small
        self.occ[(PH - 110) // self.DS:, :] = True
    def free(self, x0, y0, x1, y1):
        ds = self.DS
        sub = self.occ[max(0, y0 // ds): y1 // ds + 1, max(0, x0 // ds): x1 // ds + 1]
        return not sub.any()
    def find(self, x0, w, y_desired, h, y_max=None, up=450):
        """nearest free slot: search downward from y_desired, and upward up to `up` px (penalised)."""
        h = int(h) + 20
        x0m, x1m = x0 - 12, x0 + w + 12
        limit = PH if y_max is None else y_max
        best = None
        y = (int(max(60, y_desired)) // self.DS) * self.DS
        while y + h <= limit:
            if self.free(x0m, y, x1m, y + h):
                best = (y - y_desired, y); break
            y += self.DS
        y = (int(max(60, y_desired)) // self.DS) * self.DS - self.DS
        while y >= max(60, y_desired - up):
            if y + h <= limit and self.free(x0m, y, x1m, y + h):
                d = (y_desired - y) * 1.5
                if best is None or d < best[0]:
                    best = (d, y)
                break
            y -= self.DS
        return None if best is None else best[1]
    def take(self, x0, w, y, h):
        ds = self.DS
        self.occ[max(0, (int(y) - 12) // ds): (int(y + h) + 12) // ds + 1, max(0, (x0 - 12) // ds): (x0 + w + 12) // ds + 1] = True

COLUMN_CONFIGS = [(COL_X, COL_W), (1860, 405), (1535, 420), (1535, 300), (1980, 290)]
FALLBACK_CONFIGS = [(215, 1300), (215, 2050), (760, 1500)]   # blank areas in the body (below/between text), last resort

def place_notes(c, page, notes, ink_png):
    from paths import RENDER
    pl = PagePlacer2D(ink_png, os.path.join(RENDER, f'page{page}.png') if isinstance(page, int) else None)
    if not isinstance(page, int):   # memo page: keep its header line free
        pl.occ[: 215 // pl.DS + 1, :] = True
    report = []
    for n in notes:
        size0 = n.get('size', 14)
        min_size = n.get('min_size', 11.5)
        if 'x' in n or 'width' in n:
            configs = [(n.get('x', COL_X), n.get('width', COL_W))]
        else:
            configs = COLUMN_CONFIGS
        best = None   # (distance, x0, w, y, h, size)
        for (x0, w) in configs + ([] if ('x' in n or 'width' in n) else FALLBACK_CONFIGS):
            if (x0, w) in FALLBACK_CONFIGS and best is not None:
                break
            if n.get('title') and rich_width(n['title'], size0 * 1.15) > w * PX - 14 and len(configs) > 1:
                continue   # a box title is not wrapped: skip columns narrower than it
            size = size0
            while size >= min_size - 1e-6:
                h = note_height_px(n['text'], size, w, n.get('box', False), n.get('title'))
                y = pl.find(x0, w, n['y'], h)
                if y is not None:
                    d = y - n['y'] + (0 if w >= 700 else 350 + 0.4 * h) + (size0 - size) * 60
                    if best is None or d < best[0]:
                        best = (d, x0, w, y, h, size)
                    break
                size -= 0.5
            if best is not None and best[0] <= 120 and best[2] >= 700:
                break
        if best is None:
            x0, w = configs[0]; size = size0
            h = note_height_px(n['text'], size, w, n.get('box', False), n.get('title'))
            y = n['y']
            report.append(f'  !! page {page}: could not fit note at y={n["y"]} ({n["text"][:30]}...) -> overlapping')
        else:
            d, x0, w, y, h, size = best
        pl.take(x0, w, y, h)
        draw_note(c, x0, y, n['text'], size, w, box=n.get('box', False), title=n.get('title'))
        flag = '' if abs(y - n['y']) < 300 else '  <-- moved'
        report.append(f'  page {page}: x={x0} w={w} y={y} (want {n["y"]}) h={int(h)} size={size} {n["text"][:26]!r}{flag}')
    return report

MEMO_X, MEMO_W = 215, 1900
def _memo_page(writer, pno, notes):
    """blank page after page pno holding notes that did not fit its margins (NOTES key 'pno+')"""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
    draw_note(c, MEMO_X, 110, f'{pno}쪽 메모 — {pno}쪽 여백이 교수님 필기로 가득 차서 여기에 적음', 15, MEMO_W)
    c.saveState(); c.setStrokeColor(BOX_LINE); c.setLineWidth(1); c.line(*px(MEMO_X, 190), *px(MEMO_X + MEMO_W, 190)); c.restoreState()
    notes = [dict(n, x=n.get('x', MEMO_X), width=n.get('width', MEMO_W), y=max(230, n['y'])) for n in sorted(notes, key=lambda n: n['y'])]
    report = place_notes(c, f'{pno}+', notes, None)
    c.setFont('Fb', 9); c.setFillColor(NOTE); c.drawCentredString(PAGE_W / 2, 28, f'({pno}쪽 메모)')
    c.showPage(); c.save(); buf.seek(0)
    writer.add_page(PdfReader(buf).pages[0])
    return report

def build(notes_by_page, ink_dir, out_path, extra_draw=None):
    reader = PdfReader(SRC)
    writer = PdfWriter()
    report = []
    for i, page in enumerate(reader.pages):
        pno = i + 1
        ink_png = f'{ink_dir}/ink_page{pno}.png'
        has_ink = os.path.exists(ink_png)
        notes = notes_by_page.get(pno, [])
        if not has_ink and not notes:
            writer.add_page(page)
            if notes_by_page.get(f'{pno}+'):
                report += _memo_page(writer, pno, notes_by_page[f'{pno}+'])
            continue
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
        if has_ink:
            img = Image.open(ink_png).convert('RGBA')
            c.drawImage(ImageReader(img), 0, 0, width=PAGE_W, height=PAGE_H, mask='auto')
        if notes:
            report += place_notes(c, pno, notes, ink_png if has_ink else None)
        if extra_draw:
            extra_draw(c, pno)
        c.showPage(); c.save(); buf.seek(0)
        page.merge_page(PdfReader(buf).pages[0])
        writer.add_page(page)
        memo = notes_by_page.get(f'{pno}+')
        if memo:   # margins of page pno were full -> blank memo page inserted right after it
            report += _memo_page(writer, pno, memo)
    with open(out_path, 'wb') as f:
        writer.write(f)
    print('\n'.join(report))
    print('wrote', out_path, os.path.getsize(out_path))

if __name__ == '__main__':
    print('library module; import and call build()')
