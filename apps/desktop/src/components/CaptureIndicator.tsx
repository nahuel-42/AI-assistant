import type { DeviceState } from "../services/backend";
import { useAppStore } from "../stores/app";

const DOT: Record<DeviceState, string> = {
  on: "bg-red-500 animate-pulse",
  starting: "bg-amber-400",
  off: "bg-slate-600",
  error: "bg-yellow-300",
};

function Device({ label, state, device }: { label: string; state?: DeviceState; device?: string }) {
  if (!state) return null;
  return (
    <span className="flex items-center gap-1" title={`${device ?? label}: ${state}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${DOT[state]}`} />
      {label}
    </span>
  );
}

/** Always rendered in both modes: what is being captured must never be hidden (PRD §3.2, §12). */
export function CaptureIndicator() {
  const session = useAppStore((s) => s.session);
  const audio = useAppStore((s) => s.audio);

  if (!session) {
    return <span className="text-[10px] text-slate-500">● idle</span>;
  }
  if (session.status === "paused") {
    return <span className="text-[10px] font-medium text-amber-300">❚❚ paused · not recording</span>;
  }
  return (
    <span className="flex items-center gap-2 text-[10px] font-medium text-red-300">
      <span>live</span>
      <Device label="mic" state={audio?.mic} device={audio?.devices.mic} />
      <Device label="system" state={audio?.system} device={audio?.devices.system} />
    </span>
  );
}
