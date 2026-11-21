# Architecture

```
┌──────────── Tauri 2 shell (Rust) ────────────┐        ┌────── Python backend (FastAPI) ──────┐
│ frameless, transparent, always-on-top window │        │ api/routes.py    HTTP + /ws          │
│ global-shortcut plugin                       │  HTTP  │ services/session_manager.py          │
│ spawns + kills the backend process           │ ─────▶ │   one live session, InterviewContext │
│ ┌──────── React + TS + Tailwind ───────────┐ │   WS   │ services/ai/   provider abstraction  │
│ │ stores/app.ts    (zustand: session,mode) │ │ ◀───── │   claude.py (streaming) / echo stub  │
│ │ hooks/useGlobalShortcuts.ts              │ │        │ services/context/manager.py          │
│ │ features/assistant  Visible/Private view │ │        │ repositories/ → SQLite (models/db.py)│
│ └──────────────────────────────────────────┘ │        └──────────────────────────────────────┘
└──────────────────────────────────────────────┘
```

## Key decisions

- **The backend owns the session; the UI only mirrors it.** Every state change goes out as a
  `session.state` event over `/ws`, so hotkeys, buttons, and later a second window stay in sync.
- **Mode is UI-only state.** Visible and Private modes are two layouts over the same store, and
  switching only resizes the window. The backend session and context are never touched (FR-13).
- **Suggestions stream.** `POST /api/assistant/ask` returns `202` with an id right away, then
  `assistant.started` / `assistant.delta` / `assistant.done|error` events carry the text.
- **Providers are swappable.** `AIProvider.stream_answer(system, messages)` is the only contract.
  `ClaudeProvider` uses `claude-opus-5-5` with low effort for latency, plus the server-side refusal
  fallback. `EchoProvider` runs offline for tests.
- **Context layers** (`InterviewContext`): `personal` (Phase 4 retrieval), `history` (Q&A pairs,
  last 10), `recent_transcript` (Phase 2). The system prompt forbids inventing experience.
- **Crash safety.** On startup, sessions left `active` are marked `stopped`. Capture never resumes
  without an explicit user action.

## Audio pipeline (Phase 2)

```
mic (WASAPI)      ─┐  16 kHz mono, 100 ms chunks
speakers loopback ─┤→ UtteranceSegmenter per stream (adaptive energy, cut at 0.8 s pause / 15 s max)
                   └→ queue → one STT worker (faster-whisper base, int8, CPU) → text
                         → SessionManager: save segment, publish transcript.segment,
                           add to InterviewContext.recent_transcript,
                           if interviewer + looks_like_question → automatic suggestion
```

- Speaker = source: microphone is "You", system audio is "Interviewer". No diarization needed.
- Pause and stop close the devices. Raw audio lives in memory until transcribed and is never stored.
- At most one automatic suggestion runs at a time; if more questions arrive meanwhile, only the
  newest is answered next.
- The speech model is loaded from disk without network access; it downloads only the first time.
- `soundcard` must be imported on the startup thread (see `services/audio/sources.py`).

Measured on an i5-1135G7 laptop: model load 0.7 s, a 10 s question transcribes in ~1.2–1.5 s, and
text appears ~2–2.5 s after the speaker stops.

## Where upcoming phases plug in

| Phase | Hook point |
|---|---|
| 3 Screenshots | `screenshot` hotkey in `App.tsx` → capture in Rust → `services/vision` → image block in `build_messages` |
| 4 Assistant | `services/knowledge` populates `InterviewContext.personal`; automatic question detection triggers `ask` |
| 5 UX | settings UI over `features/settings/shortcuts.ts`, session history view over `GET /api/sessions/{id}`, keyring-backed credentials |
