import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

export type Severity = 'info' | 'success' | 'warning' | 'error';

export interface Message {
  id: number;
  severity: Severity;
  /** Already translated text. */
  text: string;
  details?: string;
  time: number;
}

export interface MessageState {
  /** Shown in the status bar for a few seconds. */
  current: Message | null;
  /** Everything shown this session, newest first (the *Meldungen* list). */
  log: Message[];
}

const VISIBLE_MS = 6000;
let nextId = 1;
let hideTimer: ReturnType<typeof setTimeout> | undefined;

export const messageStore = createStore<MessageState>(() => ({ current: null, log: [] }));

export function useMessages<T>(selector: (state: MessageState) => T): T {
  return useStore(messageStore, selector);
}

export function showMessage(severity: Severity, text: string, details?: string): void {
  const message: Message = { id: nextId++, severity, text, details, time: Date.now() };
  messageStore.setState(({ log }) => ({ current: message, log: [message, ...log].slice(0, 200) }));
  clearTimeout(hideTimer);
  hideTimer = setTimeout(() => {
    if (messageStore.getState().current?.id === message.id)
      messageStore.setState({ current: null });
  }, VISIBLE_MS);
}
