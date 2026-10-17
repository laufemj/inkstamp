"""Erase a laser-pointer stroke that overlay.py kept (it happens when the stroke crosses real ink and merges with it):
removes red/pink pixels inside a page box (200-dpi px) of overlay/ink_page{p}.png and redraws debug_page{p}.jpg.
Check the source frame first (toolbar in laser mode, glowing stroke) and keep the box tight: real red ink inside it goes too.
The first call per page saves the untouched ink as overlay/backup/ink_page{p}.png. Rerun after overlay.py rebuilds the page.
usage: python erase_laser.py <page> <x0> <y0> <x1> <y1>"""
import os, shutil, sys
import cv2, numpy as np
from paths import OVERLAY, RENDER

p = int(sys.argv[1]); x0, y0, x1, y1 = map(int, sys.argv[2:6])
ink_path = os.path.join(OVERLAY, f'ink_page{p}.png')
backup = os.path.join(OVERLAY, 'backup'); os.makedirs(backup, exist_ok=True)
if not os.path.exists(os.path.join(backup, f'ink_page{p}.png')):
    shutil.copy2(ink_path, backup)
ink = cv2.imread(ink_path, cv2.IMREAD_UNCHANGED)
box = ink[y0:y1, x0:x1]
hue = cv2.cvtColor(np.ascontiguousarray(box[:, :, :3]), cv2.COLOR_BGR2HSV)[:, :, 0]
laser = ((hue <= 12) | (hue >= 160)) & (box[:, :, 3] > 0)   # GoodNotes laser: red rim + pink glow (OpenCV hue 0..179)
box[laser] = 0
cv2.imwrite(ink_path, ink)
base = cv2.imread(os.path.join(RENDER, f'page{p}.png')).astype(np.float32)
a = ink[:, :, 3:4].astype(np.float32) / 255
comp = (base * (1 - a) + ink[:, :, :3].astype(np.float32) * a).astype(np.uint8)
h, w = comp.shape[:2]
cv2.imwrite(os.path.join(OVERLAY, f'debug_page{p}.jpg'), cv2.resize(comp, (w // 2, h // 2), interpolation=cv2.INTER_AREA),
            [cv2.IMWRITE_JPEG_QUALITY, 85])
print(f'page {p}: erased {int(laser.sum())} px in ({x0},{y0})-({x1},{y1}); backup in {backup}')
