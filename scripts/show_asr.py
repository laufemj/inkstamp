"""compact transcript dump: python show_asr.py KEY [--grep]   (--grep = only exam/notice keyword lines)"""
import json, sys, re
sys.stdout.reconfigure(encoding='utf-8')
import paths
from paths import asr_file
KW = r'각자|스킵|skip|읽어 보|읽어보|읽지|안 읽|안 내|낼 수|나올 수|숙지|파악|시험|출제|문제를 내|문제 내|안 나|안나와|외우|외워|암기|중요|꼭|반드시|숙제|과제|퀴즈|중간|기말|범위|제외|생략|넘어가|몰라도|안 해도|공지|출석|다음 시간|휴강|보강|교재|연습문제|리포트|제출'
KW = paths.J.get('keywords') or KW   # job may override (e.g. for other languages)
key = sys.argv[1]; g = '--grep' in sys.argv
rows = [json.loads(l) for l in open(asr_file(key), encoding='utf-8')]
for r in rows:
    t = int(r['start'])
    if g and not re.search(KW, r['text']):
        continue
    print(f"{t//60}:{t%60:02d} {r['text']}")
