import { api, type CaptureMode } from "../../services/backend";
import { useAppStore } from "../../stores/app";

const OPTIONS: { mode: CaptureMode; label: string; title: string }[] = [
  {
    mode: "both",
    label: "Mic + System",
    title: "Your mic is \"You\", computer sound is \"Interviewer\". Questions from both are answered. Best for video calls (use headphones).",
  },
  {
    mode: "system",
    label: "System only",
    title: "Only the computer's sound (Zoom, Teams, Meet, YouTube). Your voice is not recorded. Questions heard there are answered.",
  },
  {
    mode: "mic",
    label: "Mic only",
    title: "Only your microphone, which hears everyone in the room. Questions it hears are answered: in-person interviews, or practising aloud.",
  },
];

/** Chooses which inputs are captured. Switching applies immediately, even mid-session. */
export function CaptureModeSelector() {
  const mode = useAppStore((s) => s.captureMode);
  const online = useAppStore((s) => s.backendOnline);
  const notify = useAppStore((s) => s.notify);

  const choose = (next: CaptureMode) => {
    if (next === mode) return;
    api.setCaptureMode(next).catch((err) => notify(err instanceof Error ? err.message : String(err)));
  };

  return (
    <div className="flex items-center gap-2 px-3 pb-2">
      <span className="text-[10px] uppercase tracking-wider text-slate-500">Listen to</span>
      <div role="radiogroup" aria-label="Audio to capture" className="flex rounded-md bg-black/30 p-0.5">
        {OPTIONS.map((o) => (
          <button
            key={o.mode}
            role="radio"
            aria-checked={mode === o.mode}
            disabled={!online}
            onClick={() => choose(o.mode)}
            title={o.title}
            className={`rounded px-2 py-1 text-[11px] disabled:opacity-40 ${
              mode === o.mode ? "bg-sky-600 text-white" : "text-slate-300 hover:bg-white/10"
            }`}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}
