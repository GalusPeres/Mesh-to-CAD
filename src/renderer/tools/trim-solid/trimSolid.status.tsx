import { useTranslation } from 'react-i18next';

import type { StatusItem } from '../../app/status/types';
import { useTrimHint } from './trimSession';

/** While "Zuschneiden" is open: what a click on the preview does. */
function TrimSolidStatus() {
  const { t } = useTranslation('tools');
  const hint = useTrimHint();
  if (!hint) return null;
  return <span data-testid="status-trim-solid">{t(`trimSolid.hints.${hint}`)}</span>;
}

export const statusItem: StatusItem = { order: 5, Component: TrimSolidStatus };
