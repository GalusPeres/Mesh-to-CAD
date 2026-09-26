import { createStore } from 'zustand/vanilla';

export const settingsDialogStore = createStore<{ open: boolean }>(() => ({ open: false }));

export function openSettings(): void {
  settingsDialogStore.setState({ open: true });
}

export function closeSettings(): void {
  settingsDialogStore.setState({ open: false });
}
