"""(library) Navigation for the annotated PDF, added after all pages are written:
- index pages right after page 1 ("index": true in the job, default): every lecture box's ★ items and ※ scope lines,
  each a link to the page of the matching detailed note, plus a list of notes marked "확인 필요" / "needs checking";
- bookmarks: the index and one per lecture box;
- page labels: original page numbers stay as printed ("42"), memo pages read "42+", index pages "i, ii, …";
- optional video links: job "video_urls": {"L8-3": "https://…?t={t}"} makes each note of that lecture (and its index
  rows) open the recording at the note's first timestamp ({t} = seconds)."""
import io, re
from reportlab.pdfgen import canvas
from pypdf import PdfReader
from pypdf.annotations import Link
import paths
import compose as cm

TIME_RE = re.compile(r'(?<![\d:])(\d{1,2}):(\d{2})(?![\d])')
LECTURE_RE = re.compile(r'Lecture\s*(\d+(?:-\d+)?)')
CHECK_RE = re.compile(r'확인 필요|needs checking', re.I)

def _seconds(text):
    m = TIME_RE.search(text)
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None

def _lecture_label(title):
    m = re.search(r'(Lecture\s*\S+\s*\([^)]*\))', title)
    return m.group(1) if m else title.replace('★', '').strip()

def _page_label(key):
    ko = paths.LANGUAGE == 'ko'
    return f'{key}쪽' if ko else f'p. {key}'

def _is_lecture_box(r):   # the per-video summary box: title starts with ★ (the page-1 guide box starts with ✓)
    t = r['note'].get('title') or ''
    return bool(r['note'].get('box')) and t.lstrip().startswith('★')

def _group(placed):
    """-> list of lectures in document order: dict(box=record, items=[(kind, text, secs)], notes=[records])"""
    by_src = {}
    for r in placed:
        by_src.setdefault(r['note'].get('src', '?'), []).append(r)
    lectures, owner = [], {}
    for src, recs in by_src.items():
        boxes = [r for r in recs if _is_lecture_box(r)]
        if not boxes:
            continue
        cur = boxes[0]
        for r in recs:
            if r in boxes:
                cur = r
            owner[id(r)] = cur
    for r in placed:
        if _is_lecture_box(r) and id(r) in owner and owner[id(r)] is r:
            items = []
            for line in r['note']['text'].split('\n'):
                line = line.strip()
                if '★' in line:
                    items.append(('star', line, _seconds(line)))
                elif line.startswith('※'):
                    items.append(('scope', line, None))
            lectures.append(dict(box=r, items=items, notes=[x for x in placed if owner.get(id(x)) is r and x is not r]))
    return lectures

def _target(lec, secs):
    """page key of the detailed ★ note closest in time to secs (else the box's page)"""
    best = None
    for r in lec['notes']:
        if '★' not in r['note']['text']:
            continue
        t = _seconds(r['note']['text'])
        if t is None or secs is None:
            continue
        d = abs(t - secs)
        if best is None or d < best[0]:
            best = (d, r['page'])
    return best[1] if best and best[0] <= 120 else lec['box']['page']

def _video_url(lec, secs):
    m = LECTURE_RE.search(lec['box']['note']['title'])
    tpl = paths.J.get('video_urls', {}).get('L' + m.group(1)) if m else None
    return tpl.replace('{t}', str(secs)) if tpl and secs is not None else None

def _index_pages(lectures, checks, size):
    """draw the index; -> (PdfReader pages, links [(index page no, rect, ('page', key) | ('url', url))])"""
    W, H = size
    ko = paths.LANGUAGE == 'ko'
    buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=(W, H))
    L, R, TOP, BOT, FS = 50, W - 50, H - 60, 50, 12
    col_page = 64
    links, pno = [], 0
    y = TOP
    def newpage():
        nonlocal y, pno
        c.showPage(); pno += 1; y = TOP
    def need(h):
        if y - h < BOT:
            newpage()
    title = '★ 시험 관련 멘트 모아보기' if ko else '★ Exam-related remarks'
    sub = ('강의별 핵심 멘트(★)와 시험 범위 언급(※). 줄을 누르면 그 내용이 적힌 쪽으로 이동합니다.' if ko
           else 'Key remarks (★) and exam-scope remarks (※) per lecture. Tap a line to jump to its page.')
    cm.draw_rich(c, L, y - 22, title, 22, cm.NOTE); y -= 40
    cm.draw_rich(c, L, y - 12, sub, 12, cm.NOTE); y -= 34
    def row(text, key, url):
        nonlocal y
        lines = cm.wrap(text, FS, R - L - col_page - 10)
        h = len(lines) * FS * 1.3 + 5
        need(h)
        yy = y - FS
        for ln, ind in lines:
            cm.draw_rich(c, L + 12 + ind, yy, ln, FS, cm.NOTE); yy -= FS * 1.3
        c.setFont('Fb', FS * 0.74); c.setFillColor(cm.NOTE)
        c.drawRightString(R, y - FS, _page_label(key))
        links.append((pno, (L, y - h + 2, R, y + 2), ('page', key)))
        if url:
            c.drawString(L - 14, y - FS, '▶')
            links.append((pno, (L - 18, y - FS - 3, L + 6, y + 2), ('url', url)))
        y -= h
    for lec in lectures:
        if not lec['items']:
            continue
        need(FS * 4)
        y -= 8
        head = _lecture_label(lec['box']['note']['title'])
        cm.draw_rich(c, L, y - 15, head, 15, cm.NOTE)
        c.setStrokeColor(cm.BOX_LINE); c.setLineWidth(0.8); c.line(L, y - 20, R, y - 20)
        links.append((pno, (L, y - 22, R, y + 2), ('page', lec['box']['page'])))
        y -= 28
        for kind, text, secs in lec['items']:
            row(text, _target(lec, secs) if kind == 'star' else lec['box']['page'], _video_url(lec, secs) if kind == 'star' else None)
    if checks:
        need(FS * 5)
        y -= 16
        cm.draw_rich(c, L, y - 15, '※ 확인 필요' if ko else '※ Needs checking', 15, cm.NOTE)
        c.setStrokeColor(cm.BOX_LINE); c.line(L, y - 20, R, y - 20); y -= 28
        for r in checks:
            row(r['note']['text'].replace('\n', ' '), r['page'], None)
    c.showPage(); c.save(); buf.seek(0)
    return PdfReader(buf).pages, links

def finish(writer, page_index, placed, first_page_size):
    """page_index: page key (int page / 'P+' memo) -> writer index. Mutates writer."""
    lectures = _group(placed)
    checks = [r for r in placed if CHECK_RE.search(r['note']['text']) and not r['note'].get('box')]
    n_idx = 0
    if paths.J.get('index', True) and any(l['items'] for l in lectures):
        pages, links = _index_pages(lectures, checks, first_page_size)
        insert_at = 1 if len(writer.pages) > 1 else len(writer.pages)
        for k, pg in enumerate(pages):
            writer.insert_page(pg, insert_at + k)
        n_idx = len(pages)
        page_index = {k: (v + n_idx if v >= insert_at else v) for k, v in page_index.items()}
        for ipage, rect, (kind, val) in links:
            if kind == 'page' and val in page_index:
                writer.add_annotation(insert_at + ipage, Link(rect=rect, border=[0, 0, 0], target_page_index=page_index[val]))
            elif kind == 'url':
                writer.add_annotation(insert_at + ipage, Link(rect=rect, border=[0, 0, 0], url=val))
        writer.add_outline_item('★ 시험 관련 멘트 모아보기' if paths.LANGUAGE == 'ko' else '★ Exam-related remarks', insert_at)
    else:
        insert_at = None
    for lec in lectures:   # bookmarks
        key = lec['box']['page']
        if key in page_index:
            writer.add_outline_item(_lecture_label(lec['box']['note']['title']), page_index[key])
    for r in placed:       # video links on the notes themselves
        lec = next((l for l in lectures if r is l['box'] or r in l['notes']), None)
        url = _video_url(lec, _seconds(r['note']['text'])) if lec else None
        if url and r['page'] in page_index:
            x0, y0, x1, y1 = r['rect']
            writer.add_annotation(page_index[r['page']], Link(rect=(x0, y0, x1, y1), border=[0, 0, 0], url=url))
    # page labels: printed numbers for original pages, "42+" for memo pages, roman numerals for the index
    inv = sorted((v, k) for k, v in page_index.items())
    run = None
    def flush():
        if run:
            writer.set_page_label(run[0], run[1], style='/D', start=run[2])
    for idx, key in inv:
        if isinstance(key, int):
            if run and idx == run[1] + 1 and key == run[3] + 1:
                run = (run[0], idx, run[2], key)
            else:
                flush(); run = (idx, idx, key, key)
        else:
            flush(); run = None
            writer.set_page_label(idx, idx, prefix=str(key))
    flush()
    if n_idx:
        writer.set_page_label(insert_at, insert_at + n_idx - 1, style='/r', start=1)
    return n_idx
