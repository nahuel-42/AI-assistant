import { api } from "../services/backend";
import { useAppStore } from "../stores/app";

/** Read-aloud toggle plus a Stop button while an answer is being spoken. Shown in both modes. */
export function VoiceControls() {
  const tts = useAppStore((s) => s.tts);
  const notify = useAppStore((s) => s.notify);
  if (!tts?.available) return null;

  const fail = (err: unknown) => notify(err instanceof Error ? err.message : String(err));

  return (
    <>
      {tts.speaking && (
        <button
          onClick={() => api.stopSpeaking().catch(fail)}
          className="flex items-center gap-1 rounded bg-red-600 px-2 py-0.5 text-[11px] font-medium text-white hover:bg-red-500"
          title="Stop reading the answer aloud"
        >
          <span className="inline-block h-2 w-2 bg-white" />
          Stop
        </button>
      )}
      <button
        onClick={() => api.setReadAloud(!tts.read_aloud).catch(fail)}
        aria-pressed={tts.read_aloud}
        aria-label="Read answers aloud"
        className={`rounded px-1.5 py-0.5 text-[11px] hover:bg-white/10 ${tts.read_aloud ? "text-sky-300" : "text-slate-500"}`}
        title={tts.read_aloud ? "Answers are read aloud. Click to turn off." : "Answers are not read aloud. Click to turn on."}
      >
        {tts.read_aloud ? "🔊" : "🔇"}
      </button>
    </>
  );
}
