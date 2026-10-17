"""Render the README demo video from the synthetic demo of examples/make_demo.py: docs/demo.mp4 (H.264) and docs/demo.gif.
Everything shown is made up (page, handwriting, remarks); no real course material is involved.
usage (with the skill's python):  python examples/make_demo.py <demo_dir>
                                  python examples/make_video.py <demo_dir> [--out docs]"""
import os, sys
import numpy as np, av, pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
args = [a for a in sys.argv[1:] if not a.startswith('--')]
DEMO = os.path.abspath(args[0])
OUT = os.path.abspath(sys.argv[sys.argv.index('--out') + 1]) if '--out' in sys.argv else os.path.join(SKILL, 'docs')
WORK = os.path.join(DEMO, '_work')
W, H, FPS = 1280, 720, 30
BG, TEXT, MUTED, ACCENT, STAR = (250, 250, 246), (34, 34, 34), (118, 118, 118), (15, 81, 50), (192, 57, 43)
FONT = os.path.join(SKILL, 'fonts', 'NotoSansKR[wght].ttf')

def font(size, weight='Regular'):
    f = ImageFont.truetype(FONT, size)
    try:
        f.set_variation_by_name(weight)
    except Exception:
        pass
    return f

def fit(img, w, h):
    s = min(w / img.width, h / img.height)
    return img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS)

def ease(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)

# ------------------------------------------------------------------ assets from the synthetic demo
frame = Image.open(os.path.join(WORK, 'views_L3-1', sorted(os.listdir(os.path.join(WORK, 'views_L3-1')))[1])).convert('RGB')   # the view with a laser stroke
page = Image.open(os.path.join(WORK, 'render', 'page1.png')).convert('RGB')
ink = Image.open(os.path.join(WORK, 'overlay', 'ink_page1.png')).convert('RGBA')
inked = page.copy(); inked.paste(ink, (0, 0), ink)
doc = pdfium.PdfDocument(os.path.join(DEMO, 'lecture_notes_annotated.pdf'))
annotated = doc[0].render(scale=page.height / doc[0].get_height()).to_pil().convert('RGB')
PAGE_H = 560
page_s, inked_s, annot_s = fit(page, 2000, PAGE_H), fit(inked, 2000, PAGE_H), fit(annotated, 2000, PAGE_H)
inked_wide = Image.new('RGB', annot_s.size, 'white'); inked_wide.paste(inked_s, (0, 0))   # the build widened the right margin
frame_big, frame_small = fit(frame, 1180, 540), fit(frame, 600, 420)
TRANSCRIPT = [('12:40', 'This theorem will be on the midterm. Know both sides by heart.'),
              ('21:10', 'Check it in polar coordinates too.'),
              ('31:20', 'Cut out a small ball first. I will ask exactly this.'),
              ('36:05', 'Correction: the derivative of F one, not F.'),
              ('44:10', 'Do it yourself, it may be on the exam.')]
CHECKS = ['Every quote matches the transcript word for word', 'No note covers the ink or the printed text',
          'Every page is rendered and looked at']

def canvas(step=None, title=None):
    im = Image.new('RGB', (W, H), BG); d = ImageDraw.Draw(im)
    if step:
        d.text((48, 30), step, font=font(22, 'Bold'), fill=ACCENT)
        d.text((48 + d.textlength(step, font=font(22, 'Bold')) + 14, 30), title, font=font(22), fill=TEXT)
    return im, d

def caption(d, text):
    d.text((W // 2, H - 34), text, font=font(18), fill=MUTED, anchor='ms')

def blend(a, b, t):
    return Image.blend(a, b, ease(t))

# ------------------------------------------------------------------ scenes: (seconds, draw(t in 0..1) -> image)
def s_title(t):
    im, d = canvas(); a = ease(t * 2.5)
    col = lambda c: tuple(int(BG[i] + (c[i] - BG[i]) * a) for i in range(3))
    d.text((W // 2, 300), 'inkstamp', font=font(64, 'Bold'), fill=col(TEXT), anchor='ms')
    d.text((W // 2, 360), 'Lecture recordings + the lecture-note PDF  →  one annotated PDF', font=font(26), fill=col(TEXT), anchor='ms')
    d.text((W // 2, 410), 'A Claude Code skill  ·  synthetic demo, made-up page and remarks', font=font(18), fill=col(MUTED), anchor='ms')
    return im

def s_recording(t):
    im, d = canvas('1', 'The recording')
    im.paste(frame_big, ((W - frame_big.width) // 2, 80))
    caption(d, 'The professor writes on the lecture-note PDF on an iPad. The glowing red line is only a laser pointer.')
    return im

def s_transcript(t):
    im, d = canvas('2', 'Speech → timestamped transcript (Whisper, on your computer)')
    im.paste(frame_small, (48, 110))
    x0, y = 690, 140
    shown = t * (len(TRANSCRIPT) + 0.6)
    for i, (ts, line) in enumerate(TRANSCRIPT):
        a = ease(shown - i)
        if a <= 0:
            break
        c = lambda col: tuple(int(BG[k] + (col[k] - BG[k]) * a) for k in range(3))
        d.text((x0, y), ts, font=font(20, 'Bold'), fill=c(ACCENT))
        words, cur, yy = line.split(), '', y
        for w_ in words:   # wrap to the right column
            if d.textlength(cur + ' ' + w_, font=font(20)) > W - x0 - 130:
                d.text((x0 + 80, yy), cur.strip(), font=font(20), fill=c(TEXT)); yy += 30; cur = ''
            cur += ' ' + w_
        d.text((x0 + 80, yy), cur.strip(), font=font(20), fill=c(TEXT))
        y = yy + 52
    caption(d, 'Every word is kept with its time, so each remark in the notes can be checked and replayed.')
    return im

def s_ink(t):
    im, d = canvas('3', 'Align each view to its page, lift the ink')
    im.paste(frame_small, (48, 130))
    pg = blend(page_s, inked_s, (t - 0.25) / 0.5)
    im.paste(pg, (W - 48 - pg.width, 80))
    ax, ay = 48 + frame_small.width + 20, 130 + frame_small.height // 2
    d.line((ax, ay, W - 48 - pg.width - 20, ay), fill=MUTED, width=4)
    d.polygon([(W - 48 - pg.width - 20, ay - 10), (W - 48 - pg.width - 20, ay + 10), (W - 48 - pg.width - 4, ay)], fill=MUTED)
    caption(d, 'Handwriting lands where it was written on your own copy. Erased strokes and the laser stroke are left out.')
    return im

def s_notes(t):
    im, d = canvas('4', 'Claude writes the margin notes')
    pg = blend(inked_wide, annot_s, t / 0.45) if t < 0.5 else annot_s
    if t >= 0.5:   # slow zoom into the note column
        z = 1 + 0.4 * ease((t - 0.5) / 0.5)
        big = annot_s.resize((int(annot_s.width * z), int(annot_s.height * z)), Image.LANCZOS)
        cx = int((big.width - annot_s.width) * 0.8); cy = int((big.height - annot_s.height) * 0.25)
        pg = big.crop((cx, cy, cx + annot_s.width, cy + annot_s.height))
    im.paste(pg, ((W - pg.width) // 2, 80))
    caption(d, 'Every exam-relevant remark goes in the margin with its time; ★ marks exam and memorize remarks.')
    return im

def s_checks(t):
    im, d = canvas('5', 'Checks before you get the PDF')
    small = fit(annotated, 520, PAGE_H)
    im.paste(small, (60, 80))
    for i, text in enumerate(CHECKS):
        a = ease(t * (len(CHECKS) + 0.5) - i)
        if a <= 0:
            continue
        c = lambda col: tuple(int(BG[k] + (col[k] - BG[k]) * a) for k in range(3))
        y = 200 + i * 90
        d.ellipse((640, y - 2, 676, y + 34), outline=c(ACCENT), width=3)
        d.line((648, y + 16, 656, y + 25, 669, y + 8), fill=c(ACCENT), width=4)
        d.text((696, y + 4), text, font=font(22), fill=c(TEXT))
    caption(d, 'Anything unclear is marked "※ 확인 필요" (needs checking) instead of guessed.')
    return im

def s_end(t):
    im, d = canvas(); a = ease(t * 2)
    col = lambda c: tuple(int(BG[i] + (c[i] - BG[i]) * a) for i in range(3))
    d.text((W // 2, 300), 'One annotated PDF for the whole course', font=font(44, 'Bold'), fill=col(TEXT), anchor='ms')
    d.text((W // 2, 356), 'plus a timestamped transcript of every lecture', font=font(24), fill=col(TEXT), anchor='ms')
    d.text((W // 2, 420), '/inkstamp', font=font(22, 'Bold'), fill=col(ACCENT), anchor='ms')
    return im

SCENES = [(2.5, s_title), (3.5, s_recording), (4.5, s_transcript), (4.5, s_ink), (5.0, s_notes), (3.5, s_checks), (2.5, s_end)]
FADE = 0.4   # seconds of crossfade between scenes

def frames(fps):
    prev = None
    for sec, draw in SCENES:
        n = int(sec * fps)
        for i in range(n):
            im = draw(i / max(1, n - 1))
            if prev is not None and i < FADE * fps:
                im = Image.blend(prev, im, ease(i / (FADE * fps)))
            yield im
        prev = draw(1.0)

def main():
    os.makedirs(OUT, exist_ok=True)
    if '--preview' in sys.argv:   # one still per scene (at 70%), side by side, instead of encoding
        stills = [draw(0.7).resize((W // 2, H // 2), Image.LANCZOS) for _, draw in SCENES]
        sheet = Image.new('RGB', (W, (len(stills) + 1) // 2 * H // 2), 'white')
        for i, s in enumerate(stills):
            sheet.paste(s, (i % 2 * W // 2, i // 2 * H // 2))
        sheet.save(os.path.join(OUT, 'preview.png')); print(os.path.join(OUT, 'preview.png')); return
    mp4 = os.path.join(OUT, 'demo.mp4')
    with av.open(mp4, 'w') as c:
        st = c.add_stream('libx264', rate=FPS); st.width, st.height, st.pix_fmt = W, H, 'yuv420p'
        st.options = {'crf': '22', 'preset': 'slow', 'movflags': '+faststart'}
        for im in frames(FPS):
            for p in st.encode(av.VideoFrame.from_image(im)):
                c.mux(p)
        for p in st.encode():
            c.mux(p)
    gif_frames = [im.resize((W // 2, H // 2), Image.LANCZOS).quantize(colors=128, method=Image.Quantize.MEDIANCUT) for im in frames(10)]
    gif = os.path.join(OUT, 'demo.gif')
    gif_frames[0].save(gif, save_all=True, append_images=gif_frames[1:], duration=100, loop=0, optimize=True)
    print(f'{mp4} {os.path.getsize(mp4) / 1e6:.1f} MB, {gif} {os.path.getsize(gif) / 1e6:.1f} MB, {sum(s for s, _ in SCENES):.1f} s')

if __name__ == '__main__':
    main()
