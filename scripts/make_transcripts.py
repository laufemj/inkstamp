"""Write <transcript_dir>/<video file name> 전사본.txt from work/KEY.jsonl.  usage: python make_transcripts.py [KEY ...] (default: all job videos)
fixes = common ASR mistakes for this kind of lecture (Korean engineering math); extend per course."""
import json, os, sys
import paths
from paths import asr_file, TRANSCRIPT_DIR
# common Korean ASR slips in math/engineering lectures; add course-specific ones via the job's "asr_fixes": [["wrong", "right"], ...]
fixes = [('디터미난트', 'determinant'), ('디터미넌트', 'determinant'), ('이그젠프', 'example'), ('이그젠플', 'example'), ('이그젬플', 'example'),
         ('항등행열', '항등행렬'), ('역행열', '역행렬'), ('구면저표계', '구면좌표계'), ('구면접표계', '구면좌표계'), ('구면잡표계', '구면좌표계'), ('구면저표', '구면좌표'),
         ('지켜자표계', '직교좌표계'), ('직조자표계', '직교좌표계'), ('오소노말', 'orthonormal'), ('오토 노말', 'orthonormal'),
         ('저평면', '접평면'), ('공면', '곡면'), ('메비우스', '뫼비우스'), ('아코비', '야코비'), ('변미분계수', '편미분계수'),
         ('법백터장', '법벡터장'), ('접백터장', '접벡터장'), ('채집 bt', 'ChatGPT'), ('채집 BT', 'ChatGPT'),
         ('가건소', '각원소'), ('각원소백타장', '각원소벡터장'), ('뿌엥까레', '푸앵카레'), ('뿌엥깔', '푸앵카레'), ('뺑갈', '푸앵카레'), ('뺀까레', '푸앵카레'), ('뾱카레', '푸앵카레'),
         ('알자힘', '알짜힘'), ('알짜임', '알짜힘'), ('넷벌스', 'net force'), ('뮤톤', '뉴턴'), ('만윤력', '만유인력'), ('진량', '질량'), ('푸빈이', '푸비니')]
fixes += [tuple(x) for x in paths.J.get('asr_fixes', [])]
def ts(t): return f"{int(t)//60}:{int(t)%60:02d}"
os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
for key in (sys.argv[1:] or paths.ORDER):
    date = paths.video(key).get('date', '')
    if not asr_file(key):
        print('no transcript for', key); continue
    name = os.path.splitext(os.path.basename(paths.video(key)['file']))[0]   # e.g. 'Lecture 4-1'
    lines = [f"{paths.COURSE_TITLE} — {name} 강의 영상 ({os.path.basename(paths.video(key)['file'])}{', ' + date + ' 녹화' if date else ''}) 교수님 말씀 전사본",
             "※ 음성 인식(Whisper)으로 자동 전사한 것이라 오타·오인식이 있을 수 있음. 시각은 영상 기준 m:ss.", ""]
    for line in open(asr_file(key), encoding='utf-8'):
        r = json.loads(line); t = r['text']
        for x, y in fixes: t = t.replace(x, y)
        lines.append(f"[{ts(r['start'])}~{ts(r['end'])}] {t}")
    open(os.path.join(TRANSCRIPT_DIR, f'{name} 전사본.txt'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print(name, len(lines))
