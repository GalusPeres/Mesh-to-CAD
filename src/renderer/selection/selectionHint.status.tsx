import { useTranslation } from 'react-i18next';

import type { StatusItem } from '../app/status/types';
import { useFormatter } from '../i18n/useFormatter';
import { useTools } from '../state/toolStore';
import { useGesture } from './gestureStore';
import { isSelectionModeId } from './selectionRuntime';

/** What the mouse and Ctrl do in the active selection mode (docs/DESIGN.md 7.3). */
function SelectionHint() {
  const { t } = useTranslation(['selection', 'panels']);
  const format = useFormatter();
  const mode = useTools((state) => state.selectionMode);
  const removing = useGesture((state) => state.removing);
  const smartBusy = useGesture((state) => state.smartBusy);
  const preview = useGesture((state) => state.smartPreview);
  if (!isSelectionModeId(mode)) return null;
  const smart =
    mode !== 'select-smart'
      ? null
      : smartBusy
        ? t('hints.smartBusy')
        : preview
          ? [
              t('hints.smartFound', {
                count: preview.faces,
                formatted: format.count(preview.faces),
              }),
              preview.kind ? t(`panels:regionKind.${preview.kind}`) : null,
              preview.rms !== null ? `RMS ${format.length(preview.rms)}` : null,
            ]
              .filter(Boolean)
              .join(' · ')
          : null;
  return (
    <span data-testid="status-selection-hint">
      {t(`hints.${mode}${removing ? 'Removing' : ''}`)}
      {smart && ` · ${smart}`}
    </span>
  );
}

export const statusItem: StatusItem = { order: 5, Component: SelectionHint };
