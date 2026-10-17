"""Draw the inkstamp icon: a fountain-pen nib writing a line of ink, with a play button on top.
Writes docs/icon.svg (vector, for the README) and docs/icon.png (1024 px) from the same geometry.
usage (with the skill's python):  python examples/make_icon.py [--out docs]"""
import os, sys
import numpy as np
from PIL import Image, ImageDraw

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.abspath(sys.argv[sys.argv.index('--out') + 1]) if '--out' in sys.argv else os.path.join(SKILL, 'docs')
TOP, BOTTOM, NIB, CORAL = '#1A6B47', '#0C3B27', '#FFF6E9', '#E07A5F'
# geometry in a 512 x 512 box
RADIUS = 114
INK = ((118, 436), (168, 452), (214, 446), (256, 404))           # cubic Bezier: the line the pen is writing
INK_W = 22
PLATE = (190, 84, 322, 178, 28)                                    # the play button on top: x0, y0, x1, y1, corner radius
NIB_PTS = [(256, 400), (182, 262), (180, 236), (208, 194), (304, 194), (332, 236), (330, 262)]
PLAY = [(240, 108), (240, 154), (280, 131)]
VENT = (256, 262, 13)                                              # the nib's breather hole: x, y, r
SLIT = ((256, 276), (256, 392), 8)

def svg():
    pts = ' '.join(f'L{x} {y}' for x, y in NIB_PTS[1:])
    (a, b, c, d), (x0, y0, x1, y1, r) = INK, PLATE
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{TOP}"/><stop offset="1" stop-color="{BOTTOM}"/></linearGradient></defs>
  <rect width="512" height="512" rx="{RADIUS}" fill="url(#bg)"/>
  <path d="M{a[0]} {a[1]} C{b[0]} {b[1]} {c[0]} {c[1]} {d[0]} {d[1]}" fill="none" stroke="{CORAL}" stroke-width="{INK_W}" stroke-linecap="round"/>
  <rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" rx="{r}" fill="{CORAL}"/>
  <path d="M{NIB_PTS[0][0]} {NIB_PTS[0][1]} {pts} Z" fill="{NIB}"/>
  <circle cx="{VENT[0]}" cy="{VENT[1]}" r="{VENT[2]}" fill="{BOTTOM}"/>
  <line x1="{SLIT[0][0]}" y1="{SLIT[0][1]}" x2="{SLIT[1][0]}" y2="{SLIT[1][1]}" stroke="{BOTTOM}" stroke-width="{SLIT[2]}" stroke-linecap="round"/>
  <path d="M{PLAY[0][0]} {PLAY[0][1]} L{PLAY[1][0]} {PLAY[1][1]} L{PLAY[2][0]} {PLAY[2][1]} Z" fill="{NIB}"/>
</svg>
'''

def png(size):
    k = size * 4 / 512                                   # draw 4x larger, then downscale for smooth edges
    S = int(512 * k)
    hex2 = lambda h: tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
    y = np.linspace(0, 1, S)[:, None, None]
    grad = (np.array(hex2(TOP)) * (1 - y) + np.array(hex2(BOTTOM)) * y) * np.ones((1, S, 1))
    im = Image.fromarray(grad.astype(np.uint8)).convert('RGBA')
    mask = Image.new('L', (S, S), 0); ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), RADIUS * k, fill=255)
    im.putalpha(mask)
    d = ImageDraw.Draw(im)
    p = lambda pt: (pt[0] * k, pt[1] * k)
    (a, b, c, e) = [np.array(q, float) for q in INK]
    ts = np.linspace(0, 1, 600)[:, None]
    curve = ((1 - ts) ** 3 * a + 3 * (1 - ts) ** 2 * ts * b + 3 * (1 - ts) * ts ** 2 * c + ts ** 3 * e) * k
    r = INK_W * k / 2
    for q in curve:   # a dense row of discs = a smooth round-capped stroke
        d.ellipse((q[0] - r, q[1] - r, q[0] + r, q[1] + r), fill=CORAL)
    x0, y0, x1, y1, r = PLATE
    d.rounded_rectangle((x0 * k, y0 * k, x1 * k, y1 * k), r * k, fill=CORAL)
    d.polygon([p(q) for q in PLAY], fill=NIB)
    d.polygon([p(q) for q in NIB_PTS], fill=NIB)
    vx, vy, vr = VENT
    d.ellipse(((vx - vr) * k, (vy - vr) * k, (vx + vr) * k, (vy + vr) * k), fill=BOTTOM)
    (s0, s1, sw) = SLIT
    d.line([p(s0), p(s1)], fill=BOTTOM, width=int(sw * k))
    for q in (s0, s1):
        r = sw * k / 2; d.ellipse((q[0] * k - r, q[1] * k - r, q[0] * k + r, q[1] * k + r), fill=BOTTOM)
    return im.resize((size, size), Image.LANCZOS)

def main():
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, 'icon.svg'), 'w', encoding='utf-8').write(svg())
    png(1024).save(os.path.join(OUT, 'icon.png'), optimize=True)
    print(os.path.join(OUT, 'icon.svg'), os.path.join(OUT, 'icon.png'))

if __name__ == '__main__':
    main()
