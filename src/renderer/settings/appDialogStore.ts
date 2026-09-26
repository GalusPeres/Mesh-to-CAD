import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

/** The application dialogs of this module; at most one is open. */
export type AppDialog = 'settings' | 'shortcuts' | 'about';

export const appDialogStore = createStore<{ open: AppDialog | null }>(() => ({ open: null }));

export function useOpenDialog(): AppDialog | null {
  return useStore(appDialogStore, (state) => state.open);
}

export function openDialog(dialog: AppDialog): void {
  appDialogStore.setState({ open: dialog });
}

export function closeDialog(): void {
  appDialogStore.setState({ open: null });
}
