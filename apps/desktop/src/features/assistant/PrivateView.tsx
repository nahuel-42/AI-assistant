import { useAppStore } from "../../stores/app";
import { AskBox } from "./AskBox";
import { SuggestionCard } from "./SuggestionCard";

/** Compact layout: only the latest suggestion. Same session and context as Visible Mode. */
export function PrivateView({ onAsk }: { onAsk: (q: string) => void }) {
  const latest = useAppStore((s) => s.suggestions[0]);

  return (
    <>
      <div className="flex-1 overflow-y-auto px-3 py-2">
        {latest ? (
          <SuggestionCard item={latest} />
        ) : (
          <p className="text-[11px] text-slate-500">No suggestions yet.</p>
        )}
      </div>
      <AskBox onAsk={onAsk} compact />
    </>
  );
}
