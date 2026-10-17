"""Job configuration shared by every script.
The job file is $LECNOTES_JOB, else ./lecnotes_job.json in the current directory. Relative paths in it are
relative to course_dir. See references/job_example.json."""
import os, json
JOB_FILE = os.environ.get('LECNOTES_JOB') or os.path.join(os.getcwd(), 'lecnotes_job.json')
J = json.load(open(JOB_FILE, encoding='utf-8'))
ROOT = J['course_dir']
def _abs(p):
    return p if os.path.isabs(p) else os.path.join(ROOT, p)
W = _abs(J.get('work_dir', '_claude_work'))                 # big temporary stuff + state
PDF = _abs(J['lecture_pdf'])                                  # the clean lecture-note PDF (alignment target)
OUT_PDF = _abs(J['out_pdf'])
TRANSCRIPT_DIR = _abs(J.get('transcript_dir', 'Lecture Video/전사본'))
COURSE_TITLE = J.get('course_title', '')
RENDER = os.path.join(W, 'render')                            # 200-dpi page renders
OVERLAY = os.path.join(W, 'overlay')                          # ink_page{p}.png (RGBA, 200 dpi) - keep between runs
NOTES_DIR = os.path.join(W, 'notes')                          # notes_{KEY}.py - keep between runs
ALIGN = os.path.join(W, 'align_device.json')
RESCUE = os.path.join(W, 'align_rescue.json')
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = _abs(J['fonts_dir']) if J.get('fonts_dir') else os.path.join(SKILL_DIR, 'fonts')
PEN_FONT = J.get('pen_font', 'NanumPenScript-Regular.ttf')     # handwriting-style font for the notes
FALLBACK_FONT = J.get('fallback_font', 'NotoSansKR[wght].ttf')  # glyphs the pen font lacks (Greek, math symbols)
LANGUAGE = J.get('language', 'ko')                              # Whisper language code of the lectures
VIDEOS = J['videos']                                          # [{"key": "L4-1", "file": "...mp4", "date": "2026-09-09"}]
ORDER = [v['key'] for v in VIDEOS]
MIN_PAGE = int(J.get('min_page', 1))                          # overlay rebuild touches only pages >= this (earlier ink kept)
UI_TOP_FRAC = float(J.get('ui_top_frac', 258 / 1668))         # app chrome (status bar + toolbar) height / frame height
DPI = 200

def video(key):
    for v in VIDEOS:
        if v['key'] == key:
            return v
    raise KeyError(key)
def video_file(key):
    return _abs(video(key)['file'])
def asr_file(key):
    f = os.path.join(W, key + '.jsonl')
    return f if os.path.exists(f) else None
for d in (W, RENDER, OVERLAY, NOTES_DIR):
    os.makedirs(d, exist_ok=True)

# OpenCV on Windows cannot open non-ASCII paths -> route imread/imwrite through numpy buffers
import cv2 as _cv2, numpy as _np
if not getattr(_cv2, '_unicode_patched', False):
    def _imread(path, flags=_cv2.IMREAD_COLOR):
        try:
            buf = _np.fromfile(path, dtype=_np.uint8)
        except OSError:
            return None
        return _cv2.imdecode(buf, flags) if buf.size else None
    def _imwrite(path, img, params=None):
        ok, buf = _cv2.imencode(os.path.splitext(path)[1] or '.png', img, params or [])
        if ok:
            buf.tofile(path)
        return ok
    _cv2.imread, _cv2.imwrite, _cv2._unicode_patched = _imread, _imwrite, True
