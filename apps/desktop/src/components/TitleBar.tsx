import { useAppStore } from "../stores/app";
import { hideWindow } from "../services/window";
import { CaptureIndicator } from "./CaptureIndicator";
import { ShortcutsHint } from "./ShortcutsHint";
import { VoiceControls } from "./VoiceControls";

export function TitleBar({
  onScreenshot,
  onAnswerNow,
  onProfile,
  onPhone,
}: {
  onScreenshot: () => void;
  onAnswerNow: () => void;
  onProfile: () => void;
  onPhone: () => void;
}) {
  const phone = useAppStore((s) => s.phone);
  const phoneConnected = (phone?.clients ?? 0) > 0;
  const mode = useAppStore((s) => s.mode);
  const toggleMode = useAppStore((s) => s.toggleMode);
  const backendOnline = useAppStore((s) => s.backendOnline);
  const session = useAppStore((s) => s.session);

  return (
    // data-tauri-drag-region lets the user move the frameless window by its title bar.
    <header
      data-tauri-drag-region
      className="flex items-center gap-1 border-b border-white/10 px-3 py-2 select-none [&>*]:shrink-0"
    >
      {/* During a session the capture indicator needs the room more than the app name. */}
      {mode === "visible" && !session && (
        <span
          data-tauri-drag-region
          className="mr-1 text-xs font-semibold tracking-wide text-slate-200"
        >
          Interview Copilot
        </span>
      )}
      <CaptureIndicator />
      <div data-tauri-drag-region className="flex-1" />
      {!backendOnline && (
        <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] text-amber-300">
          backend offline
        </span>
      )}
      {/* Compact keeps only what is needed mid-interview; panels open in the full view anyway. */}
      {mode === "visible" && (
        <button
          onClick={onProfile}
          disabled={!backendOnline}
          className="rounded px-1.5 py-0.5 text-[11px] text-slate-300 hover:bg-white/10 disabled:opacity-40"
          title="My profile: CV, experience and target job used in every answer"
          aria-label="Profile"
        >
          👤
        </button>
      )}
      <button
        onClick={onAnswerNow}
        disabled={!backendOnline}
        className="rounded px-1.5 py-0.5 text-[11px] text-slate-300 hover:bg-white/10 disabled:opacity-40"
        title="Answer what was just said, even if it wasn't detected as a question (Ctrl+Shift+Q)"
        aria-label="Answer now"
      >
        💬
      </button>
      <button
        onClick={onScreenshot}
        disabled={!backendOnline}
        className="rounded px-1.5 py-0.5 text-[11px] text-slate-300 hover:bg-white/10 disabled:opacity-40"
        title="Read the text on your screen and get help with it (Ctrl+Shift+S)"
        aria-label="Screenshot"
      >
        📷
      </button>
      {(mode === "visible" || phoneConnected) && (
        <button
          onClick={onPhone}
          disabled={!backendOnline}
          className={`rounded px-1.5 py-0.5 text-[11px] hover:bg-white/10 disabled:opacity-40 ${
            phoneConnected
              ? "bg-emerald-500/20 text-emerald-300"
              : "text-slate-300"
          }`}
          title={
            phoneConnected
              ? `Phone view: ${phone?.clients} phone(s) connected`
              : phone?.enabled
                ? "Phone view is on: show the QR code"
                : "See answers on your phone (QR code)"
          }
          aria-label="Phone view"
        >
          📱
        </button>
      )}
      <VoiceControls />
      {mode === "visible" && <ShortcutsHint />}
      <button
        onClick={toggleMode}
        className="rounded px-1.5 py-0.5 text-[11px] text-slate-300 hover:bg-white/10"
        title={mode === "visible" ? "Compact view (Ctrl+Shift+M)" : "Full view (Ctrl+Shift+M)"}
        aria-label={mode === "visible" ? "Compact view" : "Full view"}
      >
        {mode === "visible" ? "⊟" : "⊞"}
      </button>
      <button
        onClick={() => void hideWindow()}
        className="rounded px-1.5 py-0.5 text-[11px] text-slate-300 hover:bg-white/10"
        title="Hide (Ctrl+Shift+A to show again)"
        aria-label="Hide window"
      >
        ✕
      </button>
    </header>
  );
}
