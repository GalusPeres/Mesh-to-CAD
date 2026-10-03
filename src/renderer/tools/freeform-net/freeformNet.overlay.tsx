import { Grid2x2Check } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { ViewportOverlay } from '../../app/extensions';
import { classNames } from '../../lib/classNames';
import styles from './FreeformNetPanel.module.css';
import { useNetSession } from './netSession';

/** While the freeform-net tool is open: which tool and mode, at the top left of the view. */
function FreeformNetMode() {
  const { t } = useTranslation('tools');
  const mode = useNetSession((state) => state.mode);
  if (!mode) return null;
  return (
    <div
      className={classNames(styles.mode, mode !== 'edit' && styles.placing)}
      data-testid="freeform-net-mode"
    >
      <Grid2x2Check size={16} aria-hidden />
      <span>{t('freeformNet.label')}</span>
      <span className={styles.modeName}>{t(`freeformNet.modes.${mode}`)}</span>
    </div>
  );
}

export const overlay: ViewportOverlay = {
  anchor: 'top-left',
  order: 10,
  Component: FreeformNetMode,
};
