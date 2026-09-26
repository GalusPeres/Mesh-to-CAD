import { useTranslation } from 'react-i18next';

import type { StatusItem } from '../app/status/types';
import { useFormatter } from '../i18n/useFormatter';
import { useSelectedFaceCount } from './api';

function SelectionCount() {
  const { t } = useTranslation('selection');
  const format = useFormatter();
  const count = useSelectedFaceCount();
  if (count === 0) return null;
  return (
    <span data-testid="status-selection">
      {t('status.selected', { count, formatted: format.count(count) })}
    </span>
  );
}

export const statusItem: StatusItem = { order: 10, Component: SelectionCount };
