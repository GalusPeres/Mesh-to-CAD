import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

import { DEFAULT_SETTINGS, type Settings, type SettingsPatch } from '@shared/settings';

/** Preferences mirrored from the main process, which stores them. */
export const settingsStore = createStore<Settings>(() => structuredClone(DEFAULT_SETTINGS));

export function useSettings<T>(selector: (settings: Settings) => T): T {
  return useStore(settingsStore, selector);
}

export function loadSettings(settings: Settings): void {
  settingsStore.setState(settings, true);
}

export async function updateSettings(patch: SettingsPatch): Promise<void> {
  loadSettings(await window.m2c.settings.set(patch));
}
