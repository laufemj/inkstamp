# Writing the margin notes (notes_{KEY}.py)

The student wants two things on the lecture PDF:
1. the professor's handwriting copied in place (done automatically by align → overlay), and
2. green handwritten-style notes in the right margin with **every** exam-relevant remark, each with its video timestamp.

The most important part is remarks like "시험에 나온다 / 안 나온다 / 나올 수 있다", "외워라", "꼭 풀어 봐라", "각자 해 봐라",
"읽어 보세요 / 안 읽어도 된다 / 생략 / 스킵", "중요하다", "몰라도 된다", and homework, attendance, or class notices.
Record them exactly, with quotes and time.

## Workflow per video
1. Read the **whole** transcript: `python scripts/show_asr.py KEY` (pipe to a file if long, then Read it).
2. Keyword pass: `python scripts/show_asr.py KEY --grep`. Judge every hit in context. Professors also say exam
   things without keywords, so step 1 is not optional.
3. Look at the ink: `work/overlay/debug_page{p}.jpg` (half-size composite) for the pages the video covered
   (`align_rescue.json` → pages per video). Board words like "각자!", "시험문제!", "생략", "Skip!", "외울 것",
   "수정", big X over a section, and "읽기를 권한다" must be reflected in the notes. When the board and the speech
   differ, or the printed PDF text contradicts what was said, write both and mark "※ 확인 필요".
4. When something is ambiguous ("얘", "밑에 것"), open the frame at that time (`work/views_KEY/v_*_SSSSSs.jpg`) and check.
5. Line positions: `python scripts/layout.py <page> [regex]` → y (200-dpi px) of each text line = the note anchor.
   Formula-heavy pages give noisy output. Then estimate from the debug image instead (debug px × 2 = page px).

## File format — work/notes/notes_{KEY}.py
```python
# -*- coding: utf-8 -*-
NOTES = {
    12: [
        dict(y=150, size=13, box=True, title="★ Lecture 4-1 (9/9, 22분) 핵심 & 시험 관련 멘트",
             text="① ...\n② ...\n※ 시험 범위 제외 언급: ..."),
        dict(y=955, size=12.5, text="(L4-1 0:30~3:10) ..."),
    ],
}
SUMMARY = """bullets of the exam-relevant remarks with times, pages covered (for the final report)"""

def patch(N):   # optional: edit notes merged from EARLIER files (runs before this file's NOTES are added)
    N[1][0] = dict(N[1][0], title='✓ 필기 안내 — Lecture 1-1 ~ 9-3 영상 (8/31 ~ 10/4)')
    N[36] = [n for n in N.get(36, []) if not n['text'].startswith('※ Lecture 7-3')]
```
- `y` = PDF line the note explains. The placer moves it to the nearest free spot. It avoids the professor's ink, the PDF's own text, and
  other notes. It tries the right margin first (x=1535, width 730), then narrower margin columns, then blank body areas.
  Use `x`/`width` only in special cases.
- size: normal 12–12.5, box 13. Hats: `"\\h{r}"`. Superscript `^{2}`, subscript `_{i}`. `★` is drawn red automatically. Quote speech with “ ”.
- Characters the fonts lack: ℝ (write R), ⟺ (⇔), ⟂ (⊥), ∘, emoji. Greek, ∂ ∇ ⇒ → are fine. `build.py --check-only` lists bad chars.
- Times: first note of a range "(L4-1 12:30~14:05)", later ones on the same page "(13:10)".
- Length: ≤ ~220 chars per note (≤ 5 lines), box ≤ ~600 chars (①~⑥ + ※). ≤ 5 notes per page per video.
  Don't repeat definitions printed in the PDF. Write what the professor *added*: intuition, emphasis, warnings, exam
  and memorize remarks, corrections of typos in the notes, and the meaning of board drawings.
- Exactly **one box per video**, on the page where the video starts. Title "★ Lecture {n} ({m/d}, {min}분) 핵심 & 시험 관련 멘트".
  The last item "※ ..." states whether anything was excluded from the exam scope, or "범위 제외 언급 없음".
- End of each video: append "— L4-1 끝 (24:10)" to its last note.
- Last video of the run: add a box "※ Lecture X (date) 영상은 여기(…)에서 끝남 — {next page/section}부터는 다음 영상"
  at the end position. The next run removes it with `patch()`.
- **Margins full of the professor's ink** (the build prints `!!`, or the render shows a note on top of ink): keep one short pointer
  note on the page ("★ … — 자세한 메모는 다음 쪽(42쪽 메모)") and put the box and the detailed notes under the key `'42+'`.
  That key becomes a blank memo page inserted right after page 42, with notes stacked full-width in the order of their `y`
  (use 230, 231, …). Prefer this to squeezing notes onto unrelated pages. A nearly blank page right before (e.g. a chapter's last page)
  may also hold the box, labelled with its page range.
- Pages no video covered: add a small box saying so (e.g. "※ 18쪽은 어느 영상에서도 다루지 않음").
- Transcripts are ASR output and contain mishearings ("저평면"=접평면, "공면"=곡면, "뺑갈/뿌엥까레"=푸앵카레).
  Fix them from context and the PDF, and never invent anything. If unsure, leave it out or mark it.

## Checking
`python scripts/build.py --check-only` → per file: pages, note count, unsupported characters.
`python scripts/build.py --out <scratch>.pdf` then look for lines with `!!` (a note did not fit, so shorten it or move it to
the neighbouring page with a "(13쪽 아래 …)" prefix). Render pages with `python scripts/render_check.py out.jpg <pdf> 12 13` and look.
