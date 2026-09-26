import { useTranslation } from 'react-i18next';

import { useFormatter } from '../../i18n/useFormatter';
import { useDocument } from '../../state/documentStore';
import type { StatusItem } from './types';

function FaceCount() {
  const { t } = useTranslation();
  const format = useFormatter();
  const count = useDocument((state) => state.snapshot?.document.scan?.faceCount ?? null);
  if (count === null) return null;
  return (
    <span data-testid="status-faces">
      {t('status.faces', { count, formatted: format.count(count) })}
    </span>
  );
}

export const statusItem: StatusItem = { order: 20, Component: FaceCount };
