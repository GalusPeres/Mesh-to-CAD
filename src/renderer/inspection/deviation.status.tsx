import { Check, TriangleAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { StatusItem } from '../app/status/types';
import { useFormatter } from '../i18n/useFormatter';
import { useDocument } from '../state/documentStore';
import { useView } from '../state/viewStore';
import styles from './DeviationStatus.module.css';
import { useDeviation } from './deviationStore';

/** "Abweichung: 97,7 % in Toleranz" while the colour map is shown. */
function DeviationStatus() {
  const { t } = useTranslation('inspection');
  const format = useFormatter();
  const shown = useView((state) => state.deviationVisible || state.displayMode === 'deviation');
  const summary = useDeviation((state) => state.summary);
  const revision = useDocument((state) => state.snapshot?.revision ?? null);
  if (!shown || !summary || summary.stats.within === null) return null;
  const share = format.percent(summary.stats.within);
  const stale = summary.revision !== revision;
  const Icon = summary.stats.passed ? Check : TriangleAlert;
  return (
    <span className={styles.item} data-testid="status-deviation">
      <Icon
        size={12}
        className={summary.stats.passed ? styles.passed : styles.failed}
        aria-hidden
      />
      {t(stale ? 'status.deviationStale' : 'status.deviation', { share })}
    </span>
  );
}

export const statusItem: StatusItem = { order: 40, Component: DeviationStatus };
