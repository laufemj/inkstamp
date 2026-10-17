"""Pick 'views' from a lecture video: decode keyframes only (PyAV), detect view changes on a downscaled
gray image (pixel diff or scroll), keep the keyframe just BEFORE each change (= the finished state of that view)
plus the last keyframe, saved full-res as views_<KEY>/v_<kfidx>_<sec>s.jpg.
usage: python extract_views.py L7-3 [L8-1 ...] [--max-sec 240] [--out DIR]"""
import sys, os, time
import av, cv2, numpy as np
import paths

def views(key, max_sec=None, out=None):
    src = paths.video_file(key)
    out = out or os.path.join(paths.W, f'views_{key}')
    os.makedirs(out, exist_ok=True)
    c = av.open(src); st = c.streams.video[0]
    st.codec_context.skip_frame = 'NONKEY'
    prev_small = prev_full = None; prev_t = 0.0; i = -1; last_change = -10; saved = []
    t0 = time.time()
    def save(idx, t, img):
        fn = os.path.join(out, f'v_{idx:04d}_{int(round(t)):05d}s.jpg')
        cv2.imwrite(fn, img, [cv2.IMWRITE_JPEG_QUALITY, 95]); saved.append(fn)
    for frame in c.decode(st):
        i += 1
        t = float(frame.pts * st.time_base) if frame.pts is not None else prev_t
        if max_sec and t > max_sec:
            break
        img = frame.to_ndarray(format='bgr24')
        h = img.shape[0]
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)[int(h * 0.114): int(h * 0.989)]   # skip status bar + toolbar
        small = cv2.resize(g, (299, 183), interpolation=cv2.INTER_AREA).astype(np.float32)
        if prev_small is not None:
            frac = float((np.abs(small - prev_small) > 40).mean())
            (dx, dy), _ = cv2.phaseCorrelate(prev_small, small)
            if frac > 0.02 or abs(dx) > 2 or abs(dy) > 2:
                if i - last_change > 1:
                    save(i - 1, prev_t, prev_full)
                last_change = i
        prev_small, prev_full, prev_t = small, img, t
    if prev_full is not None:
        save(i, prev_t, prev_full)
    c.close()
    print(f'{key}: {i + 1} keyframes, {len(saved)} views -> {out} ({time.time() - t0:.0f}s)', flush=True)

if __name__ == '__main__':
    args = sys.argv[1:]
    ms = float(args[args.index('--max-sec') + 1]) if '--max-sec' in args else None
    out = args[args.index('--out') + 1] if '--out' in args else None
    keys = [a for k, a in enumerate(args) if not a.startswith('--') and (k == 0 or args[k - 1] not in ('--max-sec', '--out'))]
    for k in keys:
        views(k, ms, out)
