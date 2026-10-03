import { X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { SketchParams } from '@shared/protocol/generated/sketch-params';

import { useFormatter } from '../../i18n/useFormatter';
import { describeError } from '../../kernel/describeError';
import type { KernelFailure } from '../../kernel/KernelFailure';
import { IconButton } from '../../ui/IconButton/IconButton';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyValue } from '../../ui/PropertyRow/PropertyRow';
import { SnapList } from '../../ui/SnapList/SnapList';
import { constraintText, profileSeverity, profileText, snapItem } from './describe';
import { removeConstraint, removeSnap } from './edits';
import styles from './SketchPanel.module.css';
import type { FitState } from './useSketchDraft';

const K = 'sectionSketch';

interface SketchResultProps {
  sketch: SketchParams;
  labels: ReadonlyMap<string, string>;
  /** State of the current draft, or of an earlier version while the refit runs. */
  state: FitState | null;
  current: boolean;
  error: KernelFailure | null;
  onEdit: (next: SketchParams) => void;
}

/** Ergebnis: profile state, fit quality, removable constraints and snapped values. */
export function SketchResult({ sketch, labels, state, current, error, onEdit }: SketchResultProps) {
  const { t } = useTranslation(['tools', 'common']);
  const format = useFormatter();
  const judged = state?.fits.filter((fit) => fit.passed !== null) ?? [];
  const passed = judged.filter((fit) => fit.passed).length;
  return (
    <PanelSection title={t('common:sections.result')}>
      <InlineMessage severity={profileSeverity(state?.profile ?? null)}>
        <span data-testid="sketch-profile">
          {profileText(state?.profile ?? null, sketch.entities.length, t)}
        </span>
      </InlineMessage>
      {!current && sketch.entities.length > 0 && (
        <p className={styles.hint}>{t('common:tool.computing')}</p>
      )}
      {state && (
        <>
          <PropertyValue label={t(`${K}.result.noise`)} value={format.length(state.noise)} />
          <PropertyValue label={t(`${K}.tolerance`)} value={`±${format.length(state.tolerance)}`} />
          <PropertyValue
            label={t(`${K}.result.entitiesInTolerance`)}
            value={t(`${K}.result.entitiesInToleranceValue`, { passed, total: judged.length })}
          />
        </>
      )}
      {error && (
        <InlineMessage severity="error" details={error.details}>
          {describeError(error, t)}
        </InlineMessage>
      )}
      {sketch.constraints.length > 0 && (
        <>
          <h3 className={styles.subheading}>{t(`${K}.constraints`)}</h3>
          <ul className={styles.list} aria-label={t(`${K}.constraints`)}>
            {sketch.constraints.map((constraint, index) => {
              const text = constraintText(constraint, labels, t);
              return (
                <li
                  key={`${constraint.kind}:${constraint.refs.join(',')}`}
                  className={styles.constraint}
                >
                  <span>{text}</span>
                  <IconButton
                    icon={X}
                    label={t(`${K}.removeConstraint`, { name: text })}
                    onClick={() => onEdit(removeConstraint(sketch, index))}
                  />
                </li>
              );
            })}
          </ul>
        </>
      )}
      {sketch.snaps.length > 0 && <h3 className={styles.subheading}>{t(`${K}.snaps`)}</h3>}
      <SnapList
        items={sketch.snaps.map((snap) => snapItem(snap, labels, format, t))}
        onRemove={(id) => onEdit(removeSnap(sketch, id))}
      />
    </PanelSection>
  );
}
