import { useTranslation } from 'react-i18next';

import type { StatusItem } from '../app/status/types';
import { useFormatter } from '../i18n/useFormatter';
import { useSelectedFaceCount } from './api';
import { useSelectionState } from './selectionStore';

function SelectionCount() {
  const { t } = useTranslation('selection');
  const format = useFormatter();
  const count = useSelectedFaceCount();
  const hidden = useSelectionState((state) => state.hiddenCount);
  if (count === 0 && hidden === 0) return null;
  return (
    <span data-testid="status-selection">
      {count > 0 && t('status.selected', { count, formatted: format.count(count) })}
      {count > 0 && hidden > 0 && ' · '}
      {hidden > 0 && t('status.hidden', { count: hidden, formatted: format.count(hidden) })}
    </span>
  );
}

export const statusItem: StatusItem = { order: 10, Component: SelectionCount };
