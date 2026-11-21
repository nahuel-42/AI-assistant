import { useAppStore } from "../../stores/app";

const PROVIDER_LABEL: Record<string, string> = {
  "claude-code": "Claude Pro plan",
  claude: "Claude API",
  echo: "Offline test mode",
};

function formatReset(epochSeconds?: number): string {
  if (!epochSeconds) return "";
  const time = new Date(epochSeconds * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return ` · resets ${time}`;
}

/** Which AI answers, and for subscription plans how much of the usage window is left. */
export function ProviderStatus() {
  const provider = useAppStore((s) => s.provider);
  const usage = useAppStore((s) => s.usage);
  if (!provider) return null;

  const window = usage?.unifiedWindows?.five_hour;
  const pct = window?.utilization != null ? Math.round(window.utilization * 100) : null;
  const tone =
    usage?.status && usage.status !== "allowed"
      ? "text-red-400"
      : pct != null && pct >= 80
        ? "text-amber-300"
        : "text-slate-500";

  return (
    <p className={`px-3 pt-1.5 text-[10px] ${tone}`}>
      {PROVIDER_LABEL[provider] ?? provider}
      {pct != null && ` · ${pct}% of 5-hour limit used${formatReset(window?.resetsAt)}`}
    </p>
  );
}
