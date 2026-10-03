import { ChevronDown, ChevronUp } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useFormatter } from '../i18n/useFormatter';
import { useDocument } from '../state/documentStore';
import { useView } from '../state/viewStore';
import { IconButton } from '../ui/IconButton/IconButton';
import styles from './DeviationLegend.module.css';
import { legendLayout, signedNumber } from './deviationModel';
import { displayRange, setLegendCollapsed, useDeviation } from './deviationStore';

const BAR_HEIGHT_PX = 240;
const STAT_DECIMALS = 3;

/**
 * The legend of docs/DESIGN.md 6.6: the bar with a tick at every band boundary,
 * the bracketed tolerance band, out-of-range and no-data swatches, and the statistics.
 */
export function DeviationLegend() {
  const { t } = useTranslation('inspection');
  const format = useFormatter();
  const shown = useView((state) => state.deviationVisible || state.displayMode === 'deviation');
  const state = useDeviation((current) => current);
  const snapshot = useDocument((current) => current.snapshot);
  const summary = state.summary;
  if (!shown || !summary || !snapshot?.document.scan) return null;

  const tolerance = snapshot.document.settings.tolerance;
  const range = displayRange(state, tolerance);
  if (range === null) return null;
  const layout = legendLayout(tolerance, range, state.scheme, format);
  const unit = BAR_HEIGHT_PX / layout.bands.reduce((total, band) => total + band.weight, 0);
  const boundaries = layout.bands.reduce<number[]>(
    (edges, band) => [...edges, (edges.at(-1) ?? 0) + band.weight * unit],
    [0],
  );
  const toleranceTop = boundaries[3] ?? 0;
  const toleranceBottom = boundaries[4] ?? 0;
  const stats = summary.stats;
  const collapsed = state.legendCollapsed;
  const number = (value: number | null) =>
    value === null ? '–' : format.number(value, STAT_DECIMALS);
  const signed = (value: number | null) =>
    value === null ? '–' : signedNumber(value, STAT_DECIMALS, format);

  return (
    <section
      className={styles.legend}
      aria-label={t('deviation.legendTitle')}
      data-testid="deviation-legend"
    >
      <header className={styles.header}>
        {!collapsed && (
          <h3 className={styles.title} title={t('deviation.legendTooltip')}>
            {t('deviation.legendTitle')}
          </h3>
        )}
        <IconButton
          icon={collapsed ? ChevronDown : ChevronUp}
          label={t(collapsed ? 'deviation.expand' : 'deviation.collapse')}
          onClick={() => setLegendCollapsed(!collapsed)}
        />
      </header>
      <div className={styles.scale} style={{ height: BAR_HEIGHT_PX }}>
        <div className={styles.bar} title={t('deviation.legendTooltip')}>
          {layout.bands.map((band, index) => (
            <div
              key={index}
              className={styles.band}
              style={{ height: band.weight * unit, backgroundColor: band.color }}
            />
          ))}
        </div>
        {!collapsed && (
          <>
            <div className={styles.ticks} aria-hidden>
              {layout.ticks.map((tick, index) => (
                <span key={index} className={styles.tick} style={{ top: boundaries[index] }}>
                  {tick}
                </span>
              ))}
            </div>
            <div
              className={styles.bracket}
              style={{ top: toleranceTop, height: toleranceBottom - toleranceTop }}
            >
              <span className={styles.bracketLabel}>
                {t('deviation.toleranceBand', {
                  value: format.number(tolerance, layout.decimals),
                })}
              </span>
            </div>
          </>
        )}
      </div>
      {!collapsed && (
        <>
          <div className={styles.swatches}>
            <span className={styles.swatchItem}>
              <span className={styles.splitSwatch}>
                <span style={{ backgroundColor: layout.above }} />
                <span style={{ backgroundColor: layout.below }} />
              </span>
              {t('deviation.outOfRange')}
            </span>
            <span className={styles.swatchItem}>
              <span className={styles.swatch} style={{ backgroundColor: layout.noData }} />
              {t('deviation.noData')}
            </span>
          </div>
          <dl className={styles.stats} data-testid="deviation-legend-stats">
            <dt>{t('deviation.mean')}</dt>
            <dd>{signed(stats.mean)}</dd>
            <dt>{t('deviation.sigma')}</dt>
            <dd>{number(stats.std)}</dd>
            <dt>{t('deviation.rms')}</dt>
            <dd>{number(stats.rms)}</dd>
            <dd className={styles.share}>
              {stats.within === null
                ? '–'
                : t('deviation.withinShare', { share: format.percent(stats.within) })}
            </dd>
          </dl>
          <p className={styles.max}>
            {t('deviation.max', { above: signed(stats.max), below: signed(stats.min) })}
          </p>
          {summary.revision !== snapshot.revision && (
            <p className={styles.stale}>{t('deviation.stale')}</p>
          )}
        </>
      )}
    </section>
  );
}
