import { useEffect, useState } from "react";
import { api } from "../../services/backend";
import { useAppStore } from "../../stores/app";

type Tab = "profile" | "style";

const TABS: Record<Tab, { label: string; help: string; saved: string }> = {
  profile: {
    label: "Profile",
    help: "CV, experience, projects, the job you are applying for, and notes. The assistant only uses facts written here.",
    saved: "Profile saved. It is used in every answer from now on.",
  },
  style: {
    label: "Answer style",
    help: "How answers to interview questions should sound: structure, tone and attitude. Applies to every answer.",
    saved: "Answer style saved. It applies to every answer from now on.",
  },
};

/** Edits the personal profile and the answer style. Both are saved locally and used in every answer. */
export function ProfileEditor({ onClose }: { onClose: () => void }) {
  const notify = useAppStore((s) => s.notify);
  const [tab, setTab] = useState<Tab>("profile");
  const [text, setText] = useState<Record<Tab, string | null>>({ profile: null, style: null });
  const [saved, setSaved] = useState<Record<Tab, string>>({ profile: "", style: "" });
  const [styleIsDefault, setStyleIsDefault] = useState(true);
  const [busy, setBusy] = useState(false);

  const fail = (err: unknown) => notify(err instanceof Error ? err.message : String(err));

  useEffect(() => {
    Promise.all([api.getProfile(), api.getStyle()])
      .then(([profile, style]) => {
        setText({ profile: profile.text, style: style.text });
        setSaved({ profile: profile.text, style: style.text });
        setStyleIsDefault(style.is_default);
      })
      .catch(fail);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const store = async (value: string) => {
    setBusy(true);
    try {
      if (tab === "profile") {
        const p = await api.saveProfile(value);
        setText((t) => ({ ...t, profile: p.text }));
        setSaved((s) => ({ ...s, profile: p.text }));
      } else {
        const st = await api.saveStyle(value);
        setText((t) => ({ ...t, style: st.text }));
        setSaved((s) => ({ ...s, style: st.text }));
        setStyleIsDefault(st.is_default);
      }
      notify(TABS[tab].saved);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };

  const current = text[tab];
  const dirty = current != null && current !== saved[tab];
  const tokens = Math.round((current?.length ?? 0) / 4);

  return (
    <section className="flex flex-1 flex-col gap-2 overflow-hidden px-3 py-2">
      <div className="flex items-center gap-1">
        {(Object.keys(TABS) as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded px-2 py-1 text-xs ${tab === t ? "bg-sky-600 text-white" : "text-slate-300 hover:bg-white/10"}`}
          >
            {TABS[t].label}
            {text[t] != null && text[t] !== saved[t] ? " •" : ""}
          </button>
        ))}
        <span className="ml-auto text-[10px] text-slate-500">≈{tokens} tokens · saved on this computer</span>
      </div>
      <p className="text-[11px] text-slate-400">
        {TABS[tab].help}
        {tab === "style" && styleIsDefault && " (Currently the default style.)"}
      </p>
      <textarea
        value={current ?? "Loading…"}
        disabled={current == null}
        onChange={(e) => setText((t) => ({ ...t, [tab]: e.target.value }))}
        spellCheck={false}
        className="min-h-0 flex-1 resize-none rounded-md border border-white/10 bg-black/30 p-2 font-mono text-[11px] leading-relaxed text-slate-100 focus:border-sky-500 focus:outline-none"
      />
      <div className="flex items-center justify-end gap-2">
        {tab === "style" && !styleIsDefault && (
          <button
            onClick={() => void store("")}
            disabled={busy}
            className="mr-auto rounded-md px-2 py-1.5 text-[11px] text-slate-400 hover:bg-white/10"
            title="Go back to the built-in answer style"
          >
            Reset to default
          </button>
        )}
        <button onClick={onClose} className="rounded-md px-3 py-1.5 text-xs text-slate-300 hover:bg-white/10">
          {dirty ? "Discard" : "Close"}
        </button>
        <button
          onClick={() => current != null && void store(current)}
          disabled={!dirty || busy}
          className="rounded-md bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-40"
        >
          {busy ? "Saving…" : "Save"}
        </button>
      </div>
    </section>
  );
}
