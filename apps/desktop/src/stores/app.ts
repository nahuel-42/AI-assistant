import { create } from "zustand";
import type {
  AudioStatus,
  BackendEvent,
  CaptureMode,
  PhoneState,
  PlanUsage,
  Session,
  TranscriptSegment,
  TtsState,
} from "../services/backend";

export type AppMode = "visible" | "private";

export interface SuggestionView {
  id: string;
  prompt: string;
  response: string;
  status: "streaming" | "done" | "error";
  auto: boolean;
  error?: string;
}

interface AppState {
  backendOnline: boolean;
  session: Session | null;
  // Mode is UI-only: switching never touches the backend session or its context (FR-13).
  mode: AppMode;
  suggestions: SuggestionView[];
  transcript: TranscriptSegment[];
  audio: AudioStatus | null;
  provider: string | null;
  usage: PlanUsage | null;
  captureMode: CaptureMode;
  tts: TtsState | null;
  phone: PhoneState | null;
  notice: string | null;
  setBackendOnline: (online: boolean) => void;
  setProvider: (provider: string | null) => void;
  setMode: (mode: AppMode) => void;
  toggleMode: () => void;
  notify: (notice: string | null) => void;
  applyEvent: (event: BackendEvent) => void;
}

const MAX_SUGGESTIONS = 50;
const MAX_TRANSCRIPT = 300;

export const useAppStore = create<AppState>((set) => ({
  backendOnline: false,
  session: null,
  mode: "visible",
  suggestions: [],
  transcript: [],
  audio: null,
  provider: null,
  usage: null,
  captureMode: "both",
  tts: null,
  phone: null,
  notice: null,
  setBackendOnline: (backendOnline) => set({ backendOnline }),
  setProvider: (provider) => set({ provider }),
  setMode: (mode) => set({ mode }),
  toggleMode: () => set((s) => ({ mode: s.mode === "visible" ? "private" : "visible" })),
  notify: (notice) => set({ notice }),
  applyEvent: (event) =>
    set((s) => {
      switch (event.type) {
        case "session.state": {
          const next = event.payload.session;
          // A brand-new session starts clean; after stopping, the last transcript stays readable.
          const isNew = next && next.id !== s.session?.id;
          return {
            session: next,
            suggestions: isNew ? [] : s.suggestions,
            transcript: isNew ? [] : s.transcript,
            audio: next ? s.audio : null,
          };
        }
        case "audio.status":
          return { audio: event.payload };
        case "assistant.usage":
          return { usage: event.payload };
        case "audio.mode":
          return { captureMode: event.payload.mode };
        case "tts.state":
          return { tts: event.payload };
        case "phone.state":
          return { phone: event.payload };
        case "transcript.segment": {
          // Ignore late lines from an older session.
          if (s.session && event.payload.session_id !== s.session.id) return {};
          return { transcript: [...s.transcript, event.payload].slice(-MAX_TRANSCRIPT) };
        }
        case "assistant.started": {
          const { id, prompt, auto } = event.payload;
          if (s.suggestions.some((x) => x.id === id)) return {};
          const item: SuggestionView = { id, prompt, response: "", status: "streaming", auto };
          return { suggestions: [item, ...s.suggestions].slice(0, MAX_SUGGESTIONS) };
        }
        case "assistant.delta":
          return {
            suggestions: s.suggestions.map((x) =>
              x.id === event.payload.id ? { ...x, response: x.response + event.payload.delta } : x,
            ),
          };
        case "assistant.done":
          return {
            suggestions: s.suggestions.map((x) =>
              x.id === event.payload.id ? { ...x, response: event.payload.response, status: "done" } : x,
            ),
          };
        case "assistant.error":
          return {
            suggestions: s.suggestions.map((x) =>
              x.id === event.payload.id ? { ...x, status: "error", error: event.payload.message } : x,
            ),
          };
      }
    }),
}));
