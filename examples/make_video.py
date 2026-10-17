"""Render the README demo video from the synthetic demo of examples/make_demo.py: docs/demo.mp4 (H.264, 1080p) and docs/demo.gif.
A macOS-style desktop (wallpaper, menu bar, Dock, windows) set in Instrument Serif, Inter and JetBrains Mono (SIL OFL,
downloaded to fonts/video/ on first use). Everything shown is made up (page, handwriting, remarks); no real course material.
usage (with the skill's python):  python examples/make_demo.py <demo_dir>
                                  python examples/make_icon.py
                                  python examples/make_video.py <demo_dir> [--out docs] [--preview] [--gif]"""
import os, sys, json
import numpy as np, av, cv2, pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from demo_fonts import font_path

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
args = [a for a in sys.argv[1:] if not a.startswith('--')]
DEMO = os.path.abspath(args[0])
OUT = os.path.abspath(sys.argv[sys.argv.index('--out') + 1]) if '--out' in sys.argv else os.path.join(SKILL, 'docs')
WORK = os.path.join(DEMO, '_work')
W, H, FPS = 1920, 1080, 30
INK, MUTED, GREEN, CORAL = (28, 29, 33), (88, 92, 99), (15, 81, 50), (214, 112, 82)

# ------------------------------------------------------------------ fonts (examples/demo_fonts.py)
_fonts = {}
def font(key, size, wght=400):
    if (key, size, wght) not in _fonts:
        f = ImageFont.truetype(font_path(key), size)
        try:   # variable fonts: set weight (and optical size, for Inter)
            f.set_variation_by_axes([{b'Weight': wght, b'Optical size': min(32, max(14, size))}.get(a.get('name'), a.get('default'))
                                     for a in f.get_variation_axes()])
        except Exception:
            pass
        _fonts[key, size, wght] = f
    return _fonts[key, size, wght]
STAR_FONT = os.path.join(SKILL, 'fonts', 'NotoSansKR[wght].ttf')   # Inter has no ★

def clamp(t): return min(1.0, max(0.0, t))
def ease_out(t): t = clamp(t); return 1 - (1 - t) ** 3
def ease_io(t): t = clamp(t); return t * t * (3 - 2 * t)
def fit(img, w, h):
    s = min(w / img.width, h / img.height)
    return img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.LANCZOS)

# ------------------------------------------------------------------ desktop: wallpaper, menu bar, Dock
def wallpaper():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    base = np.array([226, 230, 246], np.float32) * (1 - xx[..., None] / W) + np.array([250, 233, 222], np.float32) * (xx[..., None] / W)
    for cx, cy, r, col, a in [(380, 820, 620, (196, 214, 250), 0.55), (1560, 260, 560, (253, 214, 196), 0.5), (1150, 980, 520, (208, 236, 222), 0.45)]:
        g = np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * r * r)))[..., None] * a
        base = base * (1 - g) + np.array(col, np.float32) * g
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).convert('RGBA')
WALL = wallpaper()
ICON = Image.open(os.path.join(SKILL, 'docs', 'icon.png')).convert('RGBA')

def app_icon(kind, s):
    """small generic Dock icons drawn here (no trademarked artwork)"""
    if kind == 'inkstamp':
        return ICON.resize((s, s), Image.LANCZOS)
    im = Image.new('RGBA', (s, s), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    r = s * 0.22
    if kind == 'terminal':
        d.rounded_rectangle((0, 0, s - 1, s - 1), r, fill=(40, 42, 48))
        d.text((s * 0.2, s * 0.52), '>_', font=font('mono', int(s * 0.36), 700), fill=(220, 224, 230), anchor='lm')
    elif kind == 'preview':
        d.rounded_rectangle((0, 0, s - 1, s - 1), r, fill=(250, 250, 252))
        d.rounded_rectangle((s * 0.24, s * 0.16, s * 0.76, s * 0.84), s * 0.06, fill='white', outline=(200, 204, 210), width=2)
        for i in range(4):
            d.line((s * 0.32, s * (0.32 + i * 0.12), s * 0.68, s * (0.32 + i * 0.12)), fill=(170, 176, 186), width=3)
        d.ellipse((s * 0.56, s * 0.58, s * 0.8, s * 0.82), fill=CORAL)
    elif kind == 'player':
        d.rounded_rectangle((0, 0, s - 1, s - 1), r, fill=(88, 86, 214))
        d.polygon([(s * 0.4, s * 0.3), (s * 0.4, s * 0.7), (s * 0.72, s * 0.5)], fill='white')
    elif kind == 'text':
        d.rounded_rectangle((0, 0, s - 1, s - 1), r, fill=(255, 214, 102))
        for i in range(4):
            d.line((s * 0.24, s * (0.3 + i * 0.13), s * (0.76 if i < 3 else 0.56), s * (0.3 + i * 0.13)), fill=(120, 90, 30), width=4)
    elif kind == 'folder':
        d.rounded_rectangle((0, 0, s - 1, s - 1), r, fill=(90, 160, 240))
        d.rounded_rectangle((s * 0.18, s * 0.3, s * 0.82, s * 0.74), s * 0.06, fill=(170, 210, 250))
    return im
DOCK_APPS = ['folder', 'player', 'text', 'preview', 'terminal', 'inkstamp']
DOCK_ICONS = {k: app_icon(k, 76) for k in DOCK_APPS}

def menubar(im, active='inkstamp'):
    bar = Image.new('RGBA', (W, 40), (255, 255, 255, 120)); im.alpha_composite(bar, (0, 0))
    d = ImageDraw.Draw(im)
    im.alpha_composite(ICON.resize((22, 22), Image.LANCZOS), (24, 9))
    x = 60
    for i, item in enumerate([active, 'File', 'Edit', 'View', 'Window', 'Help']):
        f = font('sans', 19, 650 if i == 0 else 450)
        d.text((x, 20), item, font=f, fill=INK, anchor='lm'); x += d.textlength(item, font=f) + 26
    d.text((W - 28, 20), 'Mon Oct 12   2:48 PM', font=font('sans', 19, 500), fill=INK, anchor='rm')

def dock(im, active):
    n, s, gap = len(DOCK_APPS), 76, 14
    w = n * s + (n + 1) * gap; x0, y0 = (W - w) // 2, H - s - 2 * gap - 10
    panel = Image.new('RGBA', (w, s + 2 * gap), (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle((0, 0, w - 1, s + 2 * gap - 1), 26, fill=(255, 255, 255, 110), outline=(255, 255, 255, 170), width=2)
    im.alpha_composite(panel, (x0, y0))
    d = ImageDraw.Draw(im)
    for i, k in enumerate(DOCK_APPS):
        x = x0 + gap + i * (s + gap)
        im.alpha_composite(DOCK_ICONS[k], (x, y0 + gap - (6 if k == active else 0)))
        if k == active:
            d.ellipse((x + s // 2 - 4, y0 + s + gap + 4, x + s // 2 + 4, y0 + s + gap + 12), fill=(60, 60, 66))

# ------------------------------------------------------------------ windows
_shadows = {}
def shadow(w, h):
    if (w, h) not in _shadows:
        m = 60
        sh = Image.new('L', (w + 2 * m, h + 2 * m), 0)
        ImageDraw.Draw(sh).rounded_rectangle((m, m + 18, m + w, m + h + 18), 18, fill=95)
        layer = Image.new('RGBA', sh.size, (0, 0, 0, 0)); layer.putalpha(sh.filter(ImageFilter.GaussianBlur(26)))
        _shadows[w, h] = layer
    return _shadows[w, h]

def window(content, title, dark=False, bg=None):
    """macOS-style window around content -> RGBA (no shadow)"""
    tb = 52
    w, h = content.width, content.height + tb
    win = Image.new('RGBA', (w, h), bg or ((30, 30, 32) if dark else (255, 255, 255)))
    d = ImageDraw.Draw(win)
    d.rectangle((0, 0, w, tb), fill=(44, 44, 48) if dark else (246, 246, 247))
    d.line((0, tb - 1, w, tb - 1), fill=(20, 20, 22) if dark else (226, 226, 229), width=1)
    for i, c in enumerate([(255, 95, 87), (254, 188, 46), (40, 200, 64)]):
        d.ellipse((20 + i * 26, tb / 2 - 7, 34 + i * 26, tb / 2 + 7), fill=c)
    d.text((w / 2, tb / 2), title, font=font('sans', 19, 550), fill=(200, 200, 205) if dark else (90, 92, 98), anchor='mm')
    win.paste(content.convert('RGBA'), (0, tb))
    mask = Image.new('L', (w, h), 0); ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), 18, fill=255)
    out = Image.new('RGBA', (w, h), (0, 0, 0, 0)); out.paste(win, (0, 0), mask)
    return out

def put(im, win, x, y, alpha=1.0, dy=0):
    if alpha <= 0:
        return
    sh = shadow(win.width, win.height)
    for layer, ox, oy in ((sh, -60, -60), (win, 0, 0)):
        if alpha < 1:
            layer = layer.copy(); layer.putalpha(layer.getchannel('A').point(lambda a: int(a * alpha)))
        im.alpha_composite(layer, (int(x + ox), int(y + oy + dy)))

def enter(t, delay=0.0):
    a = ease_out((t - delay) * 4)
    return a, 40 * (1 - a)

# ------------------------------------------------------------------ headline (serif, with italic accent) + step pill
def headline(d, parts, sub, t, y=96):
    """parts: [(text, italic?), ...] in Instrument Serif; the italic part is set in green"""
    a = ease_out(t * 3); x, yy = 84, y - 16 * (1 - a)
    for s, it in parts:
        f = font('serif-it' if it else 'serif', 84)
        col = GREEN if it else INK
        d.text((x, yy), s, font=f, fill=tuple(int(col[k] * a + 240 * (1 - a)) for k in range(3)))
        x += d.textlength(s, font=f)
    if sub:
        d.text((86, yy + 104), sub, font=font('sans', 28, 420), fill=tuple(int(MUTED[k] * a + 240 * (1 - a)) for k in range(3)))

STEPS = ['Record', 'Transcribe', 'Ink', 'Notes', 'Check']
def steps(im, active):
    d = ImageDraw.Draw(im)
    fs = [font('sans', 21, 600 if i + 1 == active else 450) for i in range(len(STEPS))]
    widths = [d.textlength(s, font=f) + 40 for s, f in zip(STEPS, fs)]
    w = sum(widths) + 12; x = W - 84 - w; y = 104
    pill = Image.new('RGBA', (int(w), 52), (0, 0, 0, 0))
    ImageDraw.Draw(pill).rounded_rectangle((0, 0, w - 1, 51), 26, fill=(255, 255, 255, 150), outline=(255, 255, 255, 200), width=2)
    im.alpha_composite(pill, (int(x), y))
    x += 6
    for i, (s, f, sw) in enumerate(zip(STEPS, fs, widths)):
        if i + 1 == active:
            d.rounded_rectangle((x, y + 6, x + sw, y + 46), 20, fill=GREEN)
        d.text((x + sw / 2, y + 26), s, font=f, fill='white' if i + 1 == active else MUTED, anchor='mm')
        x += sw

def desktop(active_app, step=0):
    im = WALL.copy(); menubar(im, {'preview': 'Preview', 'terminal': 'Terminal', 'player': 'Player', 'text': 'Transcript'}.get(active_app, 'inkstamp'))
    dock(im, active_app)
    if step:
        steps(im, step)
    return im

# ------------------------------------------------------------------ assets from the synthetic demo
views = sorted(os.listdir(os.path.join(WORK, 'views_L3-1')))
frame = Image.open(os.path.join(WORK, 'views_L3-1', views[1])).convert('RGB')     # the view with a laser stroke
page = Image.open(os.path.join(WORK, 'render', 'page1.png')).convert('RGB')
ink = Image.open(os.path.join(WORK, 'overlay', 'ink_page1.png')).convert('RGBA')
inked = page.copy(); inked.paste(ink, (0, 0), ink)
doc = pdfium.PdfDocument(os.path.join(DEMO, 'lecture_notes_annotated.pdf'))
annot = doc[0].render(scale=page.height / doc[0].get_height()).to_pil().convert('RGB')
def widen(img):   # the build widened the right margin: pad the plain pages to the annotated width
    out = Image.new('RGB', annot.size, 'white'); out.paste(img, (0, 0)); return out
PAGE_H = 560
clean_w, inked_w, annot_s = fit(widen(page), 2000, PAGE_H), fit(widen(inked), 2000, PAGE_H), fit(annot, 2000, PAGE_H)
page_s, inked_s = fit(page, 2000, PAGE_H), fit(inked, 2000, PAGE_H)

def note_zoom():
    """zoom target: the note column (dark green note text) of the full-resolution annotated page, at the page's aspect"""
    a = np.array(annot).astype(int)
    m = (a[:, :, 0] < 70) & (a[:, :, 1] > 55) & (a[:, :, 1] < 120) & (a[:, :, 2] < 95) & (a[:, :, 1] > a[:, :, 0] + 25)
    ys, xs = np.nonzero(m)
    x0, x1, y0 = np.percentile(xs, 1), np.percentile(xs, 99), np.percentile(ys, 1)
    cw = (x1 - x0) * 1.12; ch = cw * annot.height / annot.width
    zx = max(0, min(annot.width - cw, x0 - (cw - (x1 - x0)) / 2)); zy = max(0, min(annot.height - ch, y0 - 0.03 * annot.height))
    return (zx, zy, zx + cw, zy + ch)
ZOOM = note_zoom()
frame_s = fit(frame, 820, 540)
LASER = ((400, 900), (1500, 820))   # where make_demo.py draws the laser stroke, in frame px

def pad(img, px=24, col='white'):
    out = Image.new('RGB', (img.width + 2 * px, img.height + 2 * px), col); out.paste(img, (px, px)); return out

# ------------------------------------------------------------------ handwriting replay
# The recording before anything is written: the frame's iPad chrome + the clean page warped into frame coordinates
# (inverse of the alignment). The ink layer is warped the same way and then revealed stroke group by stroke group.
AL = json.load(open(os.path.join(WORK, 'align_rescue.json'), encoding='utf-8'))['L3-1'][views[1]]
FW_, FH_ = frame.size
UI = round(0.1547 * FH_)
_M = np.array([[1 / AL['scale'], 0, -AL['tx'] / AL['scale']], [0, 1 / AL['scale'], -AL['ty'] / AL['scale']]])
_rec = np.array(frame).copy()
_rec[UI:] = cv2.warpAffine(np.array(page), _M, (FW_, FH_), borderValue=(232, 232, 232))[UI:]
REC_BASE = Image.fromarray(_rec).convert('RGBA')
REC_INK = cv2.warpAffine(np.array(ink), _M, (FW_, FH_)); REC_INK[:UI] = 0
PAGE_INK = np.array(ink)

def stroke_groups(rgba, k):
    """ink split into groups that were written together: blobs (dilated by k px), then split by colour; reading order"""
    m = rgba[:, :, 3] > 40
    n, lab = cv2.connectedComponents(cv2.dilate(m.astype(np.uint8), np.ones((k, k), np.uint8)))
    hue = ((cv2.cvtColor(np.ascontiguousarray(rgba[:, :, :3]), cv2.COLOR_RGB2HSV)[:, :, 0].astype(int) + 15) % 180) // 30
    out = []
    for i in range(1, n):
        ys, xs = np.nonzero(m & (lab == i))
        if len(xs) < 50:
            continue
        hb = hue[ys, xs]; vals, cnt = np.unique(hb, return_counts=True); major = vals[cnt >= 0.12 * cnt.sum()]
        hb = np.where(np.isin(hb, major), hb, vals[cnt.argmax()])   # stray edge hues join the main colour
        for b in major:
            out.append((ys[hb == b], xs[hb == b]))
    out.sort(key=lambda g: (g[0].min() // 200, g[1].mean()))   # rows, then left to right (mean x: robust to stray pixels)
    return out

def time_map(shape, groups, windows):
    """per pixel: the moment (0..1) it gets written; each group is written left to right inside its window"""
    T = np.full(shape, np.inf, np.float32)
    for (ys, xs), (t0, t1) in zip(groups, windows):
        T[ys, xs] = t0 + (t1 - t0) * (xs - xs.min()) / max(1, xs.max() - xs.min())
    return T

_rg = stroke_groups(REC_INK, 31)   # arrows, circle, 'exam!', underline, 'do it yourself' in the synthetic demo
REC_WIN = [(0.10, 0.17), (0.17, 0.26), (0.50, 0.58), (0.74, 0.80), (0.80, 0.90)] if len(_rg) == 5 else \
          [(0.1 + 0.8 * i / len(_rg), 0.1 + 0.8 * (i + 1) / len(_rg)) for i in range(len(_rg))]
REC_T = time_map(REC_INK.shape[:2], _rg, REC_WIN)
_pg = stroke_groups(PAGE_INK, 25)
PAGE_T = time_map(PAGE_INK.shape[:2], _pg, [(0.12 + 0.72 * i / len(_pg), 0.12 + 0.72 * (i + 1) / len(_pg)) for i in range(len(_pg))])

def written(base, ink_rgba, T, p, size):
    """base with the ink written up to moment p, scaled to size; also the pen tip position (scaled) or None"""
    shown = (ink_rgba[:, :, 3] * (T <= p)).astype(np.uint8)
    im = base.copy(); im.alpha_composite(Image.fromarray(np.dstack([ink_rgba[:, :, :3], shown]), 'RGBA'))
    tip = np.nonzero((T > p - 0.01) & (T <= p))
    sx, sy = size[0] / base.width, size[1] / base.height
    pen = (tip[1].mean() * sx, tip[0].mean() * sy) if len(tip[0]) else None
    return im.resize(size, Image.LANCZOS), pen

def pen_dot(d, pen):
    if pen:
        x, y = pen
        d.ellipse((x - 9, y - 9 + 3, x + 9, y + 9 + 3), fill=(0, 0, 0, 60))
        d.ellipse((x - 7, y - 7, x + 7, y + 7), fill=(30, 32, 36), outline='white', width=2)

# ------------------------------------------------------------------ scenes: draw(t in 0..1) -> RGBA
def s_hook(t):
    im = desktop('inkstamp'); d = ImageDraw.Draw(im)
    a1, a2 = ease_out(t * 3), ease_out(t * 3 - 1.1)
    col = lambda c, a: tuple(int(c[k] * a + 240 * (1 - a)) for k in range(3))
    d.text((W // 2, 400 - 20 * (1 - a1)), 'A 50-minute lecture recording.', font=font('serif', 104), fill=col(INK, a1), anchor='mm')
    f1, f2 = font('serif', 64), font('serif-it', 64)
    l1, l2 = 'Every stroke on the board and every exam hint, ', 'on your own PDF.'
    x = W // 2 - (d.textlength(l1, font=f1) + d.textlength(l2, font=f2)) / 2
    d.text((x, 530 - 20 * (1 - a2)), l1, font=f1, fill=col(INK, a2))
    d.text((x + d.textlength(l1, font=f1), 530 - 20 * (1 - a2)), l2, font=f2, fill=col(GREEN, a2))
    return im

def s_compare(t):
    im = desktop('preview'); d = ImageDraw.Draw(im)
    headline(d, [('Before ', False), ('and after', True)], 'The same page: your clean PDF, then what inkstamp gives back', t)
    s = ease_io((t - 0.2) / 0.6)
    cut = int(clean_w.width * (1 - s))
    both = annot_s.copy(); both.paste(clean_w.crop((0, 0, cut, clean_w.height)), (0, 0))
    content = pad(both, 28, (232, 233, 236))
    win = window(content, 'lecture_notes.pdf')
    x0, y0 = (W - win.width) // 2, 262
    a, dy = enter(t)
    if 0 < s < 1:   # the slider handle, drawn into the window before it is placed
        win = win.copy(); wd = ImageDraw.Draw(win)
        X = 28 + cut; wd.line((X, 52 + 18, X, 52 + 28 + both.height + 10), fill=CORAL, width=5)
        cy = 52 + 28 + both.height // 2; wd.ellipse((X - 20, cy - 20, X + 20, cy + 20), fill=CORAL)
    put(im, win, x0, y0, a, dy)
    return im

TERM_LINES = ['Transcribe the recordings (Whisper, on your computer)', 'Align every view to its PDF page',
              'Lift the ink, drop laser-pointer strokes', 'Write the margin notes, one subagent per lecture',
              'Check every quote and every note position']
TERM_BG = (30, 30, 32)
def s_terminal(t):
    im = desktop('terminal'); d = ImageDraw.Draw(im)
    headline(d, [('One ', False), ('command', True)], 'Run it in the folder with your recordings and the lecture PDF', t)
    tw, th = 1200, 470
    term = Image.new('RGB', (tw, th), TERM_BG); td = ImageDraw.Draw(term)
    mono, monob = font('mono', 28, 400), font('mono', 28, 700)
    typed = '/inkstamp'[:int(clamp(t / 0.22) * 9)]
    td.text((36, 36), '>', font=monob, fill=CORAL)
    td.text((72, 36), typed, font=monob, fill=(236, 236, 240))
    if t < 0.3 and int(t * 20) % 2 == 0:
        cx = 72 + td.textlength(typed, font=monob) + 4; td.rectangle((cx, 40, cx + 15, 72), fill=(236, 236, 240))
    for i, line in enumerate(TERM_LINES):
        a = ease_out((t - 0.3 - i * 0.11) / 0.1)
        if a <= 0:
            continue
        y = 112 + i * 56
        c = lambda col: tuple(int(col[k] * a + TERM_BG[k] * (1 - a)) for k in range(3))
        g = c((92, 200, 120)); td.ellipse((36, y + 4, 62, y + 30), fill=g)
        td.line((43, y + 17, 48, y + 23, 56, y + 11), fill=TERM_BG, width=4)
        td.text((76, y), line, font=mono, fill=c((214, 216, 222)))
    a = ease_out((t - 0.88) / 0.1)
    if a > 0:
        td.text((36, 112 + 5 * 56 + 14), '→ lecture_notes_annotated.pdf', font=monob, fill=tuple(int(c * a + TERM_BG[k] * (1 - a)) for k, c in enumerate((140, 210, 170))))
    win = window(term, 'course — claude — 120×32', dark=True)
    a, dy = enter(t)
    put(im, win, (W - win.width) // 2, 330, a, dy)
    return im

CLOCK = ([0, 0.26, 0.30, 0.44, 0.46, 0.62, 0.68, 0.92, 1.0], [1255, 1280, 1495, 1510, 1872, 1890, 2642, 2660, 2664])   # time-lapse
SUBS = [(0.10, 0.27, 'Check it in polar coordinates too.'), (0.46, 0.63, 'Cut out a small ball first. I will ask exactly this.'),
        (0.70, 0.93, 'Do it yourself, it may be on the exam.')]
EVENTS = [(0.18, '21:10', 'INK', 'sketch beside Example 1', False), (0.36, '25:00', 'LASER', 'pointer stroke, not copied', False),
          (0.50, '31:20', 'SPEECH', '“I will ask exactly this.”', True), (0.57, '31:22', 'INK', '‘exam!’ beside Example 2', False),
          (0.74, '44:10', 'SPEECH', '“Do it yourself, it may be on the exam.”', True), (0.86, '44:12', 'INK', 'underline, ‘do it yourself’', False)]
TAG = {'INK': (52, 99, 196), 'LASER': CORAL, 'SPEECH': (128, 90, 200)}
REC_SIZE = (900, round(900 * FH_ / FW_))
def mmss(s): return f'{int(s) // 60}:{int(s) % 60:02d}'

def laser_layer(size, t):
    """the professor's laser pointer, sweeping across the proof sketch around 25:00, then fading"""
    lay = Image.new('RGBA', size, (0, 0, 0, 0))
    q, fade = ease_io((t - 0.30) / 0.08), 1 - ease_io((t - 0.40) / 0.05)
    if q <= 0 or fade <= 0:
        return lay
    s = size[0] / FW_; (x0, y0), (x1, y1) = LASER
    pts = [(x0 * s + (x1 - x0) * s * u, y0 * s + (y1 - y0) * s * u) for u in np.linspace(0, q, 30)]
    glow = Image.new('RGBA', size, (0, 0, 0, 0)); ImageDraw.Draw(glow).line(pts, fill=(255, 70, 70, int(200 * fade)), width=16, joint='curve')
    lay.alpha_composite(glow.filter(ImageFilter.GaussianBlur(7)))
    ImageDraw.Draw(lay).line(pts, fill=(255, 240, 240, int(255 * fade)), width=3)
    return lay

def s_watch(t):
    im = desktop('player', 1 if t < 0.45 else 2); d = ImageDraw.Draw(im)
    headline(d, [('Watching ', False), ('the lecture', True)], 'Every stroke is followed as it is written, every word is transcribed', t)
    rec, pen = written(REC_BASE, REC_INK, REC_T, t, REC_SIZE)
    rec.alpha_composite(laser_layer(REC_SIZE, t))
    rd = ImageDraw.Draw(rec); pen_dot(rd, pen)
    for a0, a1, line in SUBS:   # captions from the speech recognition
        if a0 <= t <= a1:
            a = min(ease_out((t - a0) * 12), ease_out((a1 - t) * 12))
            f = font('sans', 24, 520); tw = rd.textlength(line, font=f) + 36
            rd.rounded_rectangle(((REC_SIZE[0] - tw) / 2, REC_SIZE[1] - 104, (REC_SIZE[0] + tw) / 2, REC_SIZE[1] - 62), 10, fill=(0, 0, 0, int(170 * a)))
            rd.text((REC_SIZE[0] / 2, REC_SIZE[1] - 83), line, font=f, fill=(255, 255, 255, int(255 * a)), anchor='mm')
    now = np.interp(t, *CLOCK)
    rd.rounded_rectangle((24, REC_SIZE[1] - 30, REC_SIZE[0] - 120, REC_SIZE[1] - 22), 4, fill=(210, 210, 214))
    rd.rounded_rectangle((24, REC_SIZE[1] - 30, 24 + (REC_SIZE[0] - 144) * now / 2892, REC_SIZE[1] - 22), 4, fill=(60, 60, 66))
    rd.text((REC_SIZE[0] - 24, REC_SIZE[1] - 26), mmss(now) + ' / 48:12', font=font('mono', 18, 600), fill=(60, 60, 66), anchor='rm')
    a, dy = enter(t)
    put(im, window(rec, 'Lecture 3-1.mp4'), 84, 268, a, dy)
    panel = Image.new('RGB', (760, 560), 'white'); pd = ImageDraw.Draw(panel)
    pd.text((28, 26), 'Found so far', font=font('sans', 22, 650), fill=MUTED)
    star = ImageFont.truetype(STAR_FONT, 22)
    for i, (at, ts, kind, what, hot) in enumerate(EVENTS):
        e = ease_out((t - at) * 10)
        if e <= 0:
            continue
        y = 76 + i * 78 - 12 * (1 - e)
        c = lambda col: tuple(int(col[k] * e + 255 * (1 - e)) for k in range(3))
        pd.text((28, y + 18), ts, font=font('mono', 22, 700), fill=c(GREEN), anchor='lm')
        f = font('sans', 17, 700); tw = pd.textlength(kind, font=f) + 22
        pd.rounded_rectangle((112, y + 4, 112 + tw, y + 32), 14, fill=c(TAG[kind]))
        pd.text((112 + tw / 2, y + 18), kind, font=f, fill=c((255, 255, 255)), anchor='mm')
        x = 112 + tw + 14
        if hot:
            pd.text((x, y + 19), '★', font=star, fill=c(CORAL), anchor='lm'); x += 28
        pd.text((x, y + 18), what, font=font('sans', 22, 500 if hot else 430), fill=c(INK), anchor='lm')
    a2, dy2 = enter(t, 0.06)
    put(im, window(panel, 'inkstamp — Lecture 3-1'), W - 84 - 760, 300, a2, dy2)
    return im

REC_DONE = written(REC_BASE, REC_INK, REC_T, 1.0, (700, round(700 * FH_ / FW_)))[0]
def s_ink(t):
    im = desktop('preview', 3); d = ImageDraw.Draw(im)
    headline(d, [('The board, ', False), ('on your page', True)], 'Each view is aligned to its PDF page, and the ink is written onto your copy in place', t)
    a, dy = enter(t)
    put(im, window(REC_DONE, 'Lecture 3-1.mp4'), 84, 330, a, dy)
    pg, pen = written(page.convert('RGBA'), PAGE_INK, PAGE_T, t, page_s.size)
    pen_dot(ImageDraw.Draw(pg), pen)
    win = window(pad(pg.convert('RGB'), 20, (232, 233, 236)), 'lecture_notes.pdf')
    a2, dy2 = enter(t, 0.08)
    x2 = W - 84 - win.width
    put(im, win, x2, 290, a2, dy2)
    ax0, ax1, ay = 84 + 700 + 40, x2 - 40, 330 + 52 + REC_DONE.height // 2
    if ax1 - ax0 > 40 and a2 > 0.5:
        d.line((ax0, ay, ax1 - 16, ay), fill=MUTED, width=5)
        d.polygon([(ax1 - 26, ay - 14), (ax1 - 26, ay + 14), (ax1, ay)], fill=MUTED)
    return im

REMARKS = [('12:40', 'This theorem will be on the midterm.', True), ('21:10', 'Check it in polar coordinates too.', False),
           ('31:20', 'I will ask exactly this.', True), ('36:05', 'A correction to the printed proof.', False),
           ('44:10', 'Do it yourself, it may be on the exam.', True)]
def s_notes(t):
    im = desktop('text' if t < 0.45 else 'preview', 2 if t < 0.45 else 4); d = ImageDraw.Draw(im)
    headline(d, [('Every exam hint, ', False), ('with its time', True)], 'Claude reads the whole transcript and writes the remarks into the margin', t)
    tx = Image.new('RGB', (860, 560), 'white'); td = ImageDraw.Draw(tx)
    star = ImageFont.truetype(STAR_FONT, 26)
    for i, (ts, line, hot) in enumerate(REMARKS):
        a = ease_out((t - 0.1 - i * 0.09) / 0.12)
        if a <= 0:
            continue
        y = 40 + i * 100
        c = lambda col: tuple(int(col[k] * a + 255 * (1 - a)) for k in range(3))
        if hot:
            td.rounded_rectangle((20, y - 14, 840, y + 58), 14, fill=c((253, 240, 234)))
        td.text((40, y), ts, font=font('mono', 26, 700), fill=c(GREEN))
        x = 150
        if hot:
            td.text((x, y + 2), '★', font=star, fill=c(CORAL)); x += 36
        td.text((x, y), line, font=font('sans', 27, 450 if not hot else 560), fill=c(INK))
    a, dy = enter(t)
    put(im, window(tx, 'Lecture 3-1 transcript.txt'), 84, 330, a, dy)
    f = ease_io((t - 0.48) / 0.3)   # notes appear, then the view zooms into the note column and holds there
    if f <= 0:
        pg = Image.blend(inked_w.resize(annot_s.size), annot_s, ease_io((t - 0.2) / 0.25))
    else:
        full = (0, 0, annot.width, annot.height)
        pg = annot.crop(tuple(int(full[i] * (1 - f) + ZOOM[i] * f) for i in range(4))).resize(annot_s.size, Image.LANCZOS)
    win = window(pad(pg, 20, (232, 233, 236)), 'lecture_notes.pdf')
    a2, dy2 = enter(t, 0.08)
    put(im, win, W - 84 - win.width, 300, a2, dy2)
    return im

CHECKS = ['Every quote matches the transcript, word for word', 'No note covers the ink or the printed text',
          'Every page is rendered and looked at', 'Anything unclear is marked “needs checking”']
ANNOT_WIN = window(pad(fit(annot, 600, 540), 20, (232, 233, 236)), 'lecture_notes.pdf')
def s_checks(t):
    im = desktop('preview', 5); d = ImageDraw.Draw(im)
    headline(d, [('Checked ', False), ('before you get it', True)], None, t)
    a, dy = enter(t)
    put(im, ANNOT_WIN, W - 84 - ANNOT_WIN.width, 300, a, dy)
    panel = Image.new('RGB', (900, 520), 'white'); pd = ImageDraw.Draw(panel)
    for i, line in enumerate(CHECKS):
        a2 = ease_out((t - 0.12 - i * 0.14) / 0.14)
        if a2 <= 0:
            continue
        y = 50 + i * 115
        g = tuple(int(c * a2 + 255 * (1 - a2)) for c in (40, 170, 90))
        pd.ellipse((40, y, 96, y + 56), fill=g)
        pd.line((54, y + 29, 64, y + 40, 83, y + 17), fill='white', width=6)
        pd.text((124, y + 28), line, font=font('sans', 30, 480), fill=tuple(int(c * a2 + 255 * (1 - a2)) for c in INK), anchor='lm')
    a3, dy3 = enter(t, 0.05)
    put(im, window(panel, 'Checks'), 84, 330, a3, dy3)
    return im

def s_end(t):
    im = desktop('inkstamp'); d = ImageDraw.Draw(im)
    a, b = ease_out(t * 3), ease_out(t * 3 - 0.8)
    ic = ICON.resize((190, 190), Image.LANCZOS)
    if a < 1:
        ic = ic.copy(); ic.putalpha(ic.getchannel('A').point(lambda v: int(v * a)))
    im.alpha_composite(ic, (W // 2 - 95, int(220 + 20 * (1 - a))))
    col = lambda c, x: tuple(int(c[k] * x + 240 * (1 - x)) for k in range(3))
    d.text((W // 2, 520 - 16 * (1 - a)), 'inkstamp', font=font('serif', 150), fill=col(INK, a), anchor='mm')
    d.text((W // 2, 632 - 16 * (1 - b)), 'One annotated PDF for the whole course, plus a transcript of every lecture', font=font('sans', 30, 420), fill=col(MUTED, b), anchor='mm')
    if b > 0:
        f = font('mono', 30, 700); w_ = d.textlength('/inkstamp', font=f) + 64
        d.rounded_rectangle((W // 2 - w_ / 2, 690, W // 2 + w_ / 2, 748), 29, fill=col(GREEN, b))
        d.text((W // 2, 719), '/inkstamp', font=f, fill='white', anchor='mm')
        d.text((W // 2, 848), 'Synthetic demo: the page, the handwriting and the remarks are made up.', font=font('sans', 20, 420), fill=col(MUTED, b), anchor='mm')
    return im

SCENES = [(3.2, s_hook), (5.2, s_compare), (4.6, s_terminal), (9.0, s_watch), (5.4, s_ink), (6.0, s_notes), (4.0, s_checks), (3.6, s_end)]
FADE = 0.45   # seconds of crossfade between scenes

def frames(fps):
    prev = None
    for sec, draw in SCENES:
        n = int(sec * fps)
        for i in range(n):
            im = draw(i / max(1, n - 1)).convert('RGB')
            if prev is not None and i < FADE * fps:
                im = Image.blend(prev, im, ease_io(i / (FADE * fps)))
            yield im
        prev = draw(1.0).convert('RGB')

def main():
    os.makedirs(OUT, exist_ok=True)
    if '--preview' in sys.argv:   # one still per scene (at 75%), on a contact sheet
        stills = [draw(0.75).convert('RGB').resize((W // 3, H // 3), Image.LANCZOS) for _, draw in SCENES]
        sheet = Image.new('RGB', (W // 3 * 2, (len(stills) + 1) // 2 * H // 3), 'white')
        for i, s in enumerate(stills):
            sheet.paste(s, (i % 2 * W // 3, i // 2 * H // 3))
        sheet.save(os.path.join(OUT, 'preview.png')); print(os.path.join(OUT, 'preview.png')); return
    mp4 = os.path.join(OUT, 'demo.mp4')
    with av.open(mp4, 'w') as c:
        st = c.add_stream('libx264', rate=FPS); st.width, st.height, st.pix_fmt = W, H, 'yuv420p'
        st.options = {'crf': '20', 'preset': 'slow', 'movflags': '+faststart'}
        for im in frames(FPS):
            for p in st.encode(av.VideoFrame.from_image(im)):
                c.mux(p)
        for p in st.encode():
            c.mux(p)
    poster = os.path.join(OUT, 'poster.png')   # README still (links to the video) and GitHub social preview
    s_watch(0.58).convert('RGB').save(poster, optimize=True)
    print(f'{mp4} {os.path.getsize(mp4) / 1e6:.1f} MB, {sum(s for s, _ in SCENES):.1f} s; {poster}')
    if '--gif' in sys.argv:   # optional animated GIF (much larger and blurrier than the MP4)
        gif_frames = [im.resize((800, 450), Image.LANCZOS).quantize(colors=128, method=Image.Quantize.MEDIANCUT) for im in frames(10)]
        gif = os.path.join(OUT, 'demo.gif')
        gif_frames[0].save(gif, save_all=True, append_images=gif_frames[1:], duration=100, loop=0, optimize=True)
        print(f'{gif} {os.path.getsize(gif) / 1e6:.1f} MB')

if __name__ == '__main__':
    main()
