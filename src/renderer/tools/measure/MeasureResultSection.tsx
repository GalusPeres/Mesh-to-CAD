import { useTranslation } from 'react-i18next';

import type { MeasureResult, MeasuredValue } from '@shared/protocol/generated/inspection';

import { useFormatter } from '../../i18n/useFormatter';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyValue } from '../../ui/PropertyRow/PropertyRow';
import styles from './MeasurePanel.module.css';

export interface MeasureResultSectionProps {
  computing: boolean;
  result: MeasureResult | null;
  /** Whether a second item is chosen (otherwise only diameters are shown). */
  second: boolean;
}

/** Values with the fit uncertainty in the secondary colour: "20,001 mm ± 0,002". */
export function MeasureResultSection({ computing, result, second }: MeasureResultSectionProps) {
  const { t } = useTranslation(['tools', 'common']);
  const format = useFormatter();

  // Fits of large faces are often better than the last shown digit; one more digit then
  // keeps "± 0,000" from suggesting an exact value.
  const spread = (sigma: number, decimals: number) =>
    format.number(sigma, sigma > 0 && sigma < 0.5 * 10 ** -decimals ? decimals + 1 : decimals);
  const value = (measured: MeasuredValue, text: (value: number) => string, decimals: number) => (
    <>
      {text(measured.value)}
      {measured.uncertainty !== null && (
        <span className={styles.uncertainty}> ± {spread(measured.uncertainty, decimals)}</span>
      )}
    </>
  );
  const length = (measured: MeasuredValue) => value(measured, (v) => format.length(v), 3);
  const angle = (measured: MeasuredValue) => value(measured, (v) => format.angle(v), 2);

  return (
    <PanelSection title={t('common:sections.result')}>
      {computing && <p className={styles.secondary}>{t('common:tool.computing')}</p>}
      {!computing && !result && <p className={styles.secondary}>{t('measure.empty')}</p>}
      {!computing && result && (
        <div data-testid="measure-result">
          {result.distance && result.distanceKind && (
            <PropertyValue
              label={t(`measure.distance.${result.distanceKind}`)}
              value={length(result.distance)}
            />
          )}
          {result.angleDeg && (
            <PropertyValue label={t('measure.angle')} value={angle(result.angleDeg)} />
          )}
          {result.diameterA && (
            <PropertyValue
              label={t(second ? 'measure.diameterFirst' : 'measure.diameter')}
              value={length(result.diameterA)}
            />
          )}
          {result.diameterB && (
            <PropertyValue label={t('measure.diameterSecond')} value={length(result.diameterB)} />
          )}
          {second && !result.distance && result.angleDeg && (
            <InlineMessage severity="info">
              {t('measure.notParallel', { angle: format.angle(result.angleDeg.value) })}
            </InlineMessage>
          )}
          {!second && !result.diameterA && (
            <p className={styles.secondary}>{t('measure.chooseSecond')}</p>
          )}
        </div>
      )}
    </PanelSection>
  );
}
