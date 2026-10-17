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
| `hotwords` | no | course terms as spoken, comma-separated, passed to Whisper as hint phrases (about 25 terms from the PDF's headings and key words, e.g. `"푸리에 급수, 푸리에 변환, 파스발 항등식, 체비쇼프 다항식, Kreyszig, 공수1"`). It cut known term mishearings from 52 to 11 on a 55-min lecture and from 12 to 3 on a 19-min one, at the same speed. Set it before transcribing |
| `asr_fixes` | no | `[["misheard", "correct"], ...]` applied when writing transcripts |
| `keywords` | no | regex for `show_asr.py --grep` (default: Korean exam/notice words) |
| `ui_top_frac` | no | app chrome height / frame height (default 0.1547 = GoodNotes on iPad) |
| `overlay_base` | no | `"existing"` (default): pages continue from existing ink. `"empty"`: rebuild from blank |
| `note_column` | no | `[x, width]` of the note column in 200-dpi px. Default: right of the printed text (document median) |
| `extend_margin` | no | `true` (default): widen pages whose right margin is too narrow for notes |
| `fonts_dir`, `pen_font`, `fallback_font` | no | other fonts (default: NanumPenScript + NotoSansKR in the skill's `fonts/`) |
