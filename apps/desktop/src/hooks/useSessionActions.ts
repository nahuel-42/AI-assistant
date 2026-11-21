import { useCallback } from "react";
import { api } from "../services/backend";
import { useAppStore } from "../stores/app";

/** Session commands shared by buttons and global shortcuts. State arrives back over the WebSocket. */
export function useSessionActions() {
  const notify = useAppStore((s) => s.notify);

  const run = useCallback(
    async (fn: () => Promise<unknown>) => {
      try {
        notify(null);
        await fn();
      } catch (err) {
        notify(err instanceof Error ? err.message : String(err));
      }
    },
    [notify],
  );

  const toggleSession = useCallback(
    () => run(() => (useAppStore.getState().session ? api.stopSession() : api.startSession())),
    [run],
  );
  const togglePause = useCallback(
    () =>
      run(() =>
        useAppStore.getState().session?.status === "paused" ? api.resumeSession() : api.pauseSession(),
      ),
    [run],
  );
  const ask = useCallback((question: string) => run(() => api.ask(question)), [run]);

  return { toggleSession, togglePause, ask };
}
