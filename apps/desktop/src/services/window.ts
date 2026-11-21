// Thin wrappers over the Tauri window API that no-op in a plain browser (npm run dev).
import { isTauri } from "@tauri-apps/api/core";
import { getCurrentWindow, LogicalSize } from "@tauri-apps/api/window";
import type { AppMode } from "../stores/app";

const SIZES: Record<AppMode, [number, number]> = {
  visible: [420, 640],
  private: [380, 170],
};

export async function applyWindowMode(mode: AppMode): Promise<void> {
  if (!isTauri()) return;
  const [w, h] = SIZES[mode];
  await getCurrentWindow().setSize(new LogicalSize(w, h));
}

export async function toggleWindowVisibility(): Promise<void> {
  if (!isTauri()) return;
  const win = getCurrentWindow();
  if (await win.isVisible()) {
    await win.hide();
  } else {
    await win.show();
    await win.setFocus();
  }
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Hides this window, reads the screen's text in the backend, then restores the window, so the
 * capture shows the interview (not the copilot itself).
 */
export async function captureScreenText<T>(capture: () => Promise<T>): Promise<T> {
  if (!isTauri()) return capture();
  const win = getCurrentWindow();
  const wasVisible = await win.isVisible();
  if (wasVisible) {
    await win.hide();
    await sleep(250); // let Windows repaint what was behind the window
  }
  try {
    return await capture();
  } finally {
    if (wasVisible) await win.show();
  }
}

export async function hideWindow(): Promise<void> {
  if (isTauri()) await getCurrentWindow().hide();
}
