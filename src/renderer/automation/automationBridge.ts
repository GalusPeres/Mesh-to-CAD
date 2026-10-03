// Answers the requests of the local automation interface (docs/AUTOMATION.md):
// the parts of the application state that only the user interface owns, such as
// the view, the open tool and the triangle selection. Document changes do not
// come through here; automation clients send them to the kernel directly.

import type { AutomationAction } from '@shared/automation';

import { allCommands, commandById, runCommand } from '../app/commands/registry';
import { i18n } from '../i18n';
import { replaceSelection } from '../selection/api';
import { selectionStore } from '../selection/selectionStore';
import { documentStore } from '../state/documentStore';
import { toolStore } from '../state/toolStore';

async function handle(action: AutomationAction): Promise<unknown> {
  switch (action.type) {
    case 'state':
      return {
        revision: documentStore.getState().snapshot?.revision ?? null,
        activeTool: toolStore.getState().activeToolId,
        selectedFaces: selectionStore.getState().count,
      };
    case 'listCommands':
      return allCommands().map((command) => ({
        id: command.id,
        label: i18n.t(command.label),
        enabled: command.isEnabled ? command.isEnabled() : true,
      }));
    case 'runCommand': {
      const command = commandById(action.id);
      if (!command) throw new Error(`unknown command: ${action.id}`);
      if (command.isEnabled && !command.isEnabled()) {
        throw new Error(`command not available right now: ${action.id}`);
      }
      await runCommand(command);
      return { ran: action.id };
    }
    case 'selectFaces': {
      const scan = documentStore.getState().snapshot?.document.scan;
      if (!scan) throw new Error('no scan loaded');
      replaceSelection(scan.key, scan.faceCount, Uint32Array.from(action.faces));
      return { selectedFaces: action.faces.length };
    }
    case 'click':
      return click(action.target);
    case 'key':
      return press(action);
  }
}

/** Click like the user: by test id first, else the button with that label or aria-label. */
function click(target: string): { clicked: string } {
  const byId = document.querySelector<HTMLElement>(`[data-testid="${CSS.escape(target)}"]`);
  const element =
    byId ??
    [...document.querySelectorAll<HTMLElement>('button, [role="button"], [role="radio"]')].find(
      (candidate) =>
        candidate.textContent?.trim() === target || candidate.getAttribute('aria-label') === target,
    );
  if (!element) throw new Error(`nothing to click: ${target}`);
  if (element instanceof HTMLButtonElement && element.disabled) {
    throw new Error(`disabled: ${target}`);
  }
  element.click();
  return { clicked: element.textContent?.trim() || target };
}

/** Press a key at the focused element (or the page), as keydown and keyup. */
function press(action: Extract<AutomationAction, { type: 'key' }>): { pressed: string } {
  const target = document.activeElement ?? document.body;
  const init: KeyboardEventInit = {
    key: action.key,
    ctrlKey: action.ctrl ?? false,
    shiftKey: action.shift ?? false,
    altKey: action.alt ?? false,
    bubbles: true,
    cancelable: true,
  };
  target.dispatchEvent(new KeyboardEvent('keydown', init));
  target.dispatchEvent(new KeyboardEvent('keyup', init));
  return { pressed: action.key };
}

export function installAutomationBridge(): void {
  window.m2c.automation.onRequest(({ requestId, action }) => {
    handle(action).then(
      (result) => window.m2c.automation.respond({ requestId, ok: true, result }),
      (error: unknown) =>
        window.m2c.automation.respond({
          requestId,
          ok: false,
          error: error instanceof Error ? error.message : String(error),
        }),
    );
  });
}
