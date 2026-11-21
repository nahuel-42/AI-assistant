# Backend API (http://127.0.0.1:8765)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | `{status, provider, audio, stt_model}` |
| GET | `/api/sessions/current` | live session or `null` |
| POST | `/api/sessions` | `{title?}` → 201; 409 if one is already live |
| POST | `/api/sessions/current/pause` \| `resume` \| `stop` | 409 on invalid transition |
| GET | `/api/sessions` | history, newest first |
| GET | `/api/sessions/{id}` | session + suggestions + transcript |
| DELETE | `/api/sessions/{id}` | 204; 409 if the session is live |
| GET/PUT | `/api/audio/mode` | `{mode: both\|mic\|system}`; applies live, remembered |
| GET/PUT | `/api/tts` | `{read_aloud: bool}` → `{available, read_aloud, speaking}` |
| POST | `/api/tts/stop` | stop speaking now |
| POST | `/api/tts/speak` | `{text}`: read an answer aloud (replay) |
| POST | `/api/screenshot` | capture + OCR the screen → `{chars, text, suggestion_id}`; text joins the context and is answered |
| POST | `/api/assistant/answer-now` | → 202 + suggestion; answers what was said since the last answer (cuts the sentence in progress first); 409 if nothing was heard |
| POST | `/api/assistant/ask` | `{question}` → 202 + suggestion id; text streams over `/ws` |

## WebSocket `/ws`

Server → client messages are `{type, payload}`:

| type | payload |
|---|---|
| `session.state` | `{session: Session \| null}`, sent on connect and on every change |
| `assistant.started` | `Suggestion` (`auto: true` when triggered by a detected question) |
| `assistant.delta` | `{id, delta}` |
| `assistant.done` | `{id, response}` |
| `assistant.error` | `{id, message}` |
| `transcript.segment` | `{id, session_id, speaker: interviewer\|user\|unknown\|screen, text, created_at, is_question}` |
| `audio.mode` | `{mode}` |
| `tts.state` | `{available, read_aloud, speaking}` |
| `assistant.usage` | subscription usage window (Claude Code provider only) |
| `audio.status` | `{mic, system: starting\|on\|off\|error, stt: loading\|ready\|error\|off, devices, message}` |

Clients may send any text (e.g. `"ping"`) to keep the connection alive; the server ignores it.
