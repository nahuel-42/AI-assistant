import { formatShortcut, loadShortcuts, type ShortcutAction } from "../features/settings/shortcuts";

const LABELS: Record<ShortcutAction, string> = {
  toggleSession: "Start / stop session",
  answerNow: "Answer what was just said",
  screenshot: "Read screen and get help",
  toggleWindow: "Show / hide window",
  toggleMode: "Compact / expand",
};

/** Keyboard icon; hovering it (or focusing it with Tab) shows every global shortcut. */
export function ShortcutsHint() {
  const shortcuts = loadShortcuts();

  return (
    <div className="group relative">
      <button
        className="rounded px-1.5 py-0.5 text-[11px] text-slate-300 hover:bg-white/10"
        aria-label="Keyboard shortcuts"
      >
        ⌨
      </button>
      <div
        role="tooltip"
        className="pointer-events-none invisible absolute right-0 top-full z-50 mt-1 w-60 rounded-md border border-white/10 bg-slate-950/95 p-2 opacity-0 shadow-xl transition-opacity group-focus-within:visible group-focus-within:opacity-100 group-hover:visible group-hover:opacity-100"
      >
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
          Shortcuts (work from any app)
        </p>
        <ul className="space-y-1">
          {(Object.keys(LABELS) as ShortcutAction[]).map((action) => (
            <li key={action} className="flex items-center justify-between gap-2 text-[11px] text-slate-200">
              <span>{LABELS[action]}</span>
              <kbd className="whitespace-nowrap rounded border border-white/15 bg-white/5 px-1 font-mono text-[10px] text-slate-300">
                {formatShortcut(shortcuts[action])}
              </kbd>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
