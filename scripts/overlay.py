#!/usr/bin/env python3
"""Build per-page RGBA ink overlays (overlay/ink_page{p}.png) from all aligned views of the job videos,
chronologically with replace semantics (each view overwrites the area it shows -> erased ink disappears).
Pages < min_page are not touched; pages >= min_page start from their existing ink png (job "overlay_base": "empty" to start blank). GoodNotes laser-pointer strokes are dropped.
usage: python overlay.py"""
import cv2, numpy as np, json, os, glob
import paths
import sys
from paths import W, RENDER, OVERLAY
MIN_PAGE = paths.MIN_PAGE
UI_TOP = 258
CLEAR_TOP = 262
FRAME_W, FRAME_H = 2388, 1668
import pypdfium2 as _pdfium
NPAGES = len(_pdfium.PdfDocument(paths.PDF))
ORDER = paths.ORDER

def load_alignments():
    out = json.load(open(paths.ALIGN))
    f = paths.RESCUE
    if os.path.exists(f):
        out.update(json.load(open(f)))
    return out

def frame_dir(vid):
    return os.path.join(W, f'views_{vid}')

def frame_time(name):
    return int(name.split('_')[2][:5])

_pages = {}
def page_img(p):
    if p not in _pages:
        _pages[p] = cv2.imread(os.path.join(RENDER, f'page{p}.png'))
    return _pages[p]

LASER = []
def extract_ink(frame, p, s, tx, ty):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    S = hsv[:, :, 1].astype(np.float32); V = hsv[:, :, 2].astype(np.float32)
    alpha = np.clip((S - 45.0) / 50.0, 0, 1) * (V > 70)
    alpha[:UI_TOP, :] = 0
    Minv = np.array([[1 / s, 0, -tx / s], [0, 1 / s, -ty / s]], dtype=np.float64)
    warped_page = cv2.warpAffine(page_img(p), Minv, (FRAME_W, FRAME_H), flags=cv2.INTER_LINEAR, borderValue=(255, 255, 255))
    ps = cv2.cvtColor(warped_page, cv2.COLOR_BGR2HSV)[:, :, 1]
    pdf_colored = cv2.dilate((ps > 60).astype(np.uint8), np.ones((7, 7), np.uint8))
    alpha[pdf_colored > 0] = 0
    mask = (alpha > 0.15).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    keep = np.zeros(n, bool)
    keep[stats[:, cv2.CC_STAT_AREA] >= 12] = True
    keep[0] = False
    # GoodNotes laser pointer: transient strokes with a wide soft glow (S 12~60, V>235) all around -> not ink
    halo = ((S >= 12) & (S <= 60) & (V > 235)).astype(np.uint8)
    for i in np.nonzero(keep)[0]:
        x, y, w, h, area = stats[i]
        x0, y0, x1, y1 = max(0, x - 14), max(0, y - 14), min(mask.shape[1], x + w + 14), min(mask.shape[0], y + h + 14)
        comp = (lab[y0:y1, x0:x1] == i).astype(np.uint8)
        ring = (cv2.dilate(comp, np.ones((25, 25), np.uint8)) > 0) & ~(cv2.dilate(mask[y0:y1, x0:x1], np.ones((7, 7), np.uint8)) > 0)
        n = int(ring.sum())
        if n > 50 and halo[y0:y1, x0:x1][ring].mean() > 0.5:
            keep[i] = False
            LASER.append(int(area))
    alpha = alpha * keep[lab]
    return np.dstack([frame, (alpha * 255).astype(np.uint8)])

def main():
    aligns = load_alignments()
    canvases = {}
    H, W = page_img(1).shape[:2]
    stats = []
    for vid in ORDER:
        if vid not in aligns:
            continue
        d = aligns[vid]
        names = sorted([k for k, v in d.items() if v.get('ok')], key=frame_time)
        for name in names:
            a = d[name]
            p = a['page']
            if p < MIN_PAGE or p > NPAGES:
                continue
            s, tx, ty = a['scale'], a['tx'], a['ty']
            frame = cv2.imread(os.path.join(frame_dir(vid), name.split('#')[0]))
            if frame is None:
                continue
            global FRAME_W, FRAME_H, UI_TOP, CLEAR_TOP
            FRAME_H, FRAME_W = frame.shape[:2]; UI_TOP = int(round(paths.UI_TOP_FRAC * FRAME_H)); CLEAR_TOP = UI_TOP + 4
            rgba = extract_ink(frame, p, s, tx, ty)
            M = np.array([[s, 0, tx], [0, s, ty]], dtype=np.float64)
            warped = cv2.warpAffine(rgba, M, (W, H), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
            x0 = int(max(0, np.floor(tx))); x1 = int(min(W, np.ceil(s * FRAME_W + tx)))
            y0 = int(max(0, np.floor(s * CLEAR_TOP + ty))); y1 = int(min(H, np.ceil(s * FRAME_H + ty)))
            if p not in canvases:   # continue from the ink already on this page (earlier runs / earlier lectures)
                prev = cv2.imread(os.path.join(OVERLAY, f'ink_page{p}.png'), cv2.IMREAD_UNCHANGED) if paths.J.get('overlay_base', 'existing') == 'existing' else None
                canvases[p] = prev if prev is not None and prev.shape == (H, W, 4) else np.zeros((H, W, 4), dtype=np.uint8)
            canv = canvases[p]
            ink_px = 0
            if x1 > x0 and y1 > y0:
                canv[y0:y1, x0:x1, :] = 0
                region = warped[y0:y1, x0:x1]
                m = region[:, :, 3] > 0
                canv[y0:y1, x0:x1][m] = region[m]
                ink_px = int((region[:, :, 3] > 60).sum())
            stats.append((vid, name, p, ink_px))
            print(f"{vid} {name} page {p} region x[{x0},{x1}] y[{y0},{y1}] ink={ink_px}", flush=True)
    os.makedirs(OVERLAY, exist_ok=True)
    touched = []
    for p, canv in sorted(canvases.items()):
        n_ink = int((canv[:, :, 3] > 60).sum())
        cv2.imwrite(os.path.join(OVERLAY, f'ink_page{p}.png'), canv)
        base = page_img(p).astype(np.float32)
        a = canv[:, :, 3:4].astype(np.float32) / 255.0
        comp = (base * (1 - a) + canv[:, :, :3].astype(np.float32) * a).astype(np.uint8)
        small = cv2.resize(comp, (W // 2, H // 2), interpolation=cv2.INTER_AREA)
        cv2.imwrite(os.path.join(OVERLAY, f'debug_page{p}.jpg'), small, [cv2.IMWRITE_JPEG_QUALITY, 85])
        touched.append((p, n_ink))
    json.dump(dict(touched=touched, stats=stats), open(os.path.join(OVERLAY, 'summary.json'), 'w'), indent=1)
    print('pages touched:', touched)
    print('laser components removed:', len(LASER), 'px', sum(LASER))

if __name__ == '__main__':
    main()
