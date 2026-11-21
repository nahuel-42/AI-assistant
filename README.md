# AI Interview Copilot

Windows desktop assistant for job interviews: a floating, always-on-top Tauri window backed by a
local Python service. See [docs/requirements.md](docs/requirements.md) for the full PRD.

**Status: Phase 2 (Audio Intelligence).** Floating window, global hotkeys, local backend, and
session start/pause/stop, plus live transcription of your microphone ("You") and computer audio
("Interviewer"). Every question gets an automatic answer, whoever asks it: the interviewer
(what to say) or you (direct help). The assistant's single purpose is to help you through the interview. Speech-to-text
runs on this PC (faster-whisper); audio is never saved or sent anywhere, only the text.
Screenshots (Phase 3): the 📷 button or Ctrl+Shift+S hides the window for a moment, reads the
text on your screen with the OCR built into Windows (offline, free), saves the text in the
session, adds it to the context (last 3 screenshots) and answers it automatically: coding
problems are solved, errors explained. The image itself is never saved or sent; only the text.

**Listen to** (button in the window, remembered between sessions, switchable mid-session):
*Mic + System* (video calls; mic = "You", computer sound = "Interviewer"), *System only*
(only the call's sound), *Mic only* (in-person interviews or practising aloud: any question the
mic hears gets an answer). In every mode, questions from anyone are answered, and a question
heard twice (mic + call sound) is answered once. Capture follows the Windows default devices, so plugging in a
headset mid-session just works.

**Read aloud:** finished answers are spoken automatically in your headphones with the built-in
Windows voices (Helena for Spanish, Zira for English), only the short "say this" part, not the
bullets. 🔊/🔇 in the title bar turns it on/off (remembered); **■ Stop** appears while it speaks;
**▶ Read aloud** on a card replays it. While it speaks, the app ignores computer sound (and the
mic in *Mic only* mode) so it never answers its own voice; interviewer words said in those
seconds are not transcribed.

**Profile & answer style** (👤 in the title bar, saved locally, used in every answer):
*Profile* holds your CV, projects, target job and notes; the assistant only cites facts written
there. *Answer style* sets how interview answers sound. The default: direct answer first, then
the reasoning and trade-offs, then a real example from the profile, delivered confidently and
constructively. Interviewer questions get one spoken paragraph (read aloud) plus up to 2 extra
points. Notes to you appear in parentheses and are not read aloud.

**Use headphones during interviews.** Especially with read-aloud: through speakers, the
interviewer would hear the spoken answer through your microphone. With speakers, your microphone also hears the interviewer
and their words show up twice (once as "You").

## Prerequisites (Windows)

| Tool | Why | Install |
|---|---|---|
| Python 3.11+ | backend | python.org |
| Node 20+ | frontend | nodejs.org |
| Rust (stable, MSVC) | Tauri shell | https://rustup.rs |
| VS Build Tools: "Desktop development with C++" | Rust linker on Windows | https://aka.ms/vs/17/release/vs_BuildTools.exe |
| WebView2 | Tauri webview | preinstalled on Windows 11 |

## Setup

```powershell
# Backend
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest            # 40 tests

# AI: with no API key set, suggestions use your Claude Pro/Max plan through Claude Code
# (run `claude` once and log in). To use the pay-per-use API instead:
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# Desktop
cd ..\apps\desktop
npm install
npm run tauri dev                          # starts Vite + the Tauri window + the backend
```

The Tauri shell starts the backend from `backend/.venv` on port 8765 and stops it on exit.
To run the backend yourself (e.g. with `--reload`), set `COPILOT_SKIP_BACKEND=1` and run:

```powershell
cd backend; .venv\Scripts\python -m uvicorn app.main:app --port 8765 --reload
```

### Desktop launcher

`npx tauri build --no-bundle` (in `apps/desktop`) produces
`src-tauri/target/release/ai-interview-copilot.exe`; the **AI Interview Copilot** shortcut on the
Desktop points to it. Re-run the build after code changes so the shortcut picks them up. The exe
finds `backend/` by its absolute path at build time, so it only works from this checkout.
With no `ANTHROPIC_API_KEY` set, the app uses your Claude subscription through Claude Code.
The window shows which one is answering and, on a subscription, how much of the 5-hour limit is used.

You can also run `npm run dev` and open http://localhost:1420 in a browser for quick UI work
(global hotkeys and window controls are no-ops outside Tauri).

## Shortcuts

| Shortcut | Action |
|---|---|
| Ctrl+Shift+Space | Start / stop session |
| Ctrl+Shift+S | Read the screen's text and get help with it |
| Ctrl+Shift+Q | Answer now: answer what was just said, even if no question was detected (also the 💬 button) |
| Ctrl+Shift+A | Show / hide window |
| Ctrl+Shift+M | Switch Visible ↔ Private mode |

Override them via the `copilot.shortcuts` localStorage key (a settings UI comes in Phase 5).

## Configuration (backend env vars)

| Variable | Default | |
|---|---|---|
| `COPILOT_AI_PROVIDER` | `auto` | `auto` = API if `ANTHROPIC_API_KEY` is set, else your Claude subscription via Claude Code; `claude` = API; `claude-code` = subscription; `echo` = offline stub |
| `COPILOT_AI_MODEL` | `claude-opus-5-5` | |
| `COPILOT_AI_EFFORT` | `low` | `low`…`max`; low keeps suggestion latency down |
| `COPILOT_DATA_DIR` | `%LOCALAPPDATA%\AIInterviewCopilot` | SQLite DB and speech models |
| `COPILOT_AUDIO_ENABLED` | `true` | `false` = no capture at all |
| `COPILOT_STT_MODEL` | `base` | `tiny`/`base`/`small`…; `base` ≈ 6× real time on a 4-core laptop |
| `COPILOT_STT_LANGUAGE` | (auto) | `en` or `es` skips language detection: faster, fewer mistakes |
| `COPILOT_AUTO_SUGGEST` | `true` | answer detected interviewer questions automatically |
| `COPILOT_OCR_LANGUAGE` | (auto) | Windows OCR language, e.g. `en-US`; auto prefers Spanish, which also reads English |
| `COPILOT_TTS_ENABLED` | `true` | `false` removes read-aloud entirely (the 🔊 toggle is for day-to-day use) |
| `COPILOT_PORT` | `8765` | if changed, set `VITE_BACKEND_URL` for the frontend |

See [docs/architecture.md](docs/architecture.md) and [docs/api.md](docs/api.md).
