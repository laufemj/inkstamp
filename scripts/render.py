"""Render the lecture PDF at 200 dpi -> work/render/page{p}.png (skips existing)."""
import os, pypdfium2 as pdfium
from paths import PDF, RENDER, DPI
def main():
    doc = pdfium.PdfDocument(PDF)
    for i in range(len(doc)):
        out = os.path.join(RENDER, f'page{i+1}.png')
        if not os.path.exists(out):
            doc[i].render(scale=DPI / 72).to_pil().convert('RGB').save(out)
    print('pages', len(doc), '->', RENDER)
if __name__ == '__main__':
    main()
