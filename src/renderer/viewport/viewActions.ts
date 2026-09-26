// View settings changed from commands, the tool row and the view cube buttons.

import {
  type DisplayMode,
  type Visibility,
  setDisplayMode,
  setSectionPlane,
  setVisibility,
  viewStore,
} from '../state/viewStore';
import { getViewport } from './api';
import { SceneController } from './SceneController';

const VISIBILITY_ORDER: readonly Visibility[] = ['both', 'scan', 'bodies'];

/** Space cycles: scan and bodies, only the scan, only the bodies (docs/DESIGN.md 6.2). */
export function nextVisibility(current: Visibility): Visibility {
  return (
    VISIBILITY_ORDER[(VISIBILITY_ORDER.indexOf(current) + 1) % VISIBILITY_ORDER.length] ?? 'both'
  );
}

export function cycleVisibility(): void {
  setVisibility(nextVisibility(viewStore.getState().visibility));
}

let beforeXray: DisplayMode = 'shaded';

/** X switches x-ray on, and off again to the mode that was shown before. */
export function toggleXray(): void {
  const mode = viewStore.getState().displayMode;
  if (mode === 'xray') {
    setDisplayMode(beforeXray);
  } else {
    beforeXray = mode;
    setDisplayMode('xray');
  }
}

/** The mounted viewport implementation, for the view commands inside viewport/. */
export function sceneController(): SceneController | null {
  const viewport = getViewport();
  return viewport instanceof SceneController ? viewport : null;
}

/** Section plane on (through the middle of the scene, facing the viewer) or off. */
export function toggleSectionPlane(): void {
  if (viewStore.getState().sectionPlane) {
    setSectionPlane(null);
    return;
  }
  const controller = sceneController();
  if (controller) setSectionPlane(controller.defaultSectionPlane());
}
