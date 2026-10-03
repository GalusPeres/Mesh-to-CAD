import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useFormatter } from '../i18n/useFormatter';
import { useView } from '../state/viewStore';
import { useViewport } from '../viewport/api';
import styles from './CursorValue.module.css';
import { cursorLabel } from './deviationModel';
import { deviationValues, useDeviation } from './deviationStore';

const OFFSET_PX = 12;

interface Hover {
  /** Window coordinates of the cursor. */
  x: number;
  y: number;
  value: number;
}

/**
 * The deviation under the cursor, next to the cursor (docs/DESIGN.md 6.6). The value
 * of the scan triangle under the cursor is the mean of its three vertices.
 */
export function CursorValue({ host }: { host: HTMLElement | null }) {
  const { t } = useTranslation('inspection');
  const format = useFormatter();
  const viewport = useViewport();
  const shown = useView((state) => state.deviationVisible || state.displayMode === 'deviation');
  const version = useDeviation((state) => (state.summary ? state.version : null));
  const [hover, setHover] = useState<Hover | null>(null);

  useEffect(() => {
    const area = host?.closest('main');
    if (!viewport || !area || !shown || version === null) return;
    let frame = 0;
    const remove = viewport.addInteraction({
      onPointerMove: (event) => {
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(() => {
          const hit = viewport.pick(event.screen, { kinds: ['scan'] });
          const values = deviationValues();
          if (hit?.kind !== 'scan' || !values) {
            setHover(null);
            return;
          }
          const rect = area.getBoundingClientRect();
          setHover({
            x: rect.left + event.screen.x,
            y: rect.top + event.screen.y,
            value: values.faceValues[hit.face] ?? Number.NaN,
          });
        });
        return false;
      },
    });
    const leave = () => {
      cancelAnimationFrame(frame);
      setHover(null);
    };
    area.addEventListener('pointerleave', leave);
    return () => {
      remove();
      leave();
      area.removeEventListener('pointerleave', leave);
    };
  }, [viewport, host, shown, version]);

  if (!hover || !shown || version === null) return null;
  const label = cursorLabel(hover.value, format) ?? t('deviation.cursorNoData');
  return (
    <div
      className={styles.label}
      style={{ left: hover.x + OFFSET_PX, top: hover.y + OFFSET_PX }}
      data-testid="deviation-cursor-value"
    >
      {label}
    </div>
  );
}
