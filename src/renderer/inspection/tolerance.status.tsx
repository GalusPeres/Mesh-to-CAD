import { useTranslation } from 'react-i18next';

import type { StatusItem } from '../app/status/types';
import { useFormatter } from '../i18n/useFormatter';
import { useDocument } from '../state/documentStore';

/**
 * The project tolerance ("Toleranz ±0,10 mm"). It is the only place to change the
 * tolerance; editing opens from here (not implemented yet).
 */
function Tolerance() {
  const { t } = useTranslation('inspection');
  const format = useFormatter();
  const snapshot = useDocument((state) => state.snapshot);
  if (!snapshot?.document.scan) return null;
  const value = format.length(snapshot.document.settings.tolerance);
  return <span data-testid="status-tolerance">{t('status.tolerance', { value })}</span>;
}

export const statusItem: StatusItem = { order: 30, Component: Tolerance };
