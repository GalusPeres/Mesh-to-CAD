// Answers the requests of the local automation interface (docs/AUTOMATION.md):
// the parts of the application state that only the user interface owns, such as
// the view, the open tool and the triangle selection. Document changes do not
// come through here; automation clients send them to the kernel directly.

import type { AutomationAction } from '@shared/automation';

import { allCommands, commandById, runCommand } from '../app/commands/registry';
import { i18n } from '../i18n';
import { deviationStore, isDeviationShown } from '../inspection/deviationStore';
import { replaceSelection } from '../selection/api';
import { selectionStore } from '../selection/selectionStore';
import { documentStore } from '../state/documentStore';
import { toolStore } from '../state/toolStore';
import { viewStore } from '../state/viewStore';
import { getViewport } from '../viewport/api';
import { toolInfo } from './toolInfo';

/** Whether the deviation colours are shown, and for which revision the map was made. */
function deviationState() {
  const summary = deviationStore.getState().summary;
  return {
    shown: isDeviationShown(),
    revision: summary?.revision ?? null,
    min: summary?.stats.min ?? null,
    max: summary?.stats.max ?? null,
  };
}

async function handle(action: AutomationAction): Promise<unknown> {
  switch (action.type) {
    case 'state': {
      const view = viewStore.getState();
      return {
        revision: documentStore.getState().snapshot?.revision ?? null,
        activeTool: toolStore.getState().activeToolId,
        selectedFaces: selectionStore.getState().count,
        visibility: view.visibility,
        displayMode: view.displayMode,
        // The heatmap is finished when its revision is the document's.
        deviation: deviationState(),
      };
    }
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
    case 'pointer':
      return pointer(action);
    case 'project': {
      const viewport = getViewport();
      if (!viewport) throw new Error('no viewport');
      return action.points.map((point) => viewport.worldToScreen(point));
    }
    case 'toolInfo':
      return toolInfo();
    case 'pick': {
      const viewport = getViewport();
      if (!viewport) throw new Error('no viewport');
      return viewport.pick({ x: action.x, y: action.y });
    }
  }
}

/** The canvas of the 3D view: the largest one in the main area. */
function viewCanvas(): HTMLCanvasElement {
  const canvases = [...document.querySelectorAll<HTMLCanvasElement>('main canvas')];
  const largest = canvases.sort(
    (a, b) => b.clientWidth * b.clientHeight - a.clientWidth * a.clientHeight,
  )[0];
  if (!largest) throw new Error('no 3D view');
  return largest;
}

const POINTER_TYPES = { down: 'pointerdown', move: 'pointermove', up: 'pointerup' } as const;

/** A pointer event on the 3D view, as the mouse would send it. */
function pointer(action: Extract<AutomationAction, { type: 'pointer' }>): { sent: string } {
  const canvas = viewCanvas();
  const rect = canvas.getBoundingClientRect();
  const button = action.button ?? 0;
  const pressed = action.kind === 'up' ? 0 : action.kind === 'down' ? 1 << button : 0;
  canvas.dispatchEvent(
    new PointerEvent(POINTER_TYPES[action.kind], {
      bubbles: true,
      cancelable: true,
      pointerId: 1,
      pointerType: 'mouse',
      isPrimary: true,
      clientX: rect.left + action.x,
      clientY: rect.top + action.y,
      button: action.kind === 'move' ? -1 : button,
      buttons: pressed,
      ctrlKey: action.ctrl ?? false,
      shiftKey: action.shift ?? false,
      altKey: action.alt ?? false,
    }),
  );
  if (action.kind === 'up' && button === 2) {
    canvas.dispatchEvent(
      new MouseEvent('contextmenu', {
        bubbles: true,
        cancelable: true,
        clientX: rect.left + action.x,
        clientY: rect.top + action.y,
        button: 2,
      }),
    );
  }
  return { sent: action.kind };
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
