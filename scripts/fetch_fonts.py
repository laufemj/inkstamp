"""Download the two fonts the notes are drawn with (both SIL Open Font License 1.1) into <skill>/fonts,
together with their license files. Standard library only.  usage: python scripts/fetch_fonts.py"""
import os, sys, urllib.request

BASE = 'https://github.com/google/fonts/raw/main/ofl/'
FILES = [  # (url path, local name, minimum size in bytes)
    ('nanumpenscript/NanumPenScript-Regular.ttf', 'NanumPenScript-Regular.ttf', 1_000_000),
    ('nanumpenscript/OFL.txt', 'OFL-NanumPenScript.txt', 1_000),
    ('notosanskr/NotoSansKR%5Bwght%5D.ttf', 'NotoSansKR[wght].ttf', 5_000_000),
    ('notosanskr/OFL.txt', 'OFL-NotoSansKR.txt', 1_000),
]
DEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fonts')

def main():
    os.makedirs(DEST, exist_ok=True)
    for path, name, min_size in FILES:
        out = os.path.join(DEST, name)
        if os.path.exists(out) and os.path.getsize(out) >= min_size:
            print('ok      ', name); continue
        print('download', name, '...', end=' ', flush=True)
        with urllib.request.urlopen(BASE + path, timeout=120) as r:
            data = r.read()
        if len(data) < min_size:
            sys.exit(f'\n{name}: got {len(data)} bytes, expected at least {min_size} -> check {BASE + path}')
        with open(out, 'wb') as f:
            f.write(data)
        print(f'{len(data) / 1e6:.1f} MB')
    print('fonts ready in', DEST)

if __name__ == '__main__':
    main()
