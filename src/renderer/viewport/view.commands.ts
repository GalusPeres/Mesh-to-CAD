import { Maximize2 } from 'lucide-react';

import type { AppCommand } from '../app/commands/types';
import { type DisplayMode, setDisplayMode, setProjection, viewStore } from '../state/viewStore';
import { type StandardView, getViewport } from './api';
import { EDGE_DISPLAY_LIMIT } from './scanLayer';
import { cycleVisibility, sceneController, toggleSectionPlane, toggleXray } from './viewActions';

export const STANDARD_VIEW_KEYS: readonly [StandardView, string][] = [
  ['front', '1'],
  ['back', '2'],
  ['left', '3'],
  ['right', '4'],
  ['top', '5'],
  ['bottom', '6'],
  ['iso', '0'],
];

/** Display modes offered in menus; "covered" (Abgedeckt) is reserved for a later release. */
export const DISPLAY_MODES: readonly DisplayMode[] = [
  'shaded',
  'shadedEdges',
  'flat',
  'xray',
  'regions',
  'deviation',
];

const hasViewport = () => getViewport() !== null;

function displayModeCommand(mode: DisplayMode, order: number): AppCommand {
  if (mode === 'xray') {
    return {
      id: 'view.xray',
      label: 'viewport:display.xray',
      shortcuts: [{ key: 'X' }],
      scope: 'viewport',
      placement: { menu: 'view', group: 4, order },
      isChecked: () => viewStore.getState().displayMode === 'xray',
      run: toggleXray,
    };
  }
  return {
    id: `view.display.${mode}`,
    label: `viewport:display.${mode}`,
    placement: { menu: 'view', group: 4, order },
    isEnabled: () =>
      mode !== 'shadedEdges' || (getViewport()?.scan.faceCount ?? 0) < EDGE_DISPLAY_LIMIT,
    isChecked: () => viewStore.getState().displayMode === mode,
    run: () => setDisplayMode(mode),
  };
}

export const commands: readonly AppCommand[] = [
  {
    id: 'view.fitAll',
    label: 'viewport:commands.fitAll',
    icon: Maximize2,
    shortcuts: [{ key: 'F' }],
    scope: 'viewport',
    placement: { menu: 'view', group: 1, order: 1 },
    isEnabled: hasViewport,
    run: () => getViewport()?.camera.fitAll(),
  },
  {
    id: 'view.fitSelection',
    label: 'viewport:commands.fitSelection',
    shortcuts: [{ key: 'F', shift: true }],
    scope: 'viewport',
    placement: { menu: 'view', group: 1, order: 2 },
    isEnabled: hasViewport,
    run: () => sceneController()?.fitSelection(),
  },
  ...STANDARD_VIEW_KEYS.map(([view, key], index): AppCommand => ({
    id: `view.${view}`,
    label: `viewport:views.${view}`,
    shortcuts: [{ key }],
    scope: 'viewport',
    placement: { menu: 'view', group: 2, order: index },
    isEnabled: hasViewport,
    run: () => getViewport()?.camera.setStandardView(view),
  })),
  {
    id: 'view.perspective',
    label: 'viewport:commands.perspective',
    shortcuts: [{ key: 'P' }],
    scope: 'viewport',
    placement: { menu: 'view', group: 3, order: 1 },
    isChecked: () => viewStore.getState().projection === 'perspective',
    run: () =>
      setProjection(
        viewStore.getState().projection === 'perspective' ? 'orthographic' : 'perspective',
      ),
  },
  {
    id: 'view.cycleVisibility',
    label: 'viewport:commands.cycleVisibility',
    shortcuts: [{ key: ' ' }],
    scope: 'viewport',
    placement: { menu: 'view', group: 3, order: 2 },
    run: cycleVisibility,
  },
  {
    id: 'view.sectionPlane',
    label: 'viewport:commands.sectionPlane',
    placement: { menu: 'view', group: 3, order: 3 },
    isEnabled: hasViewport,
    isChecked: () => viewStore.getState().sectionPlane !== null,
    run: toggleSectionPlane,
  },
  ...DISPLAY_MODES.map(displayModeCommand),
];
