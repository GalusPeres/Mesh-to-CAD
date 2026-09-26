import type { AppCommand, Shortcut, ShortcutScope } from './types';

const KEY_NAMES: Record<string, { de: string; en: string }> = {
  Delete: { de: 'Entf', en: 'Del' },
  Enter: { de: 'Eingabe', en: 'Enter' },
  Escape: { de: 'Esc', en: 'Esc' },
  ' ': { de: 'Leertaste', en: 'Space' },
};

/** Shortcut text in the UI language: `Strg+Umschalt+I` or `Ctrl+Shift+I`. */
export function formatShortcut(shortcut: Shortcut, language: string): string {
  const german = language !== 'en';
  const parts: string[] = [];
  if (shortcut.ctrl) parts.push(german ? 'Strg' : 'Ctrl');
  if (shortcut.alt) parts.push('Alt');
  if (shortcut.shift) parts.push(german ? 'Umschalt' : 'Shift');
  const named = KEY_NAMES[shortcut.key];
  parts.push(
    named
      ? german
        ? named.de
        : named.en
      : shortcut.key.length === 1
        ? shortcut.key.toUpperCase()
        : shortcut.key,
  );
  return parts.join('+');
}

export function matchesShortcut(
  event: Pick<KeyboardEvent, 'key' | 'ctrlKey' | 'metaKey' | 'shiftKey' | 'altKey'>,
  shortcut: Shortcut,
): boolean {
  const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
  const wanted = shortcut.key.length === 1 ? shortcut.key.toLowerCase() : shortcut.key;
  const shifted = shortcut.key.length === 1 && !/[a-z0-9]/i.test(shortcut.key);
  return (
    key === wanted &&
    !!shortcut.ctrl === (event.ctrlKey || event.metaKey) &&
    !!shortcut.alt === event.altKey &&
    (shifted || !!shortcut.shift === event.shiftKey)
  );
}

function shortcutId(shortcut: Shortcut): string {
  return `${shortcut.ctrl ? 'ctrl+' : ''}${shortcut.alt ? 'alt+' : ''}${shortcut.shift ? 'shift+' : ''}${shortcut.key.toLowerCase()}`;
}

/** Pairs of commands that use the same shortcut in the same scope. */
export function findShortcutConflicts(commands: readonly AppCommand[]): [string, string][] {
  const seen = new Map<string, string>();
  const conflicts: [string, string][] = [];
  for (const command of commands) {
    for (const shortcut of command.shortcuts ?? []) {
      const key = `${command.scope ?? 'global'}:${shortcutId(shortcut)}`;
      const other = seen.get(key);
      if (other) conflicts.push([other, command.id]);
      else seen.set(key, command.id);
    }
  }
  return conflicts;
}

export interface KeyContext {
  inTextField: boolean;
  sketchMode: boolean;
}

const SCOPE_ORDER: readonly ShortcutScope[] = ['sketch', 'viewport', 'global'];

/** The command a key press triggers, respecting scopes and text-field focus. */
export function resolveShortcut(
  event: Pick<KeyboardEvent, 'key' | 'ctrlKey' | 'metaKey' | 'shiftKey' | 'altKey'>,
  commands: readonly AppCommand[],
  context: KeyContext,
): AppCommand | undefined {
  for (const scope of SCOPE_ORDER) {
    if (scope === 'sketch' && !context.sketchMode) continue;
    for (const command of commands) {
      if ((command.scope ?? 'global') !== scope) continue;
      if (context.inTextField && !command.inTextFields) continue;
      if (command.shortcuts?.some((shortcut) => matchesShortcut(event, shortcut))) return command;
    }
  }
  return undefined;
}
