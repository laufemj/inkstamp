# -*- coding: utf-8 -*-
"""Local lecture transcription (faster-whisper large-v3-turbo; CUDA if it works, else CPU int8).
1) downloads the model, 2) finds a CTranslate2 setting that works on this machine (each probe runs in a separate
process, so a crash only kills the probe), 3) transcribes in a worker process: ~10-min chunks cut at quiet points
(one long call -> Windows stack overflow), BatchedInferencePipeline.
Outputs in the job work dir: KEY.jsonl (+ .done), transcribe_status.txt, transcribe_log.txt,
ct2_config.json (chosen setting + measured probe speed).
usage: python transcribe.py [KEY ...]   (default: every job video without KEY.jsonl.done)
       python transcribe.py --probe-only  (find a setting and measure speed on 60 s of audio, then stop)"""
import os, sys, json, time, traceback, faulthandler, platform, subprocess, glob, re
os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')
os.environ.setdefault('KMP_DUPLICATE_LIB_OK', 'TRUE')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
here = paths.W

def _add_cuda_libs():
    """cuBLAS/cuDNN from the pip wheels nvidia-cublas-cu12 / nvidia-cudnn-cu12 (setup installs them when an NVIDIA GPU
    exists) -> make their DLLs / .so files findable for CTranslate2, also in the probe/worker subprocesses"""
    import importlib.util
    dirs = []
    for mod in ('nvidia.cublas', 'nvidia.cudnn'):
        try:
            spec = importlib.util.find_spec(mod)
        except (ImportError, ValueError):
            spec = None
        for base in (list(spec.submodule_search_locations or []) if spec else []):
            for sub in ('bin', 'lib'):
                if os.path.isdir(os.path.join(base, sub)):
                    dirs.append(os.path.join(base, sub))
    if dirs:
        var = 'PATH' if os.name == 'nt' else 'LD_LIBRARY_PATH'
        os.environ[var] = os.pathsep.join(dirs + [os.environ.get(var, '')])
        if os.name == 'nt':
            for d in dirs:
                os.add_dll_directory(d)
_add_cuda_libs()
LOG = open(os.path.join(here, 'transcribe_log.txt'), 'a', encoding='utf-8', buffering=1)
faulthandler.enable(file=LOG, all_threads=False)
CFG = os.path.join(here, 'ct2_config.json')
REPO = 'mobiuslabsgmbh/faster-whisper-large-v3-turbo'

def log(msg):
    line = time.strftime('%H:%M:%S ') + msg
    print(line, flush=True); LOG.write(line + '\n'); LOG.flush()
def status(msg):
    with open(os.path.join(here, 'transcribe_status.txt'), 'w', encoding='utf-8') as f:
        f.write(time.strftime('%H:%M:%S ') + msg + '\n')

def load_audio(path, max_sec=None):
    """decode any audio/video file to 16 kHz mono float32 (own PyAV loop; avoids faster-whisper/PyAV version clashes)"""
    import av, numpy as np
    out, n, limit = [], 0, (int(max_sec * 16000) if max_sec else None)
    with av.open(path) as c:
        rs = av.AudioResampler(format='s16', layout='mono', rate=16000)
        for frame in c.decode(c.streams.audio[0]):
            for f in rs.resample(frame):
                a = f.to_ndarray().reshape(-1); out.append(a); n += a.size
            if limit and n >= limit:
                break
        else:
            for f in rs.resample(None) or []:
                out.append(f.to_ndarray().reshape(-1))
    x = np.concatenate(out).astype(np.float32) / 32768.0
    return x[:limit] if limit else x

def probe(model_path, dev, ct, th, test, sec=20.0):
    import faster_whisper as fw
    m = fw.WhisperModel(model_path, device=dev, compute_type=ct, cpu_threads=th)
    a = load_audio(test, sec); t0 = time.time()
    segs, info = m.transcribe(a, language=paths.LANGUAGE, beam_size=1)
    txt = ' '.join(x.text for x in segs)
    print('PROBE_OK speed=x%.1f' % (len(a) / 16000 / max(0.01, time.time() - t0)), txt[:60], flush=True)

# ---------------------------------------------------------------- worker (runs with the chosen env)
def worker(cfg, order, model_path):
    from faster_whisper import WhisperModel, BatchedInferencePipeline
    import numpy as np
    log('worker: loading model %s' % json.dumps(cfg))
    model = WhisperModel(model_path, device=cfg.get('device', 'cpu'), compute_type=cfg['compute_type'], cpu_threads=cfg['threads'])
    pipe = BatchedInferencePipeline(model=model)
    t_all = time.time()
    for n in order:
        out = os.path.join(here, '%s.jsonl' % n)
        if os.path.exists(out + '.done'):
            log('Lecture %s already done' % n); continue
        src = os.path.join(here, '%s.flac' % n)
        if not os.path.exists(src):
            src = paths.video_file(n)
        log('Lecture %s: start (%s)' % (n, os.path.basename(src)))
        t0 = time.time()
        status('Lecture %s: decoding audio' % n)
        audio = load_audio(src); dur = audio.size / 16000
        # long audio in one call -> stack overflow on Windows: cut ~10 min chunks at the quietest point near each mark
        cuts, CH, W = [0], 600 * 16000, 15 * 16000
        while cuts[-1] + CH + W < audio.size:
            mid = cuts[-1] + CH
            win = audio[mid - W: mid + W] ** 2
            e = np.convolve(win, np.ones(8000) / 8000, mode='valid')
            cuts.append(mid - W + int(e.argmin()) + 4000)
        cuts.append(audio.size)
        with open(out + '.part', 'w', encoding='utf-8') as f:
            for a, b in zip(cuts[:-1], cuts[1:]):
                off = a / 16000
                segs, info = pipe.transcribe(audio[a:b], language=paths.LANGUAGE, batch_size=(8 if cfg.get('device') == 'cuda' else 4), beam_size=1)
                for s in segs:
                    f.write(json.dumps({'start': round(s.start + off, 2), 'end': round(s.end + off, 2), 'text': s.text.strip()}, ensure_ascii=False) + chr(10)); f.flush()
                    msg = 'Lecture %s: %5.1f / %.1f min (%.0f s elapsed)' % (n, (s.end + off) / 60, dur / 60, time.time() - t0)
                    print(chr(13) + msg, end='', flush=True); status(msg)
        class info: duration = dur
        os.replace(out + '.part', out); open(out + '.done', 'w').close()
        print()
        log('Lecture %s done in %.1f min (audio %.1f min, speed x%.1f)' % (n, (time.time() - t0) / 60, info.duration / 60, info.duration / max(1, time.time() - t0)))
    log('ALL DONE in %.1f min' % ((time.time() - t_all) / 60)); status('ALL DONE')

def candidates():
    """(extra env, device, compute_type, threads) in order of preference"""
    th = max(4, min(16, (os.cpu_count() or 8) - 4))
    c = []
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            c += [({}, 'cuda', 'float16', 4), ({}, 'cuda', 'int8_float16', 4)]
    except Exception:
        pass
    c += [({}, 'cpu', 'int8', th), ({'CT2_USE_MKL': '0'}, 'cpu', 'int8', th), ({'CT2_FORCE_CPU_ISA': 'AVX2'}, 'cpu', 'int8', th),
          ({}, 'cpu', 'int8', 4), ({}, 'cpu', 'float32', 8), ({'CT2_FORCE_CPU_ISA': 'GENERIC'}, 'cpu', 'int8', 8)]
    return c

def main():
    order = [a for a in sys.argv[1:] if not a.startswith('--')] or [k for k in paths.ORDER if not os.path.exists(os.path.join(here, k + '.jsonl.done'))]
    log('==== start  python %s  %s  cpu_count=%s  order=%s' % (sys.version.split()[0], platform.platform(), os.cpu_count(), order))
    try:
        import ctypes, ctranslate2
        k = ctypes.windll.kernel32
        for dll in ('msvcp140.dll', 'vcruntime140.dll'):
            buf = ctypes.create_unicode_buffer(400); h = k.GetModuleHandleW(dll)
            k.GetModuleFileNameW(h, buf, 400) if h else None
            log('%s loaded from: %s' % (dll, buf.value or '(not loaded)'))
    except Exception as e:
        log('runtime check skipped: %r' % (e,))
    status('downloading model')
    from huggingface_hub import snapshot_download
    path = snapshot_download(REPO)
    sizes = {os.path.basename(f): os.path.getsize(f) for f in glob.glob(os.path.join(path, '*'))}
    log('model files: %s' % sizes)
    if sizes.get('model.bin', 0) < 1_000_000_000:
        log('model.bin looks incomplete -> re-downloading')
        path = snapshot_download(REPO, force_download=True)
    cfg = None
    if os.path.exists(CFG):
        cfg = json.load(open(CFG)); log('using saved setting %s' % json.dumps(cfg))
    else:
        test = paths.video_file(order[0] if order else paths.ORDER[0])
        for env, dev, ct, th in candidates():
            status('testing setting %s %s %s %d' % (env, dev, ct, th))
            t0 = time.time()
            try:
                r = subprocess.run([sys.executable, '-X', 'faulthandler', os.path.abspath(__file__), '--probe', path, dev, ct, str(th), test, '60'], env={**os.environ, **env},
                                   capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=600)
                ok = r.returncode == 0 and 'PROBE_OK' in r.stdout
                tail = (r.stdout + r.stderr).strip().replace('\n', ' | ')[-160:]
            except subprocess.TimeoutExpired:
                ok, tail = False, 'timeout'
            log('probe env=%s %s %s threads=%d -> %s (%.0f s) %s' % (env, dev, ct, th, 'OK' if ok else 'FAIL rc=%s' % (r.returncode if 'r' in dir() else '?'), time.time() - t0, tail))
            if ok:
                m = re.search(r'speed=x([0-9.]+)', r.stdout)
                cfg = {'env': env, 'device': dev, 'compute_type': ct, 'threads': th, 'probe_speed_x': float(m.group(1)) if m else None}
                json.dump(cfg, open(CFG, 'w')); break
        if cfg is None:
            raise RuntimeError('no CTranslate2 setting works on this computer -> use cloud transcription')
    if '--probe-only' in sys.argv:
        log('probe-only: %s' % json.dumps(cfg)); print(json.dumps(cfg)); return
    status('transcribing')
    r = subprocess.run([sys.executable, '-X', 'faulthandler', os.path.abspath(__file__), '--worker', json.dumps(cfg), path] + order,
                       env={**os.environ, **cfg['env']})
    if r.returncode != 0:
        log('worker failed (rc=%s); deleting saved setting so the next run re-tests' % r.returncode)
        try: os.remove(CFG)
        except OSError: pass
        sys.exit(1)

if __name__ == '__main__':
    try:
        if len(sys.argv) > 1 and sys.argv[1] == '--probe':
            probe(sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]), sys.argv[6], float(sys.argv[7]))
        elif len(sys.argv) > 1 and sys.argv[1] == '--worker':
            worker(json.loads(sys.argv[2]), sys.argv[4:], sys.argv[3])
        else:
            main()
    except BaseException as e:
        if isinstance(e, SystemExit) and e.code in (0, None): raise
        log('FAILED:\n' + traceback.format_exc()); status('FAILED - see transcribe_log.txt')
        sys.exit(1)
