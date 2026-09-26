import { Maximize2 } from 'lucide-react';

import type { AppCommand } from '../app/commands/types';
import { setProjection, setVisibility, viewStore } from '../state/viewStore';
import { type StandardView, getViewport } from './api';

const VIEWS: readonly [StandardView, string][] = [
  ['front', '1'],
  ['back', '2'],
  ['left', '3'],
  ['right', '4'],
  ['top', '5'],
  ['bottom', '6'],
  ['iso', '0'],
];

const hasViewport = () => getViewport() !== null;

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
  ...VIEWS.map(([view, key], index): AppCommand => ({
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
    run: () => {
      const order = ['both', 'scan', 'bodies'] as const;
      const next =
        order[(order.indexOf(viewStore.getState().visibility) + 1) % order.length] ?? 'both';
      setVisibility(next);
    },
  },
];
