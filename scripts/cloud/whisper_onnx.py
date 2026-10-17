#!/usr/bin/env python3
"""Greedy Whisper decoding with onnxruntime using sherpa-onnx exported models.
Own token->text assembly so byte-level BPE tokens are merged correctly (sherpa-onnx CLI
drops them for Korean)."""
import sys, json, base64, time, wave, os
import numpy as np
import onnxruntime as ort

MODEL_DIR = sys.argv[1]
WAV = sys.argv[2]
OUT = sys.argv[3]
MAX_CHUNK = float(sys.argv[4]) if len(sys.argv) > 4 else 24.0
LANG = sys.argv[5] if len(sys.argv) > 5 else 'ko'   # usage: whisper_onnx.py MODEL_DIR in.wav out.jsonl [max_chunk_s] [lang]

# ---------------- audio ----------------
def read_wav(path):
    with wave.open(path, 'rb') as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2
        n = w.getnframes()
        data = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
    return data

# ---------------- mel (whisper-compatible, librosa slaney filters) ----------------
def mel_filters(sr=16000, n_fft=400, n_mels=128):
    def hz_to_mel(f):
        f = np.asarray(f, dtype=np.float64)
        f_sp = 200.0 / 3
        mels = f / f_sp
        min_log_hz = 1000.0
        min_log_mel = min_log_hz / f_sp
        logstep = np.log(6.4) / 27.0
        if mels.ndim == 0:
            return min_log_mel + np.log(f / min_log_hz) / logstep if f >= min_log_hz else mels
        log_t = f >= min_log_hz
        mels = np.where(log_t, min_log_mel + np.log(np.maximum(f, 1e-9) / min_log_hz) / logstep, mels)
        return mels
    def mel_to_hz(m):
        m = np.asarray(m, dtype=np.float64)
        f_sp = 200.0 / 3
        freqs = f_sp * m
        min_log_hz = 1000.0
        min_log_mel = min_log_hz / f_sp
        logstep = np.log(6.4) / 27.0
        log_t = m >= min_log_mel
        freqs = np.where(log_t, min_log_hz * np.exp(logstep * (m - min_log_mel)), freqs)
        return freqs
    fmax = sr / 2
    n_freqs = 1 + n_fft // 2
    fftfreqs = np.linspace(0, sr / 2, n_freqs)
    mel_pts = mel_to_hz(np.linspace(hz_to_mel(0.0), hz_to_mel(fmax), n_mels + 2))
    fdiff = np.diff(mel_pts)
    ramps = mel_pts[:, None] - fftfreqs[None, :]
    weights = np.zeros((n_mels, n_freqs))
    for i in range(n_mels):
        lower = -ramps[i] / fdiff[i]
        upper = ramps[i + 2] / fdiff[i + 1]
        weights[i] = np.maximum(0, np.minimum(lower, upper))
    enorm = 2.0 / (mel_pts[2:n_mels + 2] - mel_pts[:n_mels])
    weights *= enorm[:, None]
    return weights.astype(np.float32)

MELW = mel_filters()
N_FFT, HOP = 400, 160
WINDOW = np.hanning(N_FFT + 1)[:-1].astype(np.float32)  # periodic hann like torch

def log_mel(audio):
    # audio: float32, already padded/trimmed to 30 s (480000)
    pad = N_FFT // 2
    x = np.pad(audio, (pad, pad), mode='reflect')
    n_frames = 1 + (len(x) - N_FFT) // HOP
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n_frames)[:, None]
    frames = x[idx] * WINDOW[None, :]
    spec = np.fft.rfft(frames, axis=1)
    mag = (np.abs(spec) ** 2)[:-1, :]  # drop last frame like whisper
    mel = MELW @ mag.T.astype(np.float32)  # (n_mels, T)
    log_spec = np.log10(np.maximum(mel, 1e-10))
    log_spec = np.maximum(log_spec, log_spec.max() - 8.0)
    log_spec = (log_spec + 4.0) / 4.0
    return log_spec.astype(np.float32)

# ---------------- tokens ----------------
def load_tokens(path):
    id2bytes = {}
    with open(path, 'rb') as f:
        for line in f:
            parts = line.rstrip(b'\n').split(b' ')
            if len(parts) != 2:
                continue
            id2bytes[int(parts[1])] = base64.b64decode(parts[0])
    return id2bytes

# ---------------- VAD (energy based) ----------------
def segment_audio(audio, sr=16000, max_len=24.0, min_sil=0.35):
    frame = int(0.02 * sr)
    n = len(audio) // frame
    rms = np.sqrt((audio[:n * frame].reshape(n, frame) ** 2).mean(axis=1))
    thr = max(np.percentile(rms, 20) * 2.0, 1e-3)
    sil = rms < thr
    # silence runs
    runs = []
    i = 0
    while i < n:
        if sil[i]:
            j = i
            while j < n and sil[j]:
                j += 1
            if (j - i) * 0.02 >= min_sil:
                runs.append((i * frame, j * frame))
            i = j
        else:
            i += 1
    # candidate split points: middle of silence runs
    splits = [ (a + b) // 2 for a, b in runs ]
    segs = []
    start = 0
    total = len(audio)
    # greedy: extend until exceeding max_len, cut at the last split before limit
    last_split = None
    for sp in splits + [total]:
        if (sp - start) / sr > max_len:
            cut = last_split if last_split is not None and last_split > start else start + int(max_len * sr)
            segs.append((start, cut))
            start = cut
            # handle the case where even the next split is too far
            while (sp - start) / sr > max_len:
                segs.append((start, start + int(max_len * sr)))
                start = start + int(max_len * sr)
        last_split = sp
    if total - start > sr * 0.3:
        segs.append((start, total))
    # merge very short segments into the next
    merged = []
    for s, e in segs:
        if merged and (e - merged[-1][0]) / sr <= max_len and (merged[-1][1] - merged[-1][0]) / sr < 4.0:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    return merged

# ---------------- model ----------------
so = ort.SessionOptions()
so.intra_op_num_threads = 2
so.inter_op_num_threads = 1
enc = ort.InferenceSession(os.path.join(MODEL_DIR, 'turbo-encoder.int8.onnx'), so, providers=['CPUExecutionProvider'])
dec = ort.InferenceSession(os.path.join(MODEL_DIR, 'turbo-decoder.int8.onnx'), so, providers=['CPUExecutionProvider'])
meta = enc.get_modelmeta().custom_metadata_map
SOT = int(meta['sot']); EOT = int(meta['eot']); NO_TS = int(meta['no_timestamps'])
TRANSCRIBE = int(meta['transcribe']); N_TEXT_CTX = int(meta['n_text_ctx'])
N_LAYER = int(meta['n_text_layer']); N_STATE = int(meta['n_text_state'])
lang_tokens = [int(x) for x in meta['all_language_tokens'].split(',')]
lang_codes = meta['all_language_codes'].split(',')
LANG_TOK = lang_tokens[lang_codes.index(LANG)]
non_speech = set(int(x) for x in meta['non_speech_tokens'].split(','))
BLANK = int(meta['blank_id'])
id2bytes = load_tokens(os.path.join(MODEL_DIR, 'turbo-tokens.txt'))
print('lang token', LANG_TOK, 'sot', SOT, 'eot', EOT, flush=True)

def decode_segment(audio_seg):
    a = np.zeros(480000, dtype=np.float32)
    a[:min(len(audio_seg), 480000)] = audio_seg[:480000]
    mel = log_mel(a)[None]  # (1,128,3000)
    ck, cv = enc.run(None, {'mel': mel})
    kcache = np.zeros((N_LAYER, 1, N_TEXT_CTX, N_STATE), dtype=np.float32)
    vcache = np.zeros((N_LAYER, 1, N_TEXT_CTX, N_STATE), dtype=np.float32)
    tokens = np.array([[SOT, LANG_TOK, TRANSCRIBE, NO_TS]], dtype=np.int64)
    offset = np.array([0], dtype=np.int64)
    out_ids = []
    n_prev = 0
    suppress = sorted(non_speech | {NO_TS, SOT, TRANSCRIBE, int(meta['translate'])} | set(lang_tokens))
    suppress = np.array(suppress)
    max_new = 400
    for step in range(max_new):
        logits, kcache, vcache = dec.run(None, {
            'tokens': tokens, 'in_n_layer_self_k_cache': kcache, 'in_n_layer_self_v_cache': vcache,
            'n_layer_cross_k': ck, 'n_layer_cross_v': cv, 'offset': offset})
        lg = logits[0, -1].copy()
        lg[suppress] = -np.inf
        lg[EOT + 1:] = -np.inf  # timestamps etc.
        if step == 0:
            lg[BLANK] = -np.inf
        tid = int(np.argmax(lg))
        if tid == EOT:
            break
        out_ids.append(tid)
        # repetition guard
        if len(out_ids) >= 12 and len(set(out_ids[-12:])) <= 2:
            break
        n_prev += tokens.shape[1]
        offset = np.array([n_prev], dtype=np.int64)
        tokens = np.array([[tid]], dtype=np.int64)
    b = b''.join(id2bytes.get(t, b'') for t in out_ids)
    return b.decode('utf-8', errors='replace').strip(), out_ids

audio = read_wav(WAV)
segs = segment_audio(audio, max_len=MAX_CHUNK)
print('segments:', len(segs), [round((e - s) / 16000, 1) for s, e in segs][:10], flush=True)
results = []
t0 = time.time()
with open(OUT, 'w', encoding='utf-8') as f:
    for k, (s, e) in enumerate(segs):
        text, ids = decode_segment(audio[s:e])
        rec = {'start': s / 16000, 'end': e / 16000, 'text': text}
        results.append(rec)
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
        f.flush()
        print(f"[{k+1}/{len(segs)}] {s/16000:7.1f}-{e/16000:7.1f} ({time.time()-t0:5.0f}s) {text}", flush=True)
print('done', flush=True)
