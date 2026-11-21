import { useEffect, useRef } from "react";
import { useAppStore } from "../../stores/app";

const LABEL = { interviewer: "Interviewer", user: "You", unknown: "Mic", screen: "Screen" } as const;

export function TranscriptPanel() {
  const transcript = useAppStore((s) => s.transcript);
  const audio = useAppStore((s) => s.audio);
  const session = useAppStore((s) => s.session);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [transcript.length]);

  let hint: string | null = null;
  if (!session) hint = "Start a session to capture your microphone and computer audio.";
  else if (session.status === "paused") hint = "Paused: nothing is being recorded.";
  else if (audio?.stt === "loading") hint = "Loading speech model… (the first time it downloads, ~0.5 GB)";
  else if (transcript.length === 0) hint = "Listening…";

  return (
    <section className="flex max-h-48 min-h-24 flex-col border-y border-white/10">
      <h2 className="px-3 pt-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        Live transcript
      </h2>
      <div className="flex-1 space-y-1 overflow-y-auto px-3 py-1.5">
        {transcript.map((seg) =>
          seg.speaker === "screen" ? (
            <details key={seg.id} className="rounded bg-violet-500/10 px-1 text-[11px] text-slate-300">
              <summary className="cursor-pointer">
                <span className="mr-1 font-semibold text-violet-300">Screen:</span>
                {seg.text.split("\n").length} lines read · click to view
              </summary>
              <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap font-mono text-[10px] text-slate-400">
                {seg.text}
              </pre>
            </details>
          ) : (
          <p
            key={seg.id}
            className={`text-[11px] leading-snug ${seg.is_question ? "rounded bg-sky-500/15 px-1 text-sky-100" : "text-slate-300"}`}
          >
            <span className={`mr-1 font-semibold ${seg.speaker === "user" ? "text-emerald-300" : "text-amber-300"}`}>
              {LABEL[seg.speaker]}:
            </span>
            {seg.text}
          </p>
          ),
        )}
        {hint && <p className="text-[11px] text-slate-500">{hint}</p>}
        {audio?.message && <p className="text-[11px] text-red-400">{audio.message}</p>}
        <div ref={end} />
      </div>
    </section>
  );
}
