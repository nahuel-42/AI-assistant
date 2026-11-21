// HTTP + WebSocket client for the local Python backend.

export const API_BASE: string = import.meta.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8765";

export type SessionStatus = "active" | "paused" | "stopped";

export interface Session {
  id: string;
  title: string;
  status: SessionStatus;
  started_at: string;
  ended_at: string | null;
}

export interface Suggestion {
  id: string;
  session_id: string | null;
  prompt: string;
  response: string;
  status: "streaming" | "done" | "error";
  created_at: string;
  auto: boolean;
}

export interface TranscriptSegment {
  id: number;
  session_id: string;
  speaker: "interviewer" | "user" | "unknown" | "screen";
  text: string;
  created_at: string;
  is_question: boolean;
}

export type DeviceState = "starting" | "on" | "off" | "error";

export interface AudioStatus {
  mic?: DeviceState;
  system?: DeviceState;
  stt: "loading" | "ready" | "error" | "off";
  devices: { mic?: string; system?: string };
  message: string | null;
}

export type CaptureMode = "both" | "mic" | "system";

export interface TtsState {
  available: boolean;
  read_aloud: boolean;
  speaking: boolean;
}

export interface PlanUsage {
  status?: string;
  rateLimitType?: string;
  resetsAt?: number;
  unifiedWindows?: Record<string, { utilization?: number; resetsAt?: number; status?: string }>;
}

export interface Health {
  status: string;
  provider: string;
  audio: boolean;
  stt_model: string | null;
}

export type BackendEvent =
  | { type: "session.state"; payload: { session: Session | null } }
  | { type: "assistant.started"; payload: Suggestion }
  | { type: "assistant.delta"; payload: { id: string; delta: string } }
  | { type: "assistant.done"; payload: { id: string; response: string } }
  | { type: "assistant.error"; payload: { id: string; message: string } }
  | { type: "transcript.segment"; payload: TranscriptSegment }
  | { type: "audio.status"; payload: AudioStatus }
  | { type: "assistant.usage"; payload: PlanUsage }
  | { type: "audio.mode"; payload: { mode: CaptureMode } }
  | { type: "tts.state"; payload: TtsState };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed (${res.status})`);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export const api = {
  health: () => request<Health>("/api/health"),
  startSession: (title?: string) =>
    request<Session>("/api/sessions", { method: "POST", body: JSON.stringify({ title }) }),
  pauseSession: () => request<Session>("/api/sessions/current/pause", { method: "POST" }),
  resumeSession: () => request<Session>("/api/sessions/current/resume", { method: "POST" }),
  stopSession: () => request<Session>("/api/sessions/current/stop", { method: "POST" }),
  listSessions: () => request<Session[]>("/api/sessions"),
  setCaptureMode: (mode: CaptureMode) =>
    request<{ mode: CaptureMode }>("/api/audio/mode", { method: "PUT", body: JSON.stringify({ mode }) }),
  setReadAloud: (read_aloud: boolean) =>
    request<TtsState>("/api/tts", { method: "PUT", body: JSON.stringify({ read_aloud }) }),
  stopSpeaking: () => request<void>("/api/tts/stop", { method: "POST" }),
  speak: (text: string) => request<void>("/api/tts/speak", { method: "POST", body: JSON.stringify({ text }) }),
  getStyle: () => request<{ text: string; is_default: boolean }>("/api/style"),
  saveStyle: (text: string) =>
    request<{ text: string; is_default: boolean }>("/api/style", { method: "PUT", body: JSON.stringify({ text }) }),
  getProfile: () => request<{ text: string }>("/api/profile"),
  saveProfile: (text: string) =>
    request<{ text: string }>("/api/profile", { method: "PUT", body: JSON.stringify({ text }) }),
  screenshot: () =>
    request<{ chars: number; text: string; suggestion_id: string | null }>("/api/screenshot", { method: "POST" }),
  answerNow: () => request<Suggestion>("/api/assistant/answer-now", { method: "POST" }),
  ask: (question: string) =>
    request<Suggestion>("/api/assistant/ask", { method: "POST", body: JSON.stringify({ question }) }),
};

/** Connects to /ws and reconnects with backoff. Returns a function that closes the connection. */
export function connectEvents(
  onEvent: (event: BackendEvent) => void,
  onStatus: (online: boolean) => void,
): () => void {
  let socket: WebSocket | null = null;
  let closed = false;
  let retryMs = 500;
  let retryTimer: number | undefined;
  let pingTimer: number | undefined;

  const open = () => {
    socket = new WebSocket(API_BASE.replace(/^http/, "ws") + "/ws");
    socket.onopen = () => {
      retryMs = 500;
      onStatus(true);
      pingTimer = window.setInterval(() => socket?.send("ping"), 20_000);
    };
    socket.onmessage = (msg) => onEvent(JSON.parse(msg.data) as BackendEvent);
    socket.onclose = () => {
      window.clearInterval(pingTimer);
      onStatus(false);
      if (closed) return;
      retryTimer = window.setTimeout(open, retryMs);
      retryMs = Math.min(retryMs * 2, 5_000);
    };
  };

  open();
  return () => {
    closed = true;
    window.clearTimeout(retryTimer);
    window.clearInterval(pingTimer);
    socket?.close();
  };
}
