import { useAppStore } from "../../stores/app";
import { formatShortcut, loadShortcuts } from "../settings/shortcuts";

interface Props {
  onToggleSession: () => void;
  onTogglePause: () => void;
}

export function SessionControls({ onToggleSession, onTogglePause }: Props) {
  const session = useAppStore((s) => s.session);
  const online = useAppStore((s) => s.backendOnline);
  const shortcut = formatShortcut(loadShortcuts().toggleSession);

  return (
    <div className="flex items-center gap-2 px-3 py-2">
      <button
        disabled={!online}
        onClick={onToggleSession}
        className={`rounded-md px-3 py-1.5 text-xs font-medium disabled:opacity-40 ${
          session ? "bg-red-600 text-white hover:bg-red-500" : "bg-emerald-600 text-white hover:bg-emerald-500"
        }`}
        title={shortcut}
      >
        {session ? "Stop session" : "Start session"}
      </button>
      {session && (
        <button
          onClick={onTogglePause}
          className="rounded-md bg-white/10 px-3 py-1.5 text-xs text-slate-200 hover:bg-white/20"
        >
          {session.status === "paused" ? "Resume" : "Pause"}
        </button>
      )}
      <span className="ml-auto truncate text-[11px] text-slate-400">
        {session ? session.title : `Press ${shortcut} to start`}
      </span>
    </div>
  );
}
