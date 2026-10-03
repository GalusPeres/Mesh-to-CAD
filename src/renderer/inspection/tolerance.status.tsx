import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { StatusItem } from '../app/status/types';
import { useFormatter } from '../i18n/useFormatter';
import { useDocument } from '../state/documentStore';
import { TolerancePopover } from './TolerancePopover';
import styles from './StatusButton.module.css';

const POPOVER_GAP_PX = 4;

/**
 * The project tolerance ("Toleranz ±0,100 mm"). A click opens the popover, the only
 * place where the tolerance changes (docs/DESIGN.md 3.5).
 */
function Tolerance() {
  const { t } = useTranslation('inspection');
  const format = useFormatter();
  const snapshot = useDocument((state) => state.snapshot);
  const [trigger, setTrigger] = useState<HTMLButtonElement | null>(null);
  const [position, setPosition] = useState<{ right: number; bottom: number } | null>(null);
  if (!snapshot?.document.scan) return null;

  const toggle = () => {
    const rect = trigger?.getBoundingClientRect();
    if (position || !rect) {
      setPosition(null);
      return;
    }
    setPosition({
      right: Math.max(0, window.innerWidth - rect.right),
      bottom: window.innerHeight - rect.top + POPOVER_GAP_PX,
    });
  };

  return (
    <>
      <button
        ref={setTrigger}
        type="button"
        className={styles.button}
        title={t('status.toleranceTooltip')}
        aria-haspopup="dialog"
        aria-expanded={position !== null}
        data-testid="status-tolerance"
        onClick={toggle}
      >
        {t('status.tolerance', { value: format.length(snapshot.document.settings.tolerance) })}
      </button>
      {position && (
        <TolerancePopover
          snapshot={snapshot}
          position={position}
          trigger={trigger}
          onClose={() => setPosition(null)}
        />
      )}
    </>
  );
}

export const statusItem: StatusItem = { order: 30, Component: Tolerance };
