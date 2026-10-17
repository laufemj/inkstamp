# `lecnotes_job.json` fields

Relative paths are relative to `course_dir`.

| field | required | meaning |
|---|---|---|
| `course_dir` | yes | absolute path of the course folder |
| `lecture_pdf` | yes | the clean lecture-note PDF. Frames are aligned to it, and it is the base of the output |
| `out_pdf` | yes | annotated PDF to write |
| `videos` | yes | `[{"key": "L4-1", "file": "...mp4", "date": "YYYY-MM-DD"}]` in lecture order. List only this run's videos |
| `course_title` | no | heading of the transcript files |
| `transcript_dir` | no | where `<video name> 전사본.txt` go (default `Lecture Video/전사본`) |
| `work_dir` | no | working + state folder (default `_claude_work`). Keep it between runs |
| `min_page` | no | first page this run may change (default 1). Earlier pages keep their ink |
| `language` | no | Whisper language code of the lectures (default `ko`) |
| `asr_fixes` | no | `[["misheard", "correct"], ...]` applied when writing transcripts |
| `keywords` | no | regex for `show_asr.py --grep` (default: Korean exam/notice words) |
| `ui_top_frac` | no | app chrome height / frame height (default 0.1547 = GoodNotes on iPad) |
| `overlay_base` | no | `"existing"` (default): pages continue from existing ink. `"empty"`: rebuild from blank |
| `fonts_dir`, `pen_font`, `fallback_font` | no | other fonts (default: NanumPenScript + NotoSansKR in the skill's `fonts/`) |
