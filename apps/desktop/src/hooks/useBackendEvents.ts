import { useEffect } from "react";
import { api, connectEvents } from "../services/backend";
import { useAppStore } from "../stores/app";

export function useBackendEvents() {
  useEffect(() => {
    const { applyEvent, setBackendOnline, setProvider } = useAppStore.getState();
    return connectEvents(applyEvent, (online) => {
      setBackendOnline(online);
      if (online) {
        api.health().then((h) => setProvider(h.provider)).catch(() => setProvider(null));
      }
    });
  }, []);
}
