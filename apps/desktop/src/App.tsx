import { useEffect, useState } from "react";
import { TitleBar } from "./components/TitleBar";
import { PrivateView } from "./features/assistant/PrivateView";
import { VisibleView } from "./features/assistant/VisibleView";
import { ProfileEditor } from "./features/settings/ProfileEditor";
import { useBackendEvents } from "./hooks/useBackendEvents";
import { useGlobalShortcuts } from "./hooks/useGlobalShortcuts";
import { useSessionActions } from "./hooks/useSessionActions";
import { api } from "./services/backend";
import { applyWindowMode, captureScreenText, toggleWindowVisibility } from "./services/window";
import { useAppStore } from "./stores/app";

export default function App() {
  const mode = useAppStore((s) => s.mode);
  const notice = useAppStore((s) => s.notice);
  const notify = useAppStore((s) => s.notify);
  const toggleMode = useAppStore((s) => s.toggleMode);
  const { toggleSession, togglePause, ask } = useSessionActions();
  const setMode = useAppStore((s) => s.setMode);
  const [profileOpen, setProfileOpen] = useState(false);

  const openProfile = () => {
    setMode("visible"); // the editor needs the full-size window
    setProfileOpen((open) => !open);
  };

  useBackendEvents();

  const screenshot = async () => {
    notify("Reading your screen…");
    try {
      const result = await captureScreenText(() => api.screenshot());
      notify(
        result.chars
          ? `Screen read (${result.text.split("\n").length} lines). Answer on the way.`
          : "No text found on the screen.",
      );
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err));
    }
  };

  // Answer key: answer what was just said, without waiting for a question to be detected.
  const answerNow = async () => {
    try {
      await api.answerNow();
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err));
    }
  };

  useEffect(() => {
    void applyWindowMode(mode);
  }, [mode]);

  useGlobalShortcuts({
    toggleSession: () => void toggleSession(),
    toggleWindow: () => void toggleWindowVisibility(),
    toggleMode,
    screenshot: () => void screenshot(),
    answerNow: () => void answerNow(),
  });

  return (
    <main className="flex h-full flex-col overflow-hidden rounded-xl border border-white/10 bg-slate-900/95 text-slate-100 shadow-2xl">
      <TitleBar onScreenshot={() => void screenshot()} onAnswerNow={() => void answerNow()} onProfile={openProfile} />
      {notice && (
        <button
          onClick={() => notify(null)}
          className="bg-amber-500/15 px-3 py-1.5 text-left text-[11px] text-amber-200"
          title="Dismiss"
        >
          {notice}
        </button>
      )}
      {profileOpen ? (
        <ProfileEditor onClose={() => setProfileOpen(false)} />
      ) : mode === "visible" ? (
        <VisibleView onToggleSession={toggleSession} onTogglePause={togglePause} onAsk={ask} />
      ) : (
        <PrivateView onAsk={ask} />
      )}
    </main>
  );
}
