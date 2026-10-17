"""print y positions (200-dpi px) of text lines on a page, to anchor margin notes.  usage: python layout.py <page> [regex]"""
import sys, re, pypdfium2 as pdfium
from paths import PDF
p = int(sys.argv[1]); pat = sys.argv[2] if len(sys.argv) > 2 else None
page = pdfium.PdfDocument(PDF)[p - 1]; H = page.get_height(); tp = page.get_textpage()
rows = []
for i in range(tp.count_rects()):
    l, b, r, t = tp.get_rect(i)
    txt = tp.get_text_bounded(l, b, r, t).replace('\r', ' ').replace('\n', ' ').strip()
    if txt:
        rows.append(((H - t) / 72 * 200, (H - b) / 72 * 200, l / 72 * 200, r / 72 * 200, txt))
# merge segments on the same line
rows.sort(key=lambda r: (round(r[0] / 25), r[2])); merged = []
for r in rows:
    if merged and abs(merged[-1][0] - r[0]) < 18:
        m = merged[-1]; merged[-1] = (min(m[0], r[0]), max(m[1], r[1]), m[2], max(m[3], r[3]), m[4] + '  ' + r[4])
    else:
        merged.append(r)
for y0, y1, x0, x1, txt in merged:
    if pat and not re.search(pat, txt):
        continue
    print(f"y={y0:6.0f}-{y1:6.0f}  x={x0:5.0f}-{x1:5.0f}  {txt[:90]}")
