---
name: lecture-video-notes
description: Turn recorded lecture videos (a professor writing on the lecture-note PDF on an iPad, e.g. GoodNotes screen recordings) plus the lecture-note PDF into an annotated PDF. The professor's handwriting is copied onto the pages in place, and handwritten-style margin notes record every exam-relevant remark with its video timestamp. Also writes plain-text transcripts. Use when the user gives lecture videos and a lecture PDF and asks for an annotated/필기 PDF, 강의 필기 정리, lecture transcripts, or to continue the notes with the next lectures. Also use it to set up this skill's environment on a new computer (환경 설정).
---

# Lecture videos → annotated lecture-note PDF

Pipeline (all scripts in `scripts/`, all read one job file `lecnotes_job.json` in the course folder):

```
videos ─┬─ transcribe.py ───────────────► work/KEY.jsonl ─► (you) notes/notes_KEY.py ─┐
        └─ extract_views.py ─► align.py ─► rescue_align.py ─► overlay.py ─► clean_specks.py ─┴─► build.py ─► annotated PDF
                                                                     make_transcripts.py ─► transcript txt
```
Shorthand: `SC` = this skill's `scripts` folder. `PY` = the skill's Python: `$LECNOTES_VENV` if set, else
`~/.lecnotes/venv` (`Scripts\python.exe` on Windows, `bin/python` elsewhere). Set `PYTHONIOENCODING=utf-8` on Windows.
Run every script from the course folder, or set `LECNOTES_JOB` to the job file.

## 0. Environment (once per machine)
Check this before anything else, on every machine. The machine is ready when `PY` exists and the last line of `PY SC/doctor.py` is
`setup ok`. Otherwise set it up (the user may be on a fresh computer that has only Claude Code and this skill folder):
1. **uv.** The setup scripts look for it on PATH, then in `~/.local/bin` and `~/.cargo/bin`, where the installer puts it.
   A shell opened before the install does not see it on PATH, so there is no need to restart. If `uv` is in none of these places,
   tell the user and ask before installing it:
   `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"` (Windows) or
   `curl -LsSf https://astral.sh/uv/install.sh | sh` (macOS/Linux).
2. **Setup.** Run it in the background from this skill's folder: `powershell -ExecutionPolicy Bypass -File setup.ps1` (Windows) or
   `bash setup.sh` (macOS/Linux). It installs a uv-managed Python 3.12 in `PY`'s venv, the packages (~150 MB), cuBLAS + cuDNN when
   `nvidia-smi` exists (~1.3 GB more), and the fonts, and then runs `doctor.py`. On a fast connection this takes a few minutes.
   It succeeded if it exits with code 0 and the last doctor line is `setup ok`. Re-running it is safe: finished steps are skipped.
   If Windows PowerShell 5.1 redirects the output, it shows uv's progress messages on stderr as `NativeCommandError`. That is harmless.
3. **Speech model.** Setup does not download the model (`mobiuslabsgmbh/faster-whisper-large-v3-turbo`, 1.6 GB). The first
   `transcribe.py --probe-only` (section 2) downloads it into the Hugging Face cache, so the first probe takes longer.

**Never use an Anaconda/conda Python**: its old msvcp140.dll makes CTranslate2 crash on Windows (access violation 0xC0000005).
No ffmpeg or poppler is needed. PyAV decodes video and audio, and pypdfium2 renders and reads the PDF.

## 1. Set up the job
- Ask only for what you cannot find: the course folder, the lecture PDF, which videos, and the output name. Look first.
  Recording dates: read the iPad status bar in the first frame of each video (`views_KEY/` first jpg, top-left).
- Write `<course_dir>/lecnotes_job.json` (see `references/job_example.json`, fields in `references/job_fields.md`):
  `course_dir`, `lecture_pdf` (the clean PDF = alignment target), `out_pdf`, `videos` (key/file/date in lecture order),
  `work_dir`, `min_page`, `language` (Whisper code, default `ko`), optional `asr_fixes` and `keywords`.
- **Continuing an earlier run:** keep the same `work_dir`. Its `overlay/`, `notes/`, and `align*.json` are the saved state.
  List only the NEW videos and set `min_page` to the page where they start. That page is in the previous run's last
  "※ Lecture X 영상은 여기…에서 끝남" box. Pages before `min_page` are untouched, and later pages continue from their existing ink.
  The first new notes file's `patch(N)` updates the page-1 guide title and removes the old end box.

## 2. Transcription: local or cloud
1. `PY SC/doctor.py`: GPU (nvidia-smi / CUDA devices), CPU threads, RAM.
2. `PY -X faulthandler SC/transcribe.py --probe-only`. It finds a working CTranslate2 setting in crash-isolated subprocesses
   (CUDA float16 first if a GPU exists, then CPU int8) and stores it with `probe_speed_x` in `work/ct2_config.json`.
3. Expected time ≈ total audio minutes / (1.5 × probe_speed_x), because the batched run is about 1.5× the probe.
   Reference: a 2024 laptop CPU (Intel Core Ultra 7 155H, int8, 16 threads, batch 4) does **4.2× real time** (222 min in 53 min).
   - Several times faster than real time: run locally in the background.
   - No setting works, or slower than about 1×: tell the user the estimate, and offer a cloud machine or letting it run anyway.
     On a Linux VM without a usable CTranslate2, `scripts/cloud/whisper_onnx.py` (sherpa-onnx whisper-turbo int8 ONNX export +
     own greedy decoder that merges byte-level BPE correctly) ran at about 1/3 real time on 2 vCPU. It writes the same jsonl.
4. Full run: `PY -X faulthandler SC/transcribe.py` (every job video without `KEY.jsonl.done`). Progress is in
   `work/transcribe_status.txt`, and the log is in `work/transcribe_log.txt`. Model: `mobiuslabsgmbh/faster-whisper-large-v3-turbo`.
   Already handled: a single long `BatchedInferencePipeline` call overflows the stack on Windows, so the audio goes in ~10-min chunks
   cut at quiet points. faster-whisper's decoder clashes with new PyAV, so the script has its own `load_audio`.

## 3. Handwriting overlay (run while transcription is going)
```
PY SC/extract_views.py            # keyframes only (~30 s per 50-min video) -> views_KEY/v_<kf>_<sec>s.jpg
PY SC/align.py                    # renders pages at 200 dpi, SIFT/RANSAC + template fallback (resumable)
PY SC/rescue_align.py             # retries failures: masked score, 400 dpi, raw gray, frame-to-frame chaining; 2nd page of straddling views
PY SC/overlay.py && PY SC/clean_specks.py <pages...>
```
- Check the last lines of `rescue_align.py` (`ok n / n`). Leftover failures are usually views with no printed text.
- Look at `work/overlay/debug_page{p}.jpg` for every touched page: ink in place, nothing duplicated or shifted.
- GoodNotes **laser pointer** strokes (glowing, fading) are dropped automatically by their soft glow. If odd glowing lines survive,
  open the source frame and check the toolbar (laser mode shows only "• ~" instead of the color palette).
- Frames are assumed to be iPad screen recordings: app chrome = top `ui_top_frac` (0.1547) of the frame. Adjust for other apps.

## 4. Notes (your work: the part the user cares most about)
Follow `references/notes_guide.md`. For each video: read the whole transcript, run the keyword pass, check the board words on the
debug images and frames, then write `work/notes/notes_KEY.py`. Videos are independent. With many videos, one subagent per video
(or per pair) drafts them in parallel as each transcript finishes. Give each one the guide, two finished notes files as style examples,
the key, date, length, its pages (from `align_rescue.json`), the course's exam rules, and permission to run a scratch build plus
`render_check.py` to fix its own placement. Then review every draft yourself: grep the transcript for exam words and confirm each
quoted remark word for word.
- Dense ink: use memo pages (`'P+'` keys, see the guide). Each memo page shifts the PDF index of later pages by one, and
  `render_check.py` takes PDF indices.

## 5. Build and review
```
PY SC/build.py --check-only
PY SC/build.py --out <scratch>/trial.pdf          # fix every "!!" line (a note did not fit)
PY SC/render_check.py <scratch>/r.jpg <scratch>/trial.pdf 12 13 14 15   # look at every touched page
PY SC/build.py                                    # final -> out_pdf
PY SC/make_transcripts.py                         # -> transcript_dir/<video name> 전사본.txt
```
Add mishearings you noticed to the job's `asr_fixes`.

## 6. Report and clean up
- Report briefly: what was produced, each video's exam remarks (from the SUMMARY strings), anything marked "※ 확인 필요",
  and the transcription speed.
- **Ask before deleting** anything the user did not explicitly ask to delete (videos are permanent losses). Even with permission,
  delete only after the user has the final PDF.
- Keep `work/overlay/`, `work/notes/`, `work/align*.json`, `work/*.jsonl` and `lecnotes_job.json` for the next run (~20–40 MB).
  Safe to delete after a run: `work/views_*`, `work/render/`, `work/*.flac`, `work/overlay_s/`.
- These are the student's course materials: never upload them anywhere, and never copy them into this skill's folder.
