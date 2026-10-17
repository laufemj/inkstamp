"""End-to-end demo / smoke test with SYNTHETIC material (no real lecture involved).

1. writes a one-page lecture-note PDF (A4, ordinary margins),
2. fakes three frames of an iPad screen recording of that page with the "professor's" ink on it
   (handwriting, highlighter, a sketch, and one laser-pointer stroke that must NOT end up in the output),
3. runs the real pipeline on them: render -> align -> rescue_align -> overlay -> clean_specks -> build,
   with an English notes file standing in for the notes Claude would write from the transcript,
4. optionally saves a side-by-side figure (frame -> annotated page).

usage (with the skill's python):  python examples/make_demo.py [out_dir] [--figure docs/demo.png]
Transcription is not exercised here (there is no audio); use `scripts/transcribe.py --probe-only` for that."""
import os, sys, json, subprocess, shutil
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from demo_fonts import font_path

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
SC = os.path.join(SKILL, 'scripts')
args = [a for a in sys.argv[1:] if not a.startswith('--')]
FIG = sys.argv[sys.argv.index('--figure') + 1] if '--figure' in sys.argv else None
if FIG in args:
    args.remove(FIG)
OUT = os.path.abspath(args[0] if args else 'lecnotes_demo')
WORK = os.path.join(OUT, '_work')
KEY = 'L3-1'
PT = 200 / 72.0                      # pt -> 200-dpi px

# ------------------------------------------------------------------ 1. synthetic lecture-note PDF (A4)
W_PT, H_PT = 595.28, 841.89
LM = 62                              # left margin (pt); text block ends ~72 pt from the right edge
LINES = []                           # (y_pt_from_top, kind, text) - also used to anchor the notes

def make_pdf(path):
    pdfmetrics.registerFont(TTFont('Noto', os.path.join(SKILL, 'fonts', 'NotoSansKR[wght].ttf')))
    c = canvas.Canvas(path, pagesize=(W_PT, H_PT))
    y = 70
    def put(text, size=10.2, dy=16, x=LM, kind='p', center=False):
        nonlocal y
        c.setFont('Noto', size)
        if center:
            c.drawCentredString(W_PT / 2 - 10, H_PT - y, text)
        else:
            c.drawString(x, H_PT - y, text)
        LINES.append((y, kind, text)); y += dy
    put('4  Integral theorems', 15, 26, kind='h')
    put('4.2  The divergence theorem', 12.5, 22, kind='h')
    put('Let R be a bounded region in R³ whose boundary ∂R is a closed, piecewise smooth')
    put('surface with outward unit normal n. For every C¹ vector field F defined on R,', dy=30)
    put('∬∂R  F · n dS  =  ∭R  div F dV', 15, 34, kind='f', center=True)
    put('Interpretation. div F(X) is the instantaneous rate at which a tiny fluid element')
    put('around X expands. The theorem says: total outflow through the boundary = total')
    put('expansion inside. Nothing more, nothing less.', dy=26)
    put('Example 1.  F(x, y, z) = (x, y, z) on the unit ball B.', kind='e')
    put('div F = 3, hence  ∬∂B F · n dS = 3 · vol(B) = 3 · 4π/3 = 4π.', x=LM + 18, dy=26)
    put('Example 2.  (solid angle field)  A(X) = X / |X|³,  X ≠ 0.', kind='e')
    put('div A = 0 away from the origin, but A is undefined at 0, so the theorem cannot be', x=LM + 18)
    put('applied to a region containing 0. Cut out a small ball B_ε: for any closed surface S', x=LM + 18)
    put('enclosing the origin,   ∬S A · n dS = 4π;   otherwise it is 0.', x=LM + 18, dy=26)
    put('Corollary.  If div F ≡ 0 on R, the flux of F through ∂R vanishes.', kind='e', dy=26)
    put('Proof (sketch).  Cut R into small boxes. For one box, opposite faces contribute')
    put('F(x+Δx) − F(x) ≈ ∂F/∂x Δx times the face area; summing over the six faces gives')
    put('div F · ΔV. Interior faces cancel in pairs (opposite normals), only ∂R survives.', dy=26)
    put('Exercise.  Verify the theorem for F = (x², y², z²) on the unit cube [0,1]³.', kind='e', dy=26)
    put('Remark.  In R² the same argument gives Green\'s theorem in flux form:')
    put('∮∂D F · n ds = ∬D div F dA.', 12.5, 30, center=True)
    c.setFont('Noto', 9); c.drawCentredString(W_PT / 2, 30, '27')
    c.showPage(); c.save()

def ypx(kind_or_text):
    """baseline y (px) of the first line of that kind, else of the first line containing the text"""
    for y, k, t in LINES:
        if kind_or_text == k:
            return int(y * PT)
    for y, k, t in LINES:
        if kind_or_text in t:
            return int(y * PT)
    raise KeyError(kind_or_text)

def xspan(line_start, phrase, size=10.2, x0=LM):
    """x range (px) of `phrase` inside the line that starts with `line_start`"""
    t = next(t for y, k, t in LINES if t.startswith(line_start))
    a = x0 + pdfmetrics.stringWidth(t[:t.index(phrase)], 'Noto', size)
    return int(a * PT), int((a + pdfmetrics.stringWidth(phrase, 'Noto', size)) * PT)

# ------------------------------------------------------------------ 2. the "professor's" ink + fake iPad frames
def ink_layer(shape):
    """BGRA ink on the 200-dpi page (what the professor wrote during the lecture)"""
    h, w = shape[:2]
    ink = np.zeros((h, w, 4), np.uint8)
    def stroke(fn, color, **kw):
        tmp = np.zeros((h, w, 3), np.uint8); fn(tmp, **kw)
        m = tmp.any(axis=2); ink[m, :3] = color; ink[m, 3] = 255
    hand_font = font_path('hand', fallback=os.path.join(SKILL, 'fonts', 'NanumPenScript-Regular.ttf'))
    def hand(text, x, base, size, angle, color):
        """handwritten words (Caveat, slightly tilted), baseline starting at (x, base)"""
        f = ImageFont.truetype(hand_font, size)
        try:
            f.set_variation_by_axes([620])
        except Exception:
            pass
        img = Image.new('L', (int(f.getlength(text)) + 2 * size, 3 * size), 0)
        ImageDraw.Draw(img).text((size, 2 * size), text, font=f, fill=255, anchor='ls')
        a = np.array(img.rotate(angle, resample=Image.BICUBIC, center=(size, 2 * size)))
        x0, y0 = x - size, base - 2 * size
        ys, xs = slice(max(0, y0), min(h, y0 + a.shape[0])), slice(max(0, x0), min(w, x0 + a.shape[1]))
        sub = a[ys.start - y0: ys.stop - y0, xs.start - x0: xs.stop - x0]
        region = ink[ys, xs]; m = sub > 0
        region[m, :3] = color; region[m, 3] = np.maximum(region[m, 3], sub[m])
    fy = ypx('f')
    stroke(lambda im: cv2.ellipse(im, (w // 2 - 28, fy - 16), (430, 64), 0, 0, 360, (255, 255, 255), 6, cv2.LINE_AA), (40, 40, 210))
    hand('must memorize!', int(w * 0.70), fy - 95, 96, 4, (200, 80, 30))
    y_n = ypx('surface with outward')
    a0, a1 = xspan('surface with outward', 'outward unit normal n')
    hl = np.zeros((h, w, 3), np.uint8); cv2.rectangle(hl, (a0 - 6, y_n - 36), (a1 + 6, y_n + 10), (255, 255, 255), -1)
    m = hl.any(axis=2) & (ink[:, :, 3] == 0); ink[m, :3] = (60, 230, 250); ink[m, 3] = 120          # yellow highlighter
    y1 = ypx('Example 1.')
    cx, cy, r = int(w * 0.80), y1 + 60, 95                                                            # sketch: ball with outward arrows
    stroke(lambda im: cv2.circle(im, (cx, cy), r, (255, 255, 255), 5, cv2.LINE_AA), (60, 160, 40))
    for ang in range(0, 360, 45):
        a = np.deg2rad(ang); p0 = (int(cx + r * np.cos(a)), int(cy + r * np.sin(a))); p1 = (int(cx + 1.6 * r * np.cos(a)), int(cy + 1.6 * r * np.sin(a)))
        stroke(lambda im: cv2.arrowedLine(im, p0, p1, (255, 255, 255), 4, cv2.LINE_AA, tipLength=0.3), (200, 80, 30))
    y2 = ypx('Example 2.')
    hand('exam!', int(w * 0.80), y2 + 10, 112, -5, (30, 30, 220))
    yx = ypx('Exercise.')
    t_ex = next(t for y, k, t in LINES if t.startswith('Exercise.'))
    x_end = xspan('Exercise.', t_ex)[1]
    stroke(lambda im: cv2.line(im, (int(LM * PT), yx + 14), (x_end, yx + 14), (255, 255, 255), 5, cv2.LINE_AA), (200, 80, 30))
    hand('do it yourself', x_end + 30, yx + 8, 74, 2, (200, 80, 30))
    return ink

def laser(frame, p0, p1):
    """GoodNotes laser pointer as measured on real recordings: ~20 px soft pink halo, a thin saturated red rim and a
    white core (overlay.py must drop it)"""
    m = np.zeros(frame.shape[:2], np.uint8); cv2.line(m, p0, p1, 255, 1, cv2.LINE_8)
    d = np.minimum(cv2.distanceTransform(255 - m, cv2.DIST_L2, 5), 200)
    halo = (0.35 * np.exp(-(d / 18.0) ** 2))[..., None]                 # wide faint glow (S ~ 64 at 5 px, ~ 20 at 20 px)
    rim = ((d >= 1.5) & (d <= 4.5))[..., None].astype(np.float32)       # saturated rim
    red = np.zeros_like(frame, dtype=np.float32); red[:] = (60, 40, 240)
    out = frame.astype(np.float32) * (1 - halo) + red * halo
    out = out * (1 - rim) + red * rim
    out[d < 1.5] = (255, 255, 255)
    return out.astype(np.uint8)

def make_frames(page_png, views_dir):
    page = cv2.imread(page_png)
    ink = ink_layer(page.shape)
    a = ink[:, :, 3:4].astype(np.float32) / 255
    inked = (page * (1 - a) + ink[:, :, :3] * a).astype(np.uint8)
    FW, FH, UI = 2388, 1668, 258
    k = 2200 / page.shape[1]
    big = cv2.resize(inked, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    os.makedirs(views_dir, exist_ok=True)
    frames = []
    for idx, (oy, t) in enumerate([(0, 610), (720, 1730), (1290, 2650)]):
        f = np.full((FH, FW, 3), 232, np.uint8)
        top = int(oy * k); crop = big[top: top + FH - UI]
        f[UI: UI + crop.shape[0], 94: 94 + crop.shape[1]] = crop
        f[:UI] = (110, 80, 67)                                      # app chrome (status bar + toolbar)
        f[150:UI] = (245, 245, 245)
        for j, col in enumerate([(0, 0, 0), (200, 80, 30), (40, 40, 210), (60, 160, 40), (60, 230, 250)]):
            cv2.circle(f, (1500 + 70 * j, 204), 22, col, -1, cv2.LINE_AA)
        cv2.putText(f, '9:41  Mon Sep 1', (40, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(f, 'lecture_notes.pdf', (1000, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (255, 255, 255), 2, cv2.LINE_AA)
        if idx == 1:
            f = laser(f, (400, 900), (1500, 820))
        name = os.path.join(views_dir, f'v_{idx * 10:04d}_{t:05d}s.jpg')
        cv2.imencode('.jpg', f, [cv2.IMWRITE_JPEG_QUALITY, 95])[1].tofile(name)
        frames.append(name)
    return frames

# ------------------------------------------------------------------ 3. notes (stand-in for what Claude writes from the transcript)
def write_notes(path):
    y_f, y_e1, y_e2, y_c, y_x = ypx('f'), ypx('Example 1.'), ypx('Example 2.'), ypx('Corollary.'), ypx('Exercise.')
    notes = {1: [
        dict(y=ypx('4.2'), size=12.5, box=True, title='★ Lecture 3-1 (9/1, 48 min) highlights',
             text='① ★ “This theorem will be on the midterm. Know both sides by heart.” (12:40)\n'
                  '② div F = expansion rate of a tiny fluid element; outflow = expansion inside (15:05)\n'
                  '③ ★ Example 2: A is undefined at 0, so cut out a ball first. “I will ask exactly this.” (31:20)\n'
                  '④ ★ Exercise: “do it yourself, it may be on the exam” (44:10)\n'
                  '※ Nothing was excluded from the exam scope.'),
        dict(y=y_f, size=12.5, text='★ (12:40) “On the midterm. Memorize both sides.” n always points OUTWARD; flipping it flips the sign of the flux.'),
        dict(y=y_e1, size=12.5, text='(21:10) Sketch on the board: the field leaves the ball radially, so flux = 3 · volume. “Check it in polar coordinates too.”'),
        dict(y=y_e2, size=12.5, text='★ (31:20) “I will ask exactly this.” Why cut out B_ε: the theorem needs F to be C¹ on the whole region.'),
        dict(y=y_c, size=12.5, text='(36:05) Correction on the board: the proof sketch should read ∂F_{1}/∂x Δx, not ∂F/∂x Δx (one component per pair of faces).'),
        dict(y=y_x, size=12.5, text='★ (44:10) “Do it yourself, it may be on the exam.” Both sides come out to 3.\n— end of Lecture 3-1 (48:12)'),
    ]}
    with open(path, 'w', encoding='utf-8') as f:
        f.write('# -*- coding: utf-8 -*-\n# synthetic demo notes\nNOTES = ' + repr(notes) + '\nSUMMARY = "demo"\n')

# ------------------------------------------------------------------ 4. figure
def figure(frame_path, pdf_path, out_png):
    import pypdfium2 as pdfium
    fr = Image.open(frame_path).convert('RGB')
    pg = pdfium.PdfDocument(pdf_path)[0].render(scale=1.15).to_pil().convert('RGB')
    H = 1100
    pg = pg.resize((int(pg.width * H / pg.height), H), Image.LANCZOS)
    fw = 1000; fr = fr.resize((fw, int(fr.height * fw / fr.width)), Image.LANCZOS)
    gap, pad, cap, foot = 120, 40, 70, 60
    W = pad + fr.width + gap + pg.width + pad
    canvas_img = Image.new('RGB', (W, H + cap + pad * 2 + foot), (255, 255, 255))
    canvas_img.paste(fr, (pad, cap + pad + (H - fr.height) // 2))
    canvas_img.paste(pg, (pad + fr.width + gap, cap + pad))
    d = ImageDraw.Draw(canvas_img)
    try:
        font = ImageFont.truetype(os.path.join(SKILL, 'fonts', 'NotoSansKR[wght].ttf'), 30)
    except OSError:
        font = ImageFont.load_default()
    d.text((pad, pad // 2), 'iPad screen recording (1 of 3 frames)', fill=(60, 60, 60), font=font)
    d.text((pad + fr.width + gap, pad // 2), 'annotated PDF page (generated)', fill=(60, 60, 60), font=font)
    small = ImageFont.truetype(os.path.join(SKILL, 'fonts', 'NotoSansKR[wght].ttf'), 22) if font != ImageFont.load_default() else font
    d.text((pad, cap + pad + (H + fr.height) // 2 + 14), 'the glowing red line is a laser-pointer stroke: it is dropped, real ink is kept', fill=(120, 120, 120), font=small)
    d.text((pad, H + cap + pad * 2 + 10), 'Synthetic demo (examples/make_demo.py): the lecture page, the handwriting and the quoted remarks are made up. '
           'The A4 page had no room for notes, so its right margin was widened automatically.', fill=(120, 120, 120), font=small)
    ax0, ay = pad + fr.width + 20, cap + pad + H // 2
    d.line((ax0, ay, ax0 + gap - 40, ay), fill=(90, 90, 90), width=6)
    d.polygon([(ax0 + gap - 40, ay - 16), (ax0 + gap - 40, ay + 16), (ax0 + gap - 14, ay)], fill=(90, 90, 90))
    d.rectangle((pad + fr.width + gap - 1, cap + pad - 1, pad + fr.width + gap + pg.width, cap + pad + H), outline=(200, 200, 200), width=2)
    os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)
    canvas_img.save(out_png, optimize=True)
    print('figure ->', out_png, canvas_img.size)

# ------------------------------------------------------------------ main
def run(script, *a):
    env = dict(os.environ, LECNOTES_JOB=os.path.join(OUT, 'lecnotes_job.json'), PYTHONIOENCODING='utf-8')
    r = subprocess.run([sys.executable, os.path.join(SC, script), *a], cwd=OUT, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode:
        sys.exit(f'{script} failed:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}')
    return r.stdout

def main():
    if os.path.exists(WORK):
        shutil.rmtree(WORK)
    os.makedirs(OUT, exist_ok=True)
    make_pdf(os.path.join(OUT, 'lecture_notes.pdf'))
    job = dict(course_dir=OUT, course_title='Demo', lecture_pdf='lecture_notes.pdf', out_pdf='lecture_notes_annotated.pdf',
               work_dir='_work', transcript_dir='transcripts', language='en', min_page=1,
               videos=[dict(key=KEY, file='Lecture 3-1.mp4', date='2026-09-01')])
    json.dump(job, open(os.path.join(OUT, 'lecnotes_job.json'), 'w', encoding='utf-8'), indent=1)
    run('render.py')
    frames = make_frames(os.path.join(WORK, 'render', 'page1.png'), os.path.join(WORK, f'views_{KEY}'))
    print(run('align.py', KEY).strip().splitlines()[-1])
    print(run('rescue_align.py', KEY).strip().splitlines()[-1])
    out = run('overlay.py'); print([l for l in out.splitlines() if 'laser' in l][0])
    run('clean_specks.py', '1')
    os.makedirs(os.path.join(WORK, 'notes'), exist_ok=True)
    write_notes(os.path.join(WORK, 'notes', f'notes_{KEY}.py'))
    out = run('build.py'); print('\n'.join(l for l in out.splitlines() if '!!' in l or 'wrote' in l))
    if FIG:
        figure(frames[1], os.path.join(OUT, 'lecture_notes_annotated.pdf'), FIG)

if __name__ == '__main__':
    main()
