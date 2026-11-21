// Global shortcut bindings (PRD §10). Stored in localStorage so they can be overridden;
// a settings screen to edit them arrives in Phase 5 (FR-14).

export type ShortcutAction = "toggleSession" | "screenshot" | "toggleWindow" | "toggleMode" | "answerNow";

export type ShortcutMap = Record<ShortcutAction, string>;

export const DEFAULT_SHORTCUTS: ShortcutMap = {
  toggleSession: "CommandOrControl+Shift+Space",
  screenshot: "CommandOrControl+Shift+S",
  toggleWindow: "CommandOrControl+Shift+A",
  toggleMode: "CommandOrControl+Shift+M",
  answerNow: "CommandOrControl+Shift+Q",
};

const STORAGE_KEY = "copilot.shortcuts";

export function loadShortcuts(): ShortcutMap {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? { ...DEFAULT_SHORTCUTS, ...JSON.parse(raw) } : DEFAULT_SHORTCUTS;
  } catch {
    return DEFAULT_SHORTCUTS;
  }
}

export function saveShortcuts(map: ShortcutMap): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
}

/** "CommandOrControl+Shift+Space" -> "Ctrl+Shift+Space" for display. */
export function formatShortcut(accelerator: string): string {
  return accelerator.replace("CommandOrControl", "Ctrl");
}
