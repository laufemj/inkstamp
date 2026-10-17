# lecture-video-notes

강의 녹화 영상과 강의노트 PDF로 **필기 PDF**를 만들어 주는 [Claude Code](https://claude.com/claude-code) 스킬입니다.

교수님이 iPad(GoodNotes 등)에서 강의노트 PDF 위에 필기하며 강의한 화면 녹화가 대상입니다.

- **교수님 필기를 원래 자리에 그대로** 옮깁니다. 영상 프레임을 PDF 쪽에 정합해서 잉크만 오려 붙이고, 지운 필기와 레이저 포인터는 빠집니다.
- **시험 관련 멘트를 빠짐없이** 영상 시각과 함께 손글씨체 메모로 오른쪽 여백에 적습니다. 예: "시험에 나온다/안 나온다", "외워라", "각자 해 봐라", "생략", 공지, 노트 정정.
  여백이 필기로 꽉 찬 쪽은 바로 뒤에 메모 쪽을 끼워 넣습니다.
- 영상마다 **전사본 txt**(시각 포함)도 만듭니다.
- 다음 강의가 쌓이면 **이어서** 같은 PDF를 계속 만들어 갑니다.

> English summary at the bottom.

## 필요한 것
- Claude Code
- Windows, macOS 또는 Linux. 개발과 실사용은 Windows 11 노트북에서 했습니다.
- [uv](https://docs.astral.sh/uv/). 설치 스크립트가 독립 Python 3.12 환경을 만듭니다. Anaconda Python 은 쓰지 않습니다.
- 디스크 약 3 GB: 음성인식 모델 1.6 GB, 패키지, 폰트

## 설치
```bash
git clone https://github.com/<OWNER>/lecture-video-notes ~/.claude/skills/lecture-video-notes
cd ~/.claude/skills/lecture-video-notes
bash setup.sh                                          # macOS / Linux
powershell -ExecutionPolicy Bypass -File setup.ps1     # Windows
```
설치 스크립트는 `~/.lecnotes/venv` 에 환경을 만들고 패키지와 폰트를 내려받은 뒤 환경 점검 결과를 보여 줍니다.
환경 위치는 `LECNOTES_VENV` 로 바꿀 수 있습니다.

## 사용법
강의 폴더(강의노트 PDF와 `Lecture Video/` 영상이 있는 곳)에서 Claude Code 를 열고:
```
/lecture-video-notes
```
또는 "이 강의 영상들로 필기 PDF 만들어 줘", "새 영상 8-1~9-3 이어서 처리해 줘"처럼 말하면 됩니다.
Claude 가 강의 폴더에 `lecnotes_job.json` 을 만들고 다음 순서로 진행합니다.

1. **음성인식**: faster-whisper large-v3-turbo. 컴퓨터를 점검해서 GPU, CPU, 클라우드 중 어디서 돌릴지 정합니다.
2. **잉크 추출**: 화면이 바뀌는 프레임을 골라 PDF 쪽에 정합하고 잉크를 오려 냅니다. 음성인식과 동시에 진행합니다.
3. **메모 작성**: Claude 가 전사본 전체와 판서를 읽고 시험 관련 멘트를 빠짐없이 정리합니다. 영상이 많으면 병렬로 작성합니다.
4. **조판·검수**: 메모를 필기와 본문을 피해 배치하고, 쪽마다 렌더링해서 확인합니다.

전사 속도 참고: 노트북 CPU(Intel Core Ultra 7 155H)에서 **실시간의 약 4배**로, 3시간 42분 분량이 53분 걸렸습니다.

## 한계
- iPad 화면 녹화처럼 **강의노트 PDF 위에 필기하는 강의**를 전제로 합니다. 칠판 촬영이나 슬라이드 강의는 대상이 아닙니다.
- 메모 문체, 폰트(나눔펜), 키워드 검색은 **한국어 강의**에 맞춰져 있습니다. `language`, `keywords`, 폰트 설정으로 다른 언어에도 쓸 수 있지만 다듬어지지 않았습니다.
- 음성인식은 틀릴 수 있습니다. 메모는 Claude 가 정리한 것이라, 중요한 멘트는 표시된 시각으로 영상에서 다시 확인하세요.
  확신이 없는 부분은 "※ 확인 필요"로 표시됩니다.

## 개인정보와 저작권
- 음성인식, 프레임 정합, PDF 조판은 **내 컴퓨터에서** 돌아갑니다. 단, 메모를 쓰는 단계에서 Claude 가 전사본, 프레임 이미지, 강의노트 일부를 읽으므로 이 내용은 Claude Code 대화로 Anthropic 에 전송됩니다.
  학교나 강의의 자료 이용 규정을 확인하세요.
- 강의 영상, 강의노트, 만든 필기 PDF는 교수님의 저작물을 포함합니다. **개인 학습용으로만** 쓰고 공유하지 마세요.
  이 저장소에는 어떤 강의 자료도 들어 있지 않습니다.

## 구성
```
SKILL.md                     Claude 가 따르는 작업 절차
references/notes_guide.md    메모 작성 규칙 (형식, 배치, 메모 쪽)
references/job_fields.md     lecnotes_job.json 항목
scripts/                     transcribe, extract_views, align, rescue_align, overlay, build ...
setup.ps1 / setup.sh         환경 설치
```

## 라이선스
- 코드: MIT ([LICENSE](LICENSE))
- 폰트: [Nanum Pen Script](https://fonts.google.com/specimen/Nanum+Pen+Script), [Noto Sans KR](https://fonts.google.com/noto/specimen/Noto+Sans+KR). SIL Open Font License 1.1 이며, 설치 시 라이선스 파일과 함께 따로 내려받습니다.
- 음성인식 모델: Hugging Face `mobiuslabsgmbh/faster-whisper-large-v3-turbo`. 각 모델의 라이선스를 따릅니다.

---

## English summary
A Claude Code skill that turns iPad screen recordings of a lecture into an annotated copy of the lecture-note PDF. The professor writes on that same PDF during the lecture.

- **Handwriting:** the professor's ink is copied onto each page in place. Frames are aligned to the PDF pages, and erased ink and laser-pointer strokes are dropped.
- **Exam remarks:** every exam-relevant remark is written in the margin with its video timestamp, in a handwritten-style font. When a margin is full, a memo page is inserted after that page.
- **Transcripts:** each video also gets a timestamped transcript.

Install by cloning into `~/.claude/skills/lecture-video-notes` and running `setup.sh` or `setup.ps1`, which needs `uv`. Then run `/lecture-video-notes` in the course folder.

Speech recognition, alignment and typesetting run locally. Writing the notes means Claude reads the transcripts and frames. The output is tuned for Korean lectures. Use it for personal study only, and don't redistribute lecture material.
