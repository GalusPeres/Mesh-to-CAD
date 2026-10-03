import { useTranslation } from 'react-i18next';

import type { StatusItem } from '../../app/status/types';
import { useNetSession } from './netSession';

/** While the freeform-net tool is open: what the pointer does right now. */
function FreeformNetStatus() {
  const { t } = useTranslation('tools');
  const hint = useNetSession((state) => state.hint);
  const corner = useNetSession((state) => state.corner);
  if (!hint) return null;
  return (
    <span data-testid="status-freeform-net">
      {t(`freeformNet.hints.${hint}`, { count: corner })}
    </span>
  );
}

export const statusItem: StatusItem = { order: 5, Component: FreeformNetStatus };
