import { Check, TriangleAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useFormatter } from '../../i18n/useFormatter';
import { PropertyValue } from '../../ui/PropertyRow/PropertyRow';
import styles from './FitResultList.module.css';

export interface FitResultValues {
  noise: number;
  rms: number;
  maxDeviation: number;
  withinTolerance: number;
  tolerance: number;
  passed: boolean;
  faceCount: number;
  excludedFaces: number;
}

/**
 * The result block of every fit (docs/DESIGN.md 5.3): scan noise, RMS, maximum,
 * share within tolerance with the verdict, and the triangles used. The verdict
 * is the single 95 % rule; RMS and maximum are information only.
 */
export function FitResultList({ values }: { values: FitResultValues }) {
  const { t } = useTranslation('tools');
  const format = useFormatter();
  const Verdict = values.passed ? Check : TriangleAlert;
  const verdictLabel = t(values.passed ? 'fitPrimitive.result.pass' : 'fitPrimitive.result.fail');
  return (
    <div data-testid="fit-result">
      <PropertyValue label={t('fitPrimitive.result.noise')} value={format.length(values.noise)} />
      <PropertyValue label={t('fitPrimitive.result.rms')} value={format.length(values.rms)} />
      <PropertyValue
        label={t('fitPrimitive.result.max')}
        value={format.length(values.maxDeviation)}
      />
      <PropertyValue
        label={t('fitPrimitive.result.withinTolerance')}
        value={
          <span className={styles.verdict}>
            {format.percent(values.withinTolerance)}
            <Verdict
              size={12}
              role="img"
              aria-label={verdictLabel}
              className={values.passed ? styles.pass : styles.fail}
            />
          </span>
        }
      />
      <PropertyValue
        label={t('fitPrimitive.result.faces')}
        value={format.count(values.faceCount)}
      />
      {values.excludedFaces > 0 && (
        <PropertyValue
          label={t('fitPrimitive.result.excluded')}
          value={format.count(values.excludedFaces)}
        />
      )}
      {!values.passed && (
        <p className={styles.message} role="status">
          <TriangleAlert size={16} aria-hidden className={styles.fail} />
          <span>
            {t('fitPrimitive.result.poorFit', {
              share: format.number(values.withinTolerance * 100, 1),
              tolerance: format.length(values.tolerance),
            })}
          </span>
        </p>
      )}
    </div>
  );
}
