# AI Interview Copilot — Product Requirements & Technical Definition (v1.0)

> Source PRD, kept here as the reference for every phase. Summary of what binds the implementation:

## Principles
Continuous audio during an active session · screenshots **only** by manual hotkey · context
awareness (personal / interview / immediate layers) · low latency · user control (start, pause,
stop) · local-first · modular, replaceable providers.

## Modes
- **Visible Mode:** full interface, live transcript, suggestions, screenshot previews, history.
- **Private Mode:** compact, keyboard-first, simplified suggestions. This is not covert capture:
  capture indicators and controls stay accessible.
- Switching modes never restarts the session or interrupts audio.

## Functional requirements
| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-01 | Windows desktop application | 1 | done (Tauri shell, needs Rust to build) |
| FR-02 | Global keyboard shortcuts | 1 | done |
| FR-03 | Auto-capture microphone on session start | 2 | done|
| FR-04 | Auto-capture system audio (WASAPI loopback) | 2 | done|
| FR-05 | Incremental speech-to-text | 2 | done (on-device faster-whisper, per utterance)|
| FR-06 | Detect questions / conversational events | 2 | done (heuristic, EN/ES)|
| FR-07 | Screenshots only via manual hotkey | 3 | done (button + Ctrl+Shift+S, never automatic) |
| FR-08 | Multimodal screenshot analysis | 3 | done via local Windows OCR → text → Claude (image never sent) |
| FR-09 | Personal, interview, immediate context | 1–4 | interview + immediate (transcript) layers active |
| FR-10 | Concise, natural suggestions | 1/4 | done for typed questions |
| FR-11 | Floating, always-on-top window | 1 | done |
| FR-12 | Visible and Private modes | 1/5 | basic layouts done |
| FR-13 | Switch modes without restarting the session | 1 | done |
| FR-14 | Configurable shortcuts | 5 | storage done; UI pending |
| FR-15 | Local session storage and history | 1/5 | storage + API done; UI pending |
| FR-16 | Upload and index personal documents | 4 | |
| FR-17 | Pause / stop capture at any time | 1/2 | done (pause closes the devices) |
| FR-18 | Configure AI provider and model | 1/5 | env vars done; UI pending |

## Roadmap
1. Desktop foundation: Tauri + React, floating window, global hotkeys, local backend, session start/stop.
2. Audio intelligence: mic + system audio, incremental transcription, question detection.
3. Screenshot intelligence: manual capture, multimodal analysis, context merge.
4. AI assistant: Claude integration, contextual answers, personal knowledge retrieval, latency.
5. UX: mode polish, settings, customizable hotkeys, session history, stability.

## Security & privacy
Audio only during an explicitly started session · screenshots only after explicit action · clear
indicators · immediate pause/stop · secure credential storage · minimal transmission of
personal data · session deletion · respect consent requirements and interview platform policies.

## Acceptance criteria (first usable version)
App launches · session starts via hotkey · mic and system audio capture automatically ·
incremental transcripts · relevant questions identified · manual screenshot capture · Claude
analyzes screenshots and conversation · suggestions in the floating window · mode switch keeps
context · stop session and review history.

Future: Vercel deployment, web dashboard, cloud sync, multi-provider AI, other OSes.
