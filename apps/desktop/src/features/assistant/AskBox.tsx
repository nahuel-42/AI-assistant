import { useState, type FormEvent } from "react";
import { useAppStore } from "../../stores/app";

export function AskBox({ onAsk, compact = false }: { onAsk: (q: string) => void; compact?: boolean }) {
  const [text, setText] = useState("");
  const online = useAppStore((s) => s.backendOnline);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const q = text.trim();
    if (!q) return;
    onAsk(q);
    setText("");
  };

  return (
    <form onSubmit={submit} className="flex gap-2 px-3 py-2">
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={!online}
        placeholder={compact ? "Ask…" : "Type the interviewer's question…"}
        className="min-w-0 flex-1 rounded-md border border-white/10 bg-black/30 px-2.5 py-1.5 text-xs text-slate-100 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none"
      />
      <button
        type="submit"
        disabled={!online || !text.trim()}
        className="rounded-md bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-40"
      >
        Ask
      </button>
    </form>
  );
}
