import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { Feature } from '@shared/protocol/generated/document-model';
import type { DocOp } from '@shared/protocol/generated/document-ops';
import type { FitParams } from '@shared/protocol/generated/feature-fit';
import type { PrimitiveKind } from '@shared/protocol/generated/fitting-primitives';
import { MIN_FIT_FACES } from '@shared/protocol/generated/limits';

import { featureNames } from '../../features/registry';
import { useFormatter } from '../../i18n/useFormatter';
import { describeError } from '../../kernel/describeError';
import { kernel } from '../../kernel/kernel';
import { replaceSelection, selectedFaces } from '../../selection/api';
import { currentRevision, documentStore, useDocument } from '../../state/documentStore';
import { settingsStore } from '../../state/settingsStore';
import { Checkbox } from '../../ui/Checkbox/Checkbox';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyValue } from '../../ui/PropertyRow/PropertyRow';
import { SnapList } from '../../ui/SnapList/SnapList';
import { ToolPanel } from '../framework/ToolPanel';
import { useCommit } from '../framework/hooks';
import type { ToolPanelProps } from '../framework/types';
import {
  EMPTY_DRAFT,
  type FitDraft,
  draftOf,
  featureInput,
  rejectSnap,
  selectionAfterFit,
  snapItems,
} from './fitDraft';
import { FitParameters } from './FitParameters';
import { FitResultList } from './FitResultList';
import styles from './FitPrimitivePanel.module.css';
import { TOOL_ID, useFitInput, useFitPreview } from './useFitPreview';

const NO_FEATURES: readonly Feature[] = [];

function storedParams(editTarget: string | null): FitParams | null {
  const feature = documentStore
    .getState()
    .snapshot?.document.features.find((item) => item.id === editTarget && item.type === 'fit');
  return feature ? (feature.params as unknown as FitParams) : null;
}

/**
 * Form einpassen: fits a plane, sphere, cylinder, cone or torus to the working
 * selection, shows the result against the project tolerance and commits a fit feature.
 */
export function FitPrimitivePanel({ editTarget, close }: ToolPanelProps) {
  const { t } = useTranslation(['tools', 'common', 'features']);
  const format = useFormatter();
  const stored = useMemo(() => storedParams(editTarget), [editTarget]);
  const [draft, setDraft] = useState<FitDraft>(() => (stored ? draftOf(stored) : EMPTY_DRAFT));
  const input = useFitInput(editTarget);
  const preview = useFitPreview(draft, input);
  const features = useDocument((state) => state.snapshot?.document.features ?? NO_FEATURES);

  const result =
    preview.status === 'ok'
      ? preview.result
      : preview.status === 'computing'
        ? preview.previous
        : null;
  const shown: PrimitiveKind =
    draft.kind === 'auto' ? (result?.primitive.type ?? 'plane') : draft.kind;

  const save = useCallback(
    async (keepOpen: boolean) => {
      const baseRevision = currentRevision();
      if (preview.status !== 'ok' || baseRevision === null || !input.scanKey) return;
      const { faces, scanKey, faceCount } = input;
      const params = featureInput(
        draft,
        faces,
        preview.result.primitive.type,
        stored?.sourceRegion ?? null,
      );
      const ops: DocOp[] = editTarget
        ? [{ type: 'updateFeature', id: editTarget, params }]
        : [{ type: 'addFeature', feature: { type: 'fit', params } }];
      await kernel().call('doc.apply', { baseRevision, ops, label: 'fit' }).result;
      const remaining = selectionAfterFit(
        selectedFaces(scanKey),
        faces,
        preview.result.used,
        !editTarget && settingsStore.getState().selection.clearAfterFit,
      );
      if (remaining) replaceSelection(scanKey, faceCount, remaining);
      if (!keepOpen) close();
    },
    [preview, input, draft, editTarget, stored, close],
  );
  const commit = useCommit(useCallback(() => save(false), [save]));
  const apply = useCommit(useCallback(() => save(true), [save]));

  const editingName = editTarget ? featureNames(features, t).get(editTarget) : undefined;
  const count = input.faces.length;
  const failure =
    commit.error ??
    apply.error ??
    input.loadError ??
    (preview.status === 'error' ? preview.error : null);

  return (
    <ToolPanel
      toolId={TOOL_ID}
      editingName={editingName}
      canCommit={preview.status === 'ok'}
      busy={commit.busy || apply.busy}
      onCommit={() => void commit.commit()}
      onCancel={close}
      onApply={editTarget ? undefined : () => void apply.commit()}
    >
      <PanelSection title={t('common:sections.input')}>
        {count >= MIN_FIT_FACES ? (
          <PropertyValue
            label={t('fitPrimitive.selection')}
            value={t('fitPrimitive.triangles', { count, formatted: format.count(count) })}
          />
        ) : (
          <InlineMessage severity="info">
            {count === 0
              ? t('fitPrimitive.selectionEmpty', { min: MIN_FIT_FACES })
              : t('fitPrimitive.selectionTooSmall', {
                  count,
                  formatted: format.count(count),
                  min: MIN_FIT_FACES,
                })}
          </InlineMessage>
        )}
      </PanelSection>
      <PanelSection title={t('common:sections.parameters')}>
        <FitParameters
          draft={draft}
          onChange={setDraft}
          shown={shown}
          primitive={result?.primitive ?? null}
          alternatives={result?.alternatives ?? []}
          editTarget={editTarget}
        />
      </PanelSection>
      <PanelSection title={t('common:sections.options')}>
        <Checkbox
          checked={draft.robust}
          label={t('fitPrimitive.robust')}
          testId="fit-robust"
          onChange={(robust) => setDraft({ ...draft, robust })}
        />
        <Checkbox
          checked={draft.snap}
          label={t('fitPrimitive.snap')}
          onChange={(snap) => setDraft({ ...draft, snap })}
        />
      </PanelSection>
      <PanelSection title={t('common:sections.result')}>
        {preview.status === 'computing' && (
          <p className={styles.computing}>{t('common:tool.computing')}</p>
        )}
        {failure && (
          <InlineMessage severity="error" details={failure.details}>
            {describeError(failure, t)}
          </InlineMessage>
        )}
        {result && preview.status !== 'error' && (
          <div className={preview.status === 'computing' ? styles.stale : undefined}>
            <FitResultList values={result.stats} />
            <SnapList
              items={snapItems(result.snaps, result.primitive.type, format, t)}
              onRemove={(id) =>
                setDraft(rejectSnap(draft, id as FitDraft['rejectedSnaps'][number]))
              }
            />
          </div>
        )}
      </PanelSection>
    </ToolPanel>
  );
}
