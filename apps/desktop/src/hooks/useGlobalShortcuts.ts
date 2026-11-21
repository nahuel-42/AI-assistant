import { useEffect, useRef } from "react";
import { isTauri } from "@tauri-apps/api/core";
import { register, unregisterAll } from "@tauri-apps/plugin-global-shortcut";
import { loadShortcuts, type ShortcutAction } from "../features/settings/shortcuts";
import { useAppStore } from "../stores/app";

// Register/unregister calls are async; serialize them so a quick remount (React Strict Mode)
// can't interleave a teardown with a setup and leave shortcuts half-registered.
let queue: Promise<unknown> = Promise.resolve();
const enqueue = (task: () => Promise<unknown>) => (queue = queue.then(task, task));

/**
 * Registers OS-wide shortcuts (they work while another app, e.g. the meeting client, has focus).
 * Handlers live in a ref so re-renders don't re-register the shortcuts.
 */
export function useGlobalShortcuts(handlers: Record<ShortcutAction, () => void>) {
  const ref = useRef(handlers);
  ref.current = handlers;
  const notify = useAppStore((s) => s.notify);

  useEffect(() => {
    if (!isTauri()) return;
    const shortcuts = loadShortcuts();

    enqueue(async () => {
      await unregisterAll();
      const failed: string[] = [];
      for (const [action, accelerator] of Object.entries(shortcuts) as [ShortcutAction, string][]) {
        try {
          await register(accelerator, (event) => {
            if (event.state === "Pressed") ref.current[action]();
          });
        } catch {
          failed.push(accelerator); // usually: already taken by another application
        }
      }
      if (failed.length) notify(`Could not register shortcut(s): ${failed.join(", ")}`);
    });

    return () => void enqueue(() => unregisterAll());
  }, [notify]);
}
