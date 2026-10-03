import { useState } from 'react';

import type { ViewportOverlay } from '../app/extensions';
import { CursorValue } from './CursorValue';
import { DeviationLegend } from './DeviationLegend';
import { useDeviationDisplay } from './useDeviationDisplay';

/** Always mounted with the viewport: keeps the colour map in sync and shows the legend. */
function DeviationOverlay() {
  useDeviationDisplay();
  const [host, setHost] = useState<HTMLDivElement | null>(null);
  return (
    <div ref={setHost}>
      <DeviationLegend />
      <CursorValue host={host} />
    </div>
  );
}

export const overlay: ViewportOverlay = { anchor: 'right', order: 10, Component: DeviationOverlay };
