import { Check, TriangleAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { FreeformPreviewResult } from '@shared/protocol/generated/freeform';

import { useFormatter } from '../../i18n/useFormatter';
import { PropertyValue } from '../../ui/PropertyRow/PropertyRow';
import styles from './FreeformPatchPanel.module.css';

const KEY = 'tools:freeformPatch.result';

/**
 * The result block of docs/DESIGN.md 5.3 for a patch: scan noise, RMS, maximum, share
 * within the tolerance with the verdict (the single 95 % rule), triangles, and the
 * spans and normal spread of the height field.
 */
export function PatchResultList({
  result,
  tolerance,
}: {
  result: FreeformPreviewResult;
  tolerance: number;
}) {
  const { t } = useTranslation();
  const format = useFormatter();
  const Verdict = result.passed ? Check : TriangleAlert;
  return (
    <div data-testid="freeform-patch-result">
      <PropertyValue label={t(`${KEY}.noise`)} value={format.length(result.noise)} />
      <PropertyValue label={t(`${KEY}.rms`)} value={format.length(result.rms)} />
      <PropertyValue label={t(`${KEY}.max`)} value={format.length(result.maxAbs)} />
      <PropertyValue
        label={t(`${KEY}.withinTolerance`)}
        value={
          <span className={styles.verdict}>
            {format.percent(result.withinTolerance)}
            <Verdict
              size={12}
              role="img"
              aria-label={t(`${KEY}.${result.passed ? 'pass' : 'fail'}`)}
              className={result.passed ? styles.pass : styles.fail}
            />
          </span>
        }
      />
      <PropertyValue label={t(`${KEY}.faces`)} value={format.count(result.faceCount)} />
      <PropertyValue
        label={t(`${KEY}.spans`)}
        value={t(`${KEY}.spansValue`, { u: result.spans[0], v: result.spans[1] })}
      />
      <PropertyValue
        label={t(`${KEY}.normalSpread`)}
        value={format.angle(result.normalSpreadDeg)}
      />
      {!result.passed && (
        <p className={styles.message} role="status">
          <TriangleAlert size={16} aria-hidden className={styles.fail} />
          <span>
            {t(`${KEY}.poorFit`, {
              share: format.number(result.withinTolerance * 100, 1),
              tolerance: format.length(tolerance),
            })}
          </span>
        </p>
      )}
    </div>
  );
}
