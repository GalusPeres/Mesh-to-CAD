import { useEffect } from 'react';

import { resolveShortcut } from './commands/keymap';
import { allCommands, runCommand } from './commands/registry';

function inTextField(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))
  );
}

/** Route key presses to commands. Viewport-scope keys never fire inside text fields. */
export function useShortcuts(): void {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.repeat) return;
      const command = resolveShortcut(event, allCommands(), {
        inTextField: inTextField(event.target),
        sketchMode: false,
      });
      if (!command || (command.isEnabled && !command.isEnabled())) return;
      event.preventDefault();
      void runCommand(command);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);
}
