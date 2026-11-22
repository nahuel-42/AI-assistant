import { useEffect, useState } from "react";
import { api, type PhoneInfo, type PhoneMode } from "../../services/backend";
import { useAppStore } from "../../stores/app";

const MODES: Record<PhoneMode, { label: string; help: string[] }> = {
  wifi: {
    label: "Same Wi-Fi",
    help: [
      "The phone must be on the same Wi-Fi as this computer.",
      "Some networks (buildings, hotels, guest Wi-Fi) keep devices apart: then use Internet link.",
    ],
  },
  internet: {
    label: "Internet link",
    help: [
      "Works from any network, mobile data included.",
      "The text travels encrypted through Cloudflare. Each time it's turned on, the address changes.",
    ],
  },
};

/** Turns the phone view on/off and shows the QR code to open it on a phone. */
export function PhonePanel({ onClose }: { onClose: () => void }) {
  const notify = useAppStore((s) => s.notify);
  const phone = useAppStore((s) => s.phone);
  const [info, setInfo] = useState<PhoneInfo | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (call: () => Promise<PhoneInfo>) => {
    setBusy(true);
    try {
      setInfo(await call());
    } catch (err) {
      notify(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  // Reload the link and QR whenever the phone view turns on/off or changes mode.
  useEffect(() => {
    void run(api.getPhone);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phone?.enabled, phone?.mode, phone?.cloudflared]);

  // Live fields come from backend events; the link and QR from the last request.
  const live = phone ?? info;
  const mode: PhoneMode = live?.mode ?? "wifi";
  const enabled = info?.enabled ?? false;
  const clients = live?.clients ?? 0;
  const needsDownload = mode === "internet" && live != null && !live.cloudflared;
  const waiting = busy || live?.starting || live?.installing;

  return (
    <section className="flex flex-1 flex-col items-center gap-3 overflow-y-auto px-4 py-3 text-center">
      <div className="flex w-full items-center justify-between">
        <span className="text-xs font-semibold text-slate-200">Phone view</span>
        <button
          onClick={() => void run(() => api.setPhone({ enabled: !enabled }))}
          disabled={waiting || info == null || needsDownload}
          className={`rounded-full px-3 py-1 text-xs font-medium disabled:opacity-40 ${
            enabled ? "bg-emerald-600 text-white hover:bg-emerald-500" : "bg-white/10 text-slate-200 hover:bg-white/20"
          }`}
        >
          {enabled ? "On" : "Off"}
        </button>
      </div>

      <div className="flex w-full rounded-lg bg-black/30 p-0.5">
        {(Object.keys(MODES) as PhoneMode[]).map((m) => (
          <button
            key={m}
            onClick={() => m !== mode && void run(() => api.setPhone({ mode: m }))}
            disabled={waiting}
            className={`flex-1 rounded-md px-2 py-1 text-[11px] disabled:opacity-60 ${
              m === mode ? "bg-sky-600 text-white" : "text-slate-300 hover:bg-white/10"
            }`}
          >
            {MODES[m].label}
          </button>
        ))}
      </div>

      {live?.error && <p className="rounded bg-red-500/15 px-2 py-1 text-[11px] text-red-300">{live.error}</p>}

      {needsDownload ? (
        <div className="flex flex-col items-center gap-2">
          <p className="text-[11px] text-slate-300">
            The internet link needs Cloudflare's free tunnel program ({live?.cloudflared_mb ?? 55} MB, one-time
            download from Cloudflare's official GitHub, checked before use).
          </p>
          <button
            onClick={() => void run(api.installTunnel)}
            disabled={waiting}
            className="rounded-md bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-40"
          >
            {live?.installing ? "Downloading…" : "Download"}
          </button>
        </div>
      ) : live?.starting ? (
        <p className="mt-6 text-xs text-slate-300">Connecting to Cloudflare… (a few seconds)</p>
      ) : enabled && info?.qr_image && info.url ? (
        <>
          <img src={info.qr_image} alt="QR code with the phone link" className="h-48 w-48 rounded-lg" />
          <p className="text-[11px] text-slate-300">Scan it with the phone's camera.</p>
          <p className={`text-xs ${clients ? "text-emerald-300" : "text-slate-400"}`}>
            {clients ? `📱 ${clients} phone${clients > 1 ? "s" : ""} connected` : "No phone connected yet"}
          </p>
          <code className="break-all rounded bg-black/30 px-2 py-1 text-[10px] text-slate-400">{info.url}</code>
          <button
            onClick={() => void run(api.newPhoneLink)}
            disabled={waiting}
            className="rounded-md px-2 py-1 text-[11px] text-slate-300 hover:bg-white/10 disabled:opacity-40"
          >
            New link
          </button>
        </>
      ) : (
        <p className="mt-4 text-xs text-slate-400">Turn it on to get the QR code.</p>
      )}

      <ul className="list-disc space-y-0.5 pl-4 text-left text-[11px] text-slate-400">
        {MODES[mode].help.map((line) => (
          <li key={line}>{line}</li>
        ))}
        <li>Read-only: the phone can't control the app. The link has a secret key, so don't share it.</li>
      </ul>

      <button onClick={onClose} className="mt-auto rounded-md px-3 py-1.5 text-xs text-slate-300 hover:bg-white/10">
        Close
      </button>
    </section>
  );
}
