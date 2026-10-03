import * as RadixDialog from '@radix-ui/react-dialog';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';
import type { SnapUnits } from '@shared/protocol/generated/snapping';

import { useFormatter } from '../i18n/useFormatter';
import type { KernelFailure } from '../kernel/KernelFailure';
import { describeError } from '../kernel/describeError';
import { kernel } from '../kernel/kernel';
import { toFailure } from '../tools/framework/hooks';
import { Button } from '../ui/Button/Button';
import { InlineMessage } from '../ui/InlineMessage/InlineMessage';
import { NumberField } from '../ui/NumberField/NumberField';
import { PropertyRow, PropertyValue } from '../ui/PropertyRow/PropertyRow';
import { SegmentedControl } from '../ui/SegmentedControl/SegmentedControl';
import {
  MAX_TOLERANCE_MM,
  MIN_TOLERANCE_MM,
  type ToleranceDraft,
  clampTolerance,
  draftChanged,
  effectiveNoise,
  isTooTightForNoise,
  proposedTolerance,
  settingsOp,
} from './toleranceModel';
import styles from './TolerancePopover.module.css';

export interface TolerancePopoverProps {
  snapshot: DocumentSnapshot;
  /** Fixed position above the status item, in CSS pixels from the window edges. */
  position: { right: number; bottom: number };
  trigger: HTMLElement | null;
  onClose: () => void;
}

/** Value, scan noise, proposal and snap units; applying them is one undoable revision. */
export function TolerancePopover({ snapshot, position, trigger, onClose }: TolerancePopoverProps) {
  const { t } = useTranslation(['inspection', 'common']);
  const format = useFormatter();
  const settings = snapshot.document.settings;
  const noise = effectiveNoise(settings, snapshot.document.scan?.noise ?? null);
  const proposal = proposedTolerance(noise);
  const [draft, setDraft] = useState<ToleranceDraft>({
    tolerance: settings.tolerance,
    snapUnits: settings.snapUnits,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<KernelFailure | null>(null);

  const apply = async () => {
    if (!draftChanged(settings, draft)) {
      onClose();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await kernel().call('doc.apply', {
        baseRevision: snapshot.revision,
        ops: [settingsOp(settings, draft)],
        label: 'settings',
      }).result;
      onClose();
    } catch (failure) {
      setError(toFailure(failure));
    } finally {
      setBusy(false);
    }
  };

  const snapSegments: { value: SnapUnits; label: string }[] = [
    { value: 'metric', label: t('tolerance.metric') },
    { value: 'inch', label: t('tolerance.inch') },
  ];

  return (
    <RadixDialog.Root open modal={false} onOpenChange={(open) => !open && onClose()}>
      <RadixDialog.Portal>
        <RadixDialog.Content
          className={styles.popover}
          style={{ right: position.right, bottom: position.bottom }}
          aria-describedby={undefined}
          data-testid="tolerance-popover"
          onInteractOutside={(event) => {
            // The status item toggles the popover itself.
            if (trigger?.contains(event.target as Node)) event.preventDefault();
          }}
        >
          <RadixDialog.Title className={styles.title}>{t('tolerance.title')}</RadixDialog.Title>
          <PropertyRow label={t('tolerance.value')} htmlFor="project-tolerance">
            <NumberField
              id="project-tolerance"
              value={draft.tolerance}
              min={MIN_TOLERANCE_MM}
              max={MAX_TOLERANCE_MM}
              step={0.01}
              onCommit={(value) => setDraft({ ...draft, tolerance: clampTolerance(value) })}
            />
          </PropertyRow>
          <PropertyValue
            label={t('tolerance.noise')}
            value={noise === null ? t('tolerance.noiseUnknown') : format.length(noise)}
          />
          {proposal !== null && (
            <div className={styles.proposal}>
              <span>{t('tolerance.proposal', { value: format.length(proposal) })}</span>
              <Button
                variant="ghost"
                disabled={proposal === draft.tolerance}
                data-testid="tolerance-use-proposal"
                onClick={() => setDraft({ ...draft, tolerance: proposal })}
              >
                {t('tolerance.useProposal')}
              </Button>
            </div>
          )}
          <PropertyRow label={t('tolerance.snapUnits')}>
            <SegmentedControl
              value={draft.snapUnits}
              segments={snapSegments}
              ariaLabel={t('tolerance.snapUnits')}
              onChange={(snapUnits) => setDraft({ ...draft, snapUnits })}
            />
          </PropertyRow>
          {isTooTightForNoise(draft.tolerance, noise) && (
            <InlineMessage severity="warning">{t('tolerance.belowNoise')}</InlineMessage>
          )}
          <p className={styles.hint}>{t('tolerance.hint')}</p>
          {error && (
            <InlineMessage severity="error" details={error.details}>
              {describeError(error, t)}
            </InlineMessage>
          )}
          <div className={styles.footer}>
            <Button
              variant="primary"
              disabled={busy}
              data-testid="tolerance-apply"
              onClick={() => void apply()}
            >
              {t('tolerance.apply')}
            </Button>
            <Button onClick={onClose}>{t('common:actions.cancel')}</Button>
          </div>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
