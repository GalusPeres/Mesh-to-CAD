import { Check, FlipHorizontal2, FlipVertical2, RotateCw, TriangleAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { AlignmentAdjust } from '@shared/protocol/generated/document-model';

import { useFormatter } from '../../i18n/useFormatter';
import { describeError } from '../../kernel/describeError';
import type { KernelFailure } from '../../kernel/KernelFailure';
import { Button } from '../../ui/Button/Button';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyValue } from '../../ui/PropertyRow/PropertyRow';
import type { ResultOf } from '../../kernel/KernelClient';
import type { PreviewState } from '../framework/hooks';
import { type AdjustAction, rotationDegrees } from './adjust';
import styles from './AlignmentPanel.module.css';

const KEY = 'tools:alignAuto';

/** Largest-plane tilt below which the alignment counts as flat. */
export const FLAT_TILT_DEG = 0.05;

export type AlignmentPreview = PreviewState<ResultOf<'alignment.preview'>>;

interface AdjustProps {
  adjust: AlignmentAdjust;
  onAdjust: (action: AdjustAction) => void;
}

/** Turn over, reverse X, rotate by 90° (the adjustment every alignment method offers). */
export function AdjustControls({ adjust, onAdjust }: AdjustProps) {
  const { t } = useTranslation();
  const format = useFormatter();
  const toggle = (pressed: boolean) => (pressed ? styles.pressed : undefined);
  return (
    <>
      <div className={styles.actions} role="group" aria-label={t(`${KEY}.adjust`)}>
        <Button
          aria-pressed={adjust.flipZ}
          className={toggle(adjust.flipZ)}
          data-testid="align-flip-z"
          onClick={() => onAdjust('flipZ')}
        >
          <FlipVertical2 size={16} aria-hidden /> {t(`${KEY}.flipZ`)}
        </Button>
        <Button
          aria-pressed={adjust.flipX}
          className={toggle(adjust.flipX)}
          data-testid="align-flip-x"
          onClick={() => onAdjust('flipX')}
        >
          <FlipHorizontal2 size={16} aria-hidden /> {t(`${KEY}.flipX`)}
        </Button>
        <Button data-testid="align-rotate" onClick={() => onAdjust('rotate')}>
          <RotateCw size={16} aria-hidden /> {t(`${KEY}.rotate`)}
        </Button>
      </div>
      <PropertyValue label={t(`${KEY}.rotation`)} value={format.angle(rotationDegrees(adjust))} />
    </>
  );
}

interface ResultProps {
  preview: AlignmentPreview;
  commitError: KernelFailure | null;
  /** Shown instead of the preview state while inputs are missing. */
  idleText: string;
}

/** Remaining tilt of the largest plane, fallbacks and errors (the _Ergebnis_ section). */
export function AlignmentResult({ preview, commitError, idleText }: ResultProps) {
  const { t } = useTranslation();
  const format = useFormatter();
  const result = preview.status === 'ok' ? preview.result : null;
  const largest = result?.largestPlane ?? null;
  const flat = largest !== null && largest.tiltDeg <= FLAT_TILT_DEG;
  const Verdict = flat ? Check : TriangleAlert;
  return (
    <PanelSection title={t('common:sections.result')}>
      {preview.status === 'idle' && <p className={styles.hint}>{idleText}</p>}
      {preview.status === 'computing' && (
        <p className={styles.hint}>{t('common:tool.computing')}</p>
      )}
      {preview.status === 'error' && (
        <InlineMessage severity="error" details={preview.error.details}>
          {describeError(preview.error, t)}
        </InlineMessage>
      )}
      {largest && (
        <PropertyValue
          label={t(`${KEY}.result.largestPlane`)}
          value={
            <span className={styles.verdict} data-testid="align-tilt">
              {t(`${KEY}.result.tilt`, {
                angle: format.angle(largest.tiltDeg),
                plane: largest.plane,
              })}
              <Verdict
                size={12}
                role="img"
                aria-label={t(`${KEY}.result.${flat ? 'flat' : 'tilted'}`)}
                className={flat ? styles.pass : styles.warn}
              />
            </span>
          }
        />
      )}
      {result && (
        <PropertyValue label={t(`${KEY}.result.planes`)} value={format.count(result.planeCount)} />
      )}
      {result?.issues.map((code) => (
        <InlineMessage key={code} severity="info">
          {t(`issues:${code}`)}
        </InlineMessage>
      ))}
      {commitError && (
        <InlineMessage severity="error" details={commitError.details}>
          {describeError(commitError, t)}
        </InlineMessage>
      )}
    </PanelSection>
  );
}
