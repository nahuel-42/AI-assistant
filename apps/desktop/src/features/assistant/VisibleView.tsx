import { useAppStore } from "../../stores/app";
import { CaptureModeSelector } from "../audio/CaptureModeSelector";
import { SessionControls } from "../interview/SessionControls";
import { TranscriptPanel } from "../interview/TranscriptPanel";
import { AskBox } from "./AskBox";
import { ProviderStatus } from "./ProviderStatus";
import { SuggestionCard } from "./SuggestionCard";

interface Props {
  onToggleSession: () => void;
  onTogglePause: () => void;
  onAsk: (q: string) => void;
}

export function VisibleView({ onToggleSession, onTogglePause, onAsk }: Props) {
  const suggestions = useAppStore((s) => s.suggestions);

  return (
    <>
      <SessionControls onToggleSession={onToggleSession} onTogglePause={onTogglePause} />
      <CaptureModeSelector />
      <TranscriptPanel />
      <div className="flex-1 space-y-2 overflow-y-auto px-3 py-2">
        {suggestions.length === 0 ? (
          <p className="pt-6 text-center text-[11px] text-slate-500">
            Answers appear here automatically when a question is asked, by the interviewer or by you. You can also type one below.
          </p>
        ) : (
          suggestions.map((s) => <SuggestionCard key={s.id} item={s} />)
        )}
      </div>
      <div className="border-t border-white/10">
        <ProviderStatus />
        <AskBox onAsk={onAsk} />
      </div>
    </>
  );
}
