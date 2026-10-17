"""Second pass over align_device.json:
 (1) failed frames -> retry SIFT against neighbour pages at 200 and 400 dpi, score only on the in-page part of the frame
 (2) every aligned frame whose view runs past the page top/bottom -> align the remainder to the adjacent page
     (same scale & tx expected), stored as extra entry '<frame>#p<q>'.
usage: python rescue_align.py [L4-2 ...] [--no-split]"""
import sys, os, json, glob, time
import numpy as np, cv2, pypdfium2 as pdfium
import paths
from paths import W, PDF, RENDER
import align as ad
SRC = paths.ALIGN
OUT = paths.RESCUE   # per-video results; overlay prefers these over align_device.json
FW, FH = 2388, 1668   # reset from the first frame read (see _set_frame_size)
args = [a for a in sys.argv[1:] if not a.startswith('--')]
SPLIT = '--no-split' not in sys.argv
RETRY = '--retry' in sys.argv
_doc = pdfium.PdfDocument(PDF)
_hr = {}
def page_hr(p):
    if p not in _hr:
        f = os.path.join(RENDER, f'page{p}_400.png')
        if not os.path.exists(f):
            _doc[p - 1].render(scale=400 / 72).to_pil().convert('L').save(f)
        g = cv2.imread(f, cv2.IMREAD_GRAYSCALE)
        kp, des = ad.sift.detectAndCompute(g, None)
        _hr[p] = (g, kp, des)
    return _hr[p]

_raw = {}
def page_raw_feats(p):
    """200-dpi page in plain gray (PDF colour text kept) -> for pages printed largely in colour"""
    if p not in _raw:
        g = cv2.cvtColor(cv2.imread(os.path.join(RENDER, f'page{p}.png')), cv2.COLOR_BGR2GRAY)
        kp, des = ad.sift.detectAndCompute(g, None)
        _raw[p] = (g, kp, des)
    return _raw[p]

def sift_match(kp, des, p, hr):
    g, pkp, pdes = (page_raw_feats(p) if hr == 'raw' else page_hr(p) if hr else ad.page_data(p))
    if des is None or pdes is None or len(kp) < 20:
        return None
    knn = cv2.BFMatcher(cv2.NORM_L2).knnMatch(des, pdes, k=2)
    good = [m for m, n in (mn for mn in knn if len(mn) == 2) if m.distance < 0.75 * n.distance]
    if len(good) < 15:
        return None
    src = np.float64([kp[m.queryIdx].pt for m in good]); dst = np.float64([pkp[m.trainIdx].pt for m in good])
    M, cnt = ad.ransac_scale_trans(src, dst, smin=0.15, smax=4.0)
    if M is None:
        return None
    k = 0.5 if hr is True else 1.0
    return dict(page=p, scale=M[0] * k, tx=M[1] * k, ty=M[2] * k, inliers=cnt, n_good=len(good), hr=hr)

_clean = {}
def page_clean(p):
    """page render in gray with the PDF's own coloured text whitened (the frame side gets the same treatment)"""
    if p not in _clean:
        _clean[p] = ad.clean_gray(cv2.imread(os.path.join(RENDER, f'page{p}.png')))
    return _clean[p]

def masked_score(fg, p, s, tx, ty, valid=None, raw=False):
    """NCC between frame and warped page over frame pixels that land inside the page (rows >= CLEAR_TOP)."""
    g = page_raw_feats(p)[0] if raw else page_clean(p)
    Minv = np.array([[1 / s, 0, -tx / s], [0, 1 / s, -ty / s]], dtype=np.float64)
    warped = cv2.warpAffine(g, Minv, (FW, FH), flags=cv2.INTER_AREA, borderValue=255)
    inside = cv2.warpAffine(np.full(g.shape, 255, np.uint8), Minv, (FW, FH), flags=cv2.INTER_NEAREST, borderValue=0) > 0
    inside[:ad.CLEAR_TOP] = False
    inside = cv2.erode(inside.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    if valid is not None:
        inside &= valid
    frac = inside.mean() / (1 - ad.CLEAR_TOP / FH)
    if frac < 0.12:
        return -1.0, frac
    a = fg[inside].astype(np.float32); b = warped[inside].astype(np.float32)
    a -= a.mean(); b -= b.mean()
    return float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-9)), float(frac)

def page_rows(s, ty, ph):
    """frame rows [r0, r1) that show page content (page y in [0, ph])"""
    return int(np.clip(-ty / s, 0, FH)), int(np.clip((ph - ty) / s, 0, FH))

def best_alignment(fg, pages, valid=None, raw_gray=None):
    mask = None if valid is None else valid.astype(np.uint8) * 255
    kp, des = ad.sift.detectAndCompute(fg, mask)
    best = None
    for hr in (False, True, 'raw'):
      if best is not None and best['score'] >= 0.70 and best['inliers'] >= 40:
          break
      if hr == 'raw':
          if raw_gray is None:
              break
          kp, des = ad.sift.detectAndCompute(raw_gray, mask)
      for p in pages:
            r = sift_match(kp, des, p, hr)
            if r is None:
                continue
            sc, frac = masked_score(raw_gray if hr == 'raw' else fg, p, r['scale'], r['tx'], r['ty'], valid, raw=(hr == 'raw'))
            r.update(score=sc, frac=frac)
            if best is None or (sc, r['inliers']) > (best['score'], best['inliers']):
                best = r
    return best

def _set_frame_size(frame):
    global FW, FH
    FH, FW = frame.shape[:2]
    ad.UI_TOP = int(round(paths.UI_TOP_FRAC * FH)); ad.CLEAR_TOP = ad.UI_TOP + 52

def chain_align(vid, name, frame, res, names):
    """frame->frame SIFT (colour ink included) with the nearest aligned frames, composed with their frame->page map"""
    t = ad.frame_time(name)
    near = sorted((abs(ad.frame_time(k) - t), k) for k in names if res[k].get('ok') and k != name)[:6]
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY); g[:ad.UI_TOP] = 255
    kp, des = ad.sift.detectAndCompute(g, None)
    best = None
    for _, k in near:
        o = cv2.imread(os.path.join(W, f'views_{vid}', k)); og = cv2.cvtColor(o, cv2.COLOR_BGR2GRAY); og[:ad.UI_TOP] = 255
        okp, odes = ad.sift.detectAndCompute(og, None)
        if des is None or odes is None:
            continue
        knn = cv2.BFMatcher(cv2.NORM_L2).knnMatch(des, odes, k=2)
        good = [m for m, n in (mn for mn in knn if len(mn) == 2) if m.distance < 0.75 * n.distance]
        if len(good) < 15:
            continue
        src = np.float64([kp[m.queryIdx].pt for m in good]); dst = np.float64([okp[m.trainIdx].pt for m in good])
        M, cnt = ad.ransac_scale_trans(src, dst, smin=0.3, smax=3.0)
        if M is None or cnt < 15:
            continue
        sf, tfx, tfy = M
        # verify: NCC of this frame vs the other frame warped into it, over the overlap
        Minv = np.array([[sf, 0, tfx], [0, sf, tfy]], dtype=np.float64)   # this -> other coords; warp other into this
        w = cv2.warpAffine(og, Minv, (FW, FH), flags=cv2.INTER_AREA | cv2.WARP_INVERSE_MAP, borderValue=0)
        inside = cv2.warpAffine(np.full(og.shape, 255, np.uint8), Minv, (FW, FH), flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP, borderValue=0) > 0
        inside[:ad.CLEAR_TOP] = False
        frac = float(inside.mean())
        if frac < 0.2:
            continue
        a = g[inside].astype(np.float32); b2 = w[inside].astype(np.float32); a -= a.mean(); b2 -= b2.mean()
        sc = float((a * b2).sum() / (np.sqrt((a * a).sum() * (b2 * b2).sum()) + 1e-9))
        e = res[k]
        r = dict(page=e['page'], scale=e['scale'] * sf, tx=e['scale'] * tfx + e['tx'], ty=e['scale'] * tfy + e['ty'],
                 inliers=cnt, hr='chain', via=k, score=sc, frac=frac)
        if sc >= 0.80 and (best is None or (cnt, sc) > (best['inliers'], best['score'])):
            best = r
    return best

def accept(b):
    return bool(b) and ((b['score'] >= 0.70 and b['inliers'] >= 20) or (b['score'] >= 0.85 and b['inliers'] >= 10)
                        or (b.get('hr') == 'tm' and b['score'] >= 0.80 and b['frac'] >= 0.4))

def main():
    src = json.load(open(SRC))
    res_all = json.load(open(OUT)) if os.path.exists(OUT) else {}
    vids = args or list(src)
    for v in vids:
        if v not in res_all:
            res_all[v] = src[v]
        else:   # pick up frames the main pass added since
            for k, e in src[v].items():
                res_all[v].setdefault(k, e)
    for vid in vids:
        res = res_all[vid]
        names = sorted([k for k in res if '#' not in k], key=ad.frame_time)
        okpages = [(ad.frame_time(k), res[k]['page']) for k in names if res[k].get('ok')]
        for name in names:
            e = res[name]
            frame = None
            if not e.get('ok') and (RETRY or not e.get('rescue_tried')):
                t = ad.frame_time(name)
                prev = [p for tt, p in okpages if tt <= t][-1:]; nxt = [p for tt, p in okpages if tt >= t][:1]
                pages = sorted({q for p in prev + nxt for q in (p - 1, p, p + 1) if 1 <= q <= ad.NPAGES}) or list(range(1, ad.NPAGES + 1))
                frame = cv2.imread(os.path.join(W, f'views_{vid}', name)); _set_frame_size(frame)
                fg = ad.clean_gray(frame); fg[:ad.UI_TOP] = 255
                t0 = time.time()
                rg = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY); rg[:ad.UI_TOP] = 255
                b = best_alignment(fg, pages, raw_gray=rg)
                if not accept(b):   # template matching on the raw image at the zoom of nearby frames
                    near = sorted((abs(ad.frame_time(k) - t), res[k]['scale']) for k in names if res[k].get('ok'))[:4]
                    for sc in sorted({round(v, 3) for _, v in near}):
                        for p in pages:
                            r = ad.tm_search(rg, p, sc)
                            if r is None:
                                continue
                            r['score'], r['frac'] = masked_score(rg, p, r['scale'], r['tx'], r['ty'], raw=True)
                            r['inliers'] = 0; r['hr'] = 'tm'
                            if b is None or r['score'] > b['score']:
                                b = r
                if not accept(b):   # chain through a neighbouring aligned frame showing the same ink
                    c = chain_align(vid, name, frame, res, names)
                    if c is not None:
                        b = c
                if accept(b):
                    res[name] = dict(b, method='rescue', ok=True)
                else:
                    e['rescue_tried'] = True
                    e['rescue_best'] = b
                r = res[name]
                print(f"{vid} {name} rescue -> ok={r.get('ok')} {b and {k: round(v, 3) if isinstance(v, float) else v for k, v in b.items()}} ({time.time() - t0:.0f}s)", flush=True)
            e = res[name]
            if SPLIT and e.get('ok') and not e.get('split_done'):
                s, tx, ty, p = e['scale'], e['tx'], e['ty'], e['page']
                r0, r1 = page_rows(s, ty, ad.page_data(p)[0].shape[0])
                top_extra = r0 - ad.CLEAR_TOP; bot_extra = FH - r1
                for q, extra, rows in ((p - 1, top_extra, (ad.CLEAR_TOP, r0)), (p + 1, bot_extra, (r1, FH))):
                    if extra < 220 or not (1 <= q <= ad.NPAGES) or f'{name}#p{q}' in res:
                        continue
                    if frame is None:
                        frame = cv2.imread(os.path.join(W, f'views_{vid}', name)); _set_frame_size(frame)
                    fg = ad.clean_gray(frame); fg[:ad.UI_TOP] = 255
                    valid = np.zeros((FH, FW), bool); valid[rows[0]:rows[1]] = True
                    b = best_alignment(fg, [q], valid)
                    good = b and b['score'] >= 0.62 and abs(b['scale'] / s - 1) < 0.03 and abs(b['tx'] - tx) < 40 * s
                    if good:
                        res[f'{name}#p{q}'] = dict(b, method='split', ok=True, parent=name)
                    print(f"{vid} {name} split p{p}->p{q} rows {rows} ok={bool(good)} {b and (round(b['score'], 3), round(b['scale'], 3), round(b['tx']), b['inliers'])}", flush=True)
                e['split_done'] = True
            json.dump(res_all, open(OUT, 'w'), indent=1, default=float)
    for vid in vids:
        d = res_all[vid]; base = [k for k in d if '#' not in k]
        print(vid, 'ok', sum(d[k].get('ok', False) for k in base), '/', len(base), ' extra split entries', sum('#' in k for k in d))

if __name__ == '__main__':
    main()
