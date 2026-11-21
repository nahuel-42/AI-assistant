import { useAppStore } from "../stores/app";
import { hideWindow } from "../services/window";
import { CaptureIndicator } from "./CaptureIndicator";
import { ShortcutsHint } from "./ShortcutsHint";
import { VoiceControls } from "./VoiceControls";

export function TitleBar({
  onScreenshot,
  onAnswerNow,
  onProfile,
}: {
  onScreenshot: () => void;
  onAnswerNow: () => void;
  onProfile: () => void;
}) {
  const mode = useAppStore((s) => s.mode);
  const toggleMode = useAppStore((s) => s.toggleMode);
  const backendOnline = useAppStore((s) => s.backendOnline);

  return (
    // data-tauri-drag-region lets the user move the frameless window by its title bar.
    <header
      data-tauri-drag-region
      className="flex items-center gap-2 border-b border-white/10 px-3 py-2 select-none"
    >
      <span data-tauri-drag-region className="text-xs font-semibold tracking-wide text-slate-200">
        Interview Copilot
      </span>
      <CaptureIndicator />
      <div data-tauri-drag-region className="flex-1" />
      {!backendOnline && (
        <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] text-amber-300">
          backend offline
        </span>
      )}
      <button
        onClick={onProfile}
        disabled={!backendOnline}
        className="rounded px-1.5 py-0.5 text-[11px] text-slate-300 hover:bg-white/10 disabled:opacity-40"
        title="My profile: CV, experience and target job used in every answer"
        aria-label="Profile"
      >
        👤
      </button>
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
      <VoiceControls />
      <ShortcutsHint />
      <button
        onClick={toggleMode}
        className="rounded px-1.5 py-0.5 text-[11px] text-slate-300 hover:bg-white/10"
        title="Switch mode (Ctrl+Shift+M)"
      >
        {mode === "visible" ? "Compact" : "Expand"}
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
