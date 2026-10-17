"""remove tiny specks from ink pngs. usage: python clean_specks.py [page ...]"""
import cv2, numpy as np, glob, os, sys
from paths import OVERLAY
pages = set(int(a) for a in sys.argv[1:])
for f in sorted(glob.glob(os.path.join(OVERLAY, 'ink_page*.png'))):
    if pages and int(os.path.basename(f)[8:-4]) not in pages: continue
    a = cv2.imread(f, cv2.IMREAD_UNCHANGED)
    n, lab, st, _ = cv2.connectedComponentsWithStats((a[:, :, 3] > 40).astype(np.uint8), 8)
    kill = np.zeros(n, bool)
    for i in range(1, n):
        x, y, w, h, area = st[i]
        kill[i] = area < 40 or (w < 7 and h < 7)
    a[kill[lab], 3] = 0
    cv2.imwrite(f, a)
print('specks cleaned')
