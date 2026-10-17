"""render pages of a built PDF side by side: python render_check.py out.jpg pdf p1 p2 ... (dpi 90)"""
import sys, pypdfium2 as pdfium
from PIL import Image
out, pdf, pages = sys.argv[1], sys.argv[2], [int(x) for x in sys.argv[3:]]
doc = pdfium.PdfDocument(pdf)
ims = [doc[p - 1].render(scale=90 / 72).to_pil() for p in pages]
W = sum(i.width for i in ims); H = max(i.height for i in ims)
sheet = Image.new('RGB', (W, H), 'white'); x = 0
for i in ims:
    sheet.paste(i, (x, 0)); x += i.width
sheet.save(out, quality=85)
