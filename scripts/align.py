#!/usr/bin/env python3
"""Main alignment pass: each view frame -> (page, scale, tx, ty) on the 200-dpi page render.
Sequential page window + SIFT/RANSAC (scale+translation), template-matching fallback, verification score.
usage: python align.py [KEY ...]   (default: all videos in the job). Resumable. Follow with rescue_align.py."""
import cv2, numpy as np, glob, os, json, sys, time
import subprocess

import paths
from paths import W as MULTI, PDF, RENDER
TIME_BUDGET = 1e9
T_START = time.time()
DPI = 200
import pypdfium2 as _pdfium
NPAGES = len(_pdfium.PdfDocument(PDF))
UI_TOP = 258      # rescaled per frame height below if frames are not 1668 px tall
CLEAR_TOP = 310
VIDEOS = [a for a in sys.argv[1:] if not a.startswith('--')] or paths.ORDER
OUT = paths.ALIGN


def render_all():
    import render
    render.main()

def clean_gray(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).copy()
    g[hsv[:, :, 1] > 60] = 255
    return g

sift = cv2.SIFT_create(nfeatures=6000)
_page_cache = {}
def page_data(p):
    if p not in _page_cache:
        g = cv2.imread(f'{RENDER}/page{p}.png', cv2.IMREAD_GRAYSCALE)
        kp, des = sift.detectAndCompute(g, None)
        _page_cache[p] = (g, kp, des)
    return _page_cache[p]

def ransac_scale_trans(src, dst, iters=4000, thr=4.0, smin=0.3, smax=2.0, seed=0):
    rng = np.random.default_rng(seed)
    n = len(src)
    best_inl = None; best_cnt = 0
    for _ in range(iters):
        i, j = rng.choice(n, 2, replace=False)
        dq = src[j] - src[i]; dp = dst[j] - dst[i]
        nq = np.hypot(*dq)
        if nq < 20:
            continue
        s = np.hypot(*dp) / nq
        if s < smin or s > smax:
            continue
        if np.dot(dq, dp) < 0.95 * nq * np.hypot(*dp):
            continue
        t = dst[i] - s * src[i]
        err = np.hypot(*((s * src + t) - dst).T)
        inl = err < thr
        cnt = int(inl.sum())
        if cnt > best_cnt:
            best_cnt = cnt; best_inl = inl
    if best_inl is None or best_cnt < 12:
        return None, 0
    q = src[best_inl]; p = dst[best_inl]
    qm = q.mean(axis=0); pm = p.mean(axis=0)
    s = float(((q - qm) * (p - pm)).sum() / ((q - qm) ** 2).sum())
    t = pm - s * qm
    return (s, float(t[0]), float(t[1])), best_cnt

def match_frame(kp, des, p):
    g, pkp, pdes = page_data(p)
    if des is None or pdes is None or len(kp) < 30:
        return None
    bf = cv2.BFMatcher(cv2.NORM_L2)
    knn = bf.knnMatch(des, pdes, k=2)
    good = [m for m, n in (mn for mn in knn if len(mn) == 2) if m.distance < 0.75 * n.distance]
    if len(good) < 25:
        return None
    src = np.float64([kp[m.queryIdx].pt for m in good])
    dst = np.float64([pkp[m.trainIdx].pt for m in good])
    M, cnt = ransac_scale_trans(src, dst)
    if M is None:
        return None
    return dict(page=p, scale=M[0], tx=M[1], ty=M[2], inliers=cnt, n_good=len(good))

def score(fg, p, s, tx, ty):
    g = page_data(p)[0]
    Minv = np.array([[1 / s, 0, -tx / s], [0, 1 / s, -ty / s]], dtype=np.float64)
    warped = cv2.warpAffine(g, Minv, (fg.shape[1], fg.shape[0]), flags=cv2.INTER_AREA, borderValue=255)
    a = fg[CLEAR_TOP:, :].astype(np.float32); b = warped[CLEAR_TOP:, :].astype(np.float32)
    # ignore region where warped page is pure border (outside page) -> treat as white anyway
    a -= a.mean(); b -= b.mean()
    den = np.sqrt((a * a).sum() * (b * b).sum()) + 1e-9
    return float((a * b).sum() / den)

PAD = 1600
def tm_search(fg, p, s, down=4):
    g = page_data(p)[0]
    h, w = g.shape
    big = cv2.resize(g, (int(round(w / s)), int(round(h / s))), interpolation=cv2.INTER_AREA)
    big = cv2.copyMakeBorder(big, PAD, PAD, PAD, PAD, cv2.BORDER_CONSTANT, value=255)
    tpl = fg[CLEAR_TOP:, :]
    tpl_s = cv2.resize(tpl, (tpl.shape[1] // down, tpl.shape[0] // down), interpolation=cv2.INTER_AREA)
    big_s = cv2.resize(big, (big.shape[1] // down, big.shape[0] // down), interpolation=cv2.INTER_AREA)
    if big_s.shape[0] < tpl_s.shape[0] or big_s.shape[1] < tpl_s.shape[1]:
        return None
    r = cv2.matchTemplate(big_s, tpl_s, cv2.TM_CCOEFF_NORMED)
    # require overlap with the real page: mask positions whose template center lies outside page area
    _, mx, _, loc = cv2.minMaxLoc(r)
    x0, y0 = loc[0] * down, loc[1] * down
    win = 2 * down + 2
    ys, xs = max(0, y0 - win), max(0, x0 - win)
    sub = big[ys: y0 + tpl.shape[0] + win, xs: x0 + tpl.shape[1] + win]
    if sub.shape[0] < tpl.shape[0] or sub.shape[1] < tpl.shape[1]:
        return None
    r2 = cv2.matchTemplate(sub, tpl, cv2.TM_CCOEFF_NORMED)
    _, mx2, _, loc2 = cv2.minMaxLoc(r2)
    x1, y1 = xs + loc2[0], ys + loc2[1]
    tx = s * (x1 - PAD); ty = s * (y1 - PAD - CLEAR_TOP)
    return dict(page=p, scale=s, tx=tx, ty=ty, tm=float(mx2))

def frame_time(name):
    return int(name.split('_')[2][:5])

def main():
    render_all()
    results = json.load(open(OUT)) if os.path.exists(OUT) else {}
    for vid in VIDEOS:
        res = results.setdefault(vid, {})
        files = sorted(glob.glob(f'{MULTI}/views_{vid}/*.jpg'), key=lambda f: frame_time(os.path.basename(f)))
        last_page = None
        scales = []
        for f in files:
            name = os.path.basename(f)
            if name in res:
                if res[name].get('ok'):
                    last_page = res[name]['page']; scales.append(res[name]['scale'])
                continue
            if time.time() - T_START > TIME_BUDGET:
                print('time budget reached; resume later', flush=True)
                return
            t0 = time.time()
            frame = cv2.imread(f)
            global UI_TOP, CLEAR_TOP
            UI_TOP = int(round(paths.UI_TOP_FRAC * frame.shape[0])); CLEAR_TOP = UI_TOP + 52
            fg = clean_gray(frame); fg[:UI_TOP] = 255
            kp, des = sift.detectAndCompute(fg, None)
            cands = list(range(max(1, last_page - 1), min(NPAGES, last_page + 3) + 1)) if last_page else list(range(1, NPAGES + 1))
            best = None
            for p in cands:
                r = match_frame(kp, des, p)
                if r and (best is None or r['inliers'] > best['inliers']):
                    best = r
            if (best is None or best['inliers'] < 40) and last_page is not None:
                # widen to all pages
                for p in range(1, NPAGES + 1):
                    if p in cands:
                        continue
                    r = match_frame(kp, des, p)
                    if r and (best is None or r['inliers'] > best['inliers']):
                        best = r
            entry = None
            if best is not None:
                sc = score(fg, best['page'], best['scale'], best['tx'], best['ty'])
                if sc >= 0.72 and best['inliers'] >= 25:
                    entry = dict(best, score=sc, method='sift', ok=True)
            if entry is None:
                # TM fallback with known scales on window pages
                cand_scales = sorted(set(round(s, 3) for s in scales[-5:])) or [0.7544, 0.906]
                tbest = None
                for p in cands:
                    for s in cand_scales:
                        r = tm_search(fg, p, s)
                        if r and (tbest is None or r['tm'] > tbest['tm']):
                            tbest = r
                if tbest is not None:
                    sc = score(fg, tbest['page'], tbest['scale'], tbest['tx'], tbest['ty'])
                    if sc >= 0.72:
                        entry = dict(tbest, score=sc, method='tm', ok=True)
                    else:
                        entry = dict(tbest, score=sc, method='tm', ok=False, sift=best)
                else:
                    entry = dict(ok=False, sift=best)
            res[name] = entry
            if entry.get('ok'):
                last_page = entry['page']; scales.append(entry['scale'])
            print(f"{vid} {name} ok={entry.get('ok')} page={entry.get('page')} s={entry.get('scale', 0):.4f} tx={entry.get('tx', 0):.0f} ty={entry.get('ty', 0):.0f} score={entry.get('score', 0):.3f} {entry.get('method','')} ({time.time()-t0:.1f}s)", flush=True)
            json.dump(results, open(OUT, 'w'), indent=1, default=float)
    json.dump(results, open(OUT, 'w'), indent=1, default=float)

if __name__ == '__main__':
    main()
