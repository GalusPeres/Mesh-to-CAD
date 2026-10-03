import { Check, TriangleAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';

import { useFormatter } from '../../i18n/useFormatter';
import type { DeviationSummary } from '../../inspection/deviationStore';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyValue } from '../../ui/PropertyRow/PropertyRow';
import styles from './DeviationPanel.module.css';

export interface DeviationResultSectionProps {
  computing: boolean;
  summary: DeviationSummary | null;
  snapshot: DocumentSnapshot;
}

/** Scan noise, mean, sigma, RMS, extremes and the verdict (docs/DESIGN.md 5.3). */
export function DeviationResultSection({
  computing,
  summary,
  snapshot,
}: DeviationResultSectionProps) {
  const { t } = useTranslation(['tools', 'common']);
  const format = useFormatter();
  const scan = snapshot.document.scan;
  const tolerance = snapshot.document.settings.tolerance;
  const stats = summary?.stats;
  const length = (value: number | null | undefined, signed = false) =>
    value === null || value === undefined ? '–' : format.length(value, { signed });

  return (
    <PanelSection title={t('common:sections.result')}>
      {computing && <p className={styles.computing}>{t('common:tool.computing')}</p>}
      {!computing && stats && (
        <div data-testid="deviation-result">
          <PropertyValue
            label={t('deviation.result.noise')}
            value={length(snapshot.document.settings.noiseOverride ?? scan?.noise)}
          />
          <PropertyValue label={t('deviation.result.mean')} value={length(stats.mean, true)} />
          <PropertyValue label={t('deviation.result.std')} value={length(stats.std)} />
          <PropertyValue label={t('deviation.result.rms')} value={length(stats.rms)} />
          <PropertyValue
            label={t('deviation.result.max')}
            value={`${length(stats.max, true)} / ${length(stats.min, true)}`}
          />
          <PropertyValue
            label={t('deviation.result.within')}
            value={
              <span className={styles.verdict}>
                {stats.within === null ? '–' : format.percent(stats.within)}
                {stats.passed ? (
                  <Check size={12} className={styles.passed} aria-label={t('deviation.passed')} />
                ) : (
                  <TriangleAlert
                    size={12}
                    className={styles.failed}
                    aria-label={t('deviation.failed')}
                  />
                )}
              </span>
            }
          />
          <PropertyValue label={t('deviation.result.points')} value={format.count(stats.count)} />
          {scan && (
            <PropertyValue
              label={t('deviation.result.noData')}
              value={format.count(Math.max(0, scan.vertexCount - stats.count))}
            />
          )}
          {!stats.passed && stats.within !== null && (
            <InlineMessage severity="warning">
              {t('deviation.verdictFailed', {
                share: format.percent(stats.within),
                tolerance: format.length(tolerance),
              })}
            </InlineMessage>
          )}
        </div>
      )}
    </PanelSection>
  );
}
