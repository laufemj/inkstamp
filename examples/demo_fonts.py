"""(library) Fonts for the synthetic demo and the demo video: downloaded on first use from the google/fonts repository
(all SIL Open Font License 1.1) into fonts/video/, which is not committed."""
import os, urllib.request

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(SKILL, 'fonts', 'video')
FILES = {'serif': 'instrumentserif/InstrumentSerif-Regular.ttf', 'serif-it': 'instrumentserif/InstrumentSerif-Italic.ttf',
         'sans': 'inter/Inter%5Bopsz,wght%5D.ttf', 'mono': 'jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf',
         'hand': 'caveat/Caveat%5Bwght%5D.ttf'}

def font_path(key, fallback=None):
    """local path of a font, downloading it if needed; returns `fallback` when offline"""
    os.makedirs(DIR, exist_ok=True)
    path = os.path.join(DIR, FILES[key].split('/')[-1].replace('%5B', '[').replace('%5D', ']'))
    if not os.path.exists(path):
        try:
            with urllib.request.urlopen('https://github.com/google/fonts/raw/main/ofl/' + FILES[key], timeout=120) as r:
                data = r.read()
            open(path, 'wb').write(data)
        except OSError:
            if fallback:
                return fallback
            raise
    return path
