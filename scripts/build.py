"""Merge all notes files + ink overlays onto the lecture PDF and write the annotated PDF.
Notes files: <work>/notes/notes_*.py, each with NOTES = {page: [dict(y=..., text=..., ...), ...]} (format: references/notes_guide.md).
Merge order: files that are not a job video (e.g. notes_00_*.py, earlier lectures) in natural name order, then the job videos in order.
A notes file may also define patch(N) which edits the merged dict so far (e.g. update the page-1 guide title,
remove the previous run's 'video ends here' box).
usage: python build.py [--check-only] [--only KEY ...] [--out PATH] [--overlay-scale 0.75]"""
import sys, os, glob, argparse, importlib.util
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
from paths import OVERLAY, NOTES_DIR, OUT_PDF, W
import cv2
import compose as cm
from reportlab.pdfbase import pdfmetrics
ap = argparse.ArgumentParser()
ap.add_argument('--out', default=OUT_PDF)
ap.add_argument('--overlay-scale', type=float, default=1.0)
ap.add_argument('--only', nargs='*')
ap.add_argument('--check-only', action='store_true')
a = ap.parse_args()
import re
def _nat(f):   # natural order: notes_00_* < notes_L4-1 < notes_L10-1
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', os.path.basename(f))]
files = sorted(glob.glob(os.path.join(NOTES_DIR, 'notes_*.py')), key=_nat)
keyed = {os.path.basename(f)[6:-3]: f for f in files}
ordered = [f for k, f in keyed.items() if k not in paths.ORDER] + [keyed[k] for k in paths.ORDER if k in keyed]
missing = [k for k in paths.ORDER if k not in keyed]
if missing:
    print('MISSING notes for', missing)
fb = pdfmetrics.getFont('Fb').face.charToGlyph
def _pk(p):   # page key: 42, or '42+' = memo page inserted after page 42
    return p if isinstance(p, str) and p.endswith('+') else int(p)
N = {}
for f in ordered:
    key = os.path.basename(f)[6:-3]
    spec = importlib.util.spec_from_file_location('notes_' + key.replace('-', '_'), f)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    if hasattr(mod, 'patch'):
        mod.patch(N)
    if a.only and key not in a.only:
        for p, lst in mod.NOTES.items():
            N.setdefault(_pk(p), []).extend(lst)
        continue
    bad = set()
    for p, lst in mod.NOTES.items():
        for n in lst:
            for ch in n['text'] + (n.get('title') or ''):
                if ch not in ' \n' and not cm.PEN_CMAP.get(ord(ch), 0) and not fb.get(ord(ch), 0):
                    bad.add(ch)
        N.setdefault(_pk(p), []).extend(lst)
    print(f'{key}: pages {sorted((_pk(p) for p in mod.NOTES), key=str)}, notes {sum(len(v) for v in mod.NOTES.values())}' + (f'  !! UNSUPPORTED CHARS {sorted(bad)}' if bad else ''))
if a.check_only:
    sys.exit(0)
ink = OVERLAY
if a.overlay_scale != 1.0:
    sd = os.path.join(W, 'overlay_s'); os.makedirs(sd, exist_ok=True)
    for fn in glob.glob(os.path.join(ink, 'ink_page*.png')):
        im = cv2.imread(fn, cv2.IMREAD_UNCHANGED); s = a.overlay_scale
        cv2.imwrite(os.path.join(sd, os.path.basename(fn)), cv2.resize(im, (int(im.shape[1] * s), int(im.shape[0] * s)), interpolation=cv2.INTER_AREA))
    ink = sd
cm.build(N, ink, a.out)
