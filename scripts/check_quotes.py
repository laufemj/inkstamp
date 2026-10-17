"""Verify every “quoted” remark in the notes files word for word against the raw transcripts (after the job's asr_fixes;
case, whitespace and punctuation are ignored). Each quote is split at '…' and every piece must occur in the note's own video.
Prints only the pieces that don't; ASR-corrected quotes then need a manual look. Board and printed text belong in ‘ ’.
usage: python check_quotes.py [KEY ...]   (default: all job videos)"""
import glob, json, os, re, sys
sys.stdout.reconfigure(encoding='utf-8')
import paths
from notes_loader import load_notes

norm = lambda s: re.sub(r'[\s.,?!~·\'"“”‘’()\[\]:;…-]+', '', s).lower()
fixes = paths.J.get('asr_fixes', [])
def transcript(key):
    t = ''.join(json.loads(l)['text'] for l in open(paths.asr_file(key), encoding='utf-8'))
    for x, y in fixes:
        t = t.replace(x, y)
    return norm(t)
tr = {k: transcript(k) for k in paths.ORDER if paths.asr_file(k)}
total = bad = 0
for key in (sys.argv[1:] or paths.ORDER):
    f = os.path.join(paths.NOTES_DIR, f'notes_{key}.py')
    if key not in tr or not os.path.exists(f):
        print(key, ': no transcript or notes file'); continue
    for page, notes in load_notes(f).NOTES.items():
        for n in notes:
            for q in re.findall(r'“([^”]+)”', (n.get('title') or '') + '\n' + n['text']):
                for piece in q.split('…'):
                    if len(norm(piece)) < 2:
                        continue
                    total += 1
                    if norm(piece) not in tr[key]:
                        bad += 1
                        other = [k for k, t in tr.items() if norm(piece) in t]
                        print(f'{key} p{page}: not in transcript: “{piece.strip()}”' + (f'  (found in {other})' if other else ''))
print(f'{total} quoted pieces checked, {bad} not found')
