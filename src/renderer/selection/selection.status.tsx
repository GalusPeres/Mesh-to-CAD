import { X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { StatusItem } from '../app/status/types';
import { useFormatter } from '../i18n/useFormatter';
import { IconButton } from '../ui/IconButton/IconButton';
import { useSelectedFaceCount } from './api';
import styles from './SelectionStatus.module.css';
import { clearSelectedFaces } from './selectionEdits';
import { useSelectionState } from './selectionStore';

function SelectionCount() {
  const { t } = useTranslation('selection');
  const format = useFormatter();
  const count = useSelectedFaceCount();
  const hidden = useSelectionState((state) => state.hiddenCount);
  if (count === 0 && hidden === 0) return null;
  return (
    <span className={styles.item} data-testid="status-selection">
      {count > 0 && t('status.selected', { count, formatted: format.count(count) })}
      {count > 0 && (
        <IconButton
          icon={X}
          label={t('status.clear')}
          onClick={clearSelectedFaces}
          data-testid="status-selection-clear"
        />
      )}
      {count > 0 && hidden > 0 && ' · '}
      {hidden > 0 && t('status.hidden', { count: hidden, formatted: format.count(hidden) })}
    </span>
  );
}

export const statusItem: StatusItem = { order: 10, Component: SelectionCount };
