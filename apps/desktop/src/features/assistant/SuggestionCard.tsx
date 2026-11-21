import { api } from "../../services/backend";
import { useAppStore, type SuggestionView } from "../../stores/app";

export function SuggestionCard({ item, showPrompt = true }: { item: SuggestionView; showPrompt?: boolean }) {
  const ttsAvailable = useAppStore((s) => s.tts?.available ?? false);
  return (
    <article className="rounded-lg border border-white/10 bg-white/5 p-2.5">
      {showPrompt && (
        <p className="mb-1.5 line-clamp-2 text-[11px] font-medium text-sky-300">
          {item.auto && <span className="mr-1 rounded bg-sky-500/20 px-1 text-[9px] uppercase">auto</span>}
          {item.prompt}
        </p>
      )}
      <p className="whitespace-pre-wrap text-xs leading-relaxed text-slate-100">
        {item.response}
        {item.status === "streaming" && <span className="ml-0.5 animate-pulse text-slate-400">▍</span>}
      </p>
      {item.status === "error" && <p className="mt-1.5 text-[11px] text-red-400">{item.error}</p>}
      {item.status === "done" && ttsAvailable && (
        <button
          onClick={() => void api.speak(item.response).catch(() => undefined)}
          className="mt-1.5 text-[10px] text-slate-400 hover:text-sky-300"
          title="Read this answer aloud again"
        >
          ▶ Read aloud
        </button>
      )}
    </article>
  );
}
