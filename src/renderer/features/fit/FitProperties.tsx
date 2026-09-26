import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { FitParams } from '@shared/protocol/generated/feature-fit';

import { useFormatter } from '../../i18n/useFormatter';
import { i18n } from '../../i18n';
import { KernelFailure } from '../../kernel/KernelFailure';
import { describeError } from '../../kernel/describeError';
import { kernel } from '../../kernel/kernel';
import { currentRevision, useDocument } from '../../state/documentStore';
import { showMessage } from '../../state/messageStore';
import { useTools } from '../../state/toolStore';
import { FitResultList } from '../../tools/fit-primitive/FitResultList';
import { FitValueField } from '../../tools/fit-primitive/FitValueField';
import {
  type FitDraft,
  VALUES_BY_KIND,
  draftOf,
  featureInput,
  fixValue,
  isFixed,
  rejectSnap,
  releaseValue,
  snapItems,
} from '../../tools/fit-primitive/fitDraft';
import { SnapList } from '../../ui/SnapList/SnapList';
import { appliedSnaps, resultValues } from './fitStats';

/** Store a changed draft: the stored triangles are sent again with the new parameters. */
async function updateFit(featureId: string, params: FitParams, draft: FitDraft): Promise<void> {
  const baseRevision = currentRevision();
  if (baseRevision === null) return;
  try {
    const { faces } = await kernel().call('fit.featureFaces', { featureId }).result;
    const input = featureInput(draft, faces, params.kind, params.sourceRegion);
    const ops = [{ type: 'updateFeature' as const, id: featureId, params: input }];
    await kernel().call('doc.apply', { baseRevision, ops, label: 'fit' }).result;
  } catch (error) {
    if (!(error instanceof KernelFailure)) throw error;
    showMessage('error', describeError(error, i18n.t), error.details);
  }
}

/**
 * Result and values of a selected fit. Values can be fixed or released here and
 * snaps removed; each change is one feature edit (docs/DESIGN.md 3.4).
 */
export function FitProperties({ featureId }: { featureId: string }) {
  const { t } = useTranslation(['tools', 'features']);
  const format = useFormatter();
  const feature = useDocument((state) =>
    state.snapshot?.document.features.find((item) => item.id === featureId),
  );
  const status = useDocument((state) => state.snapshot?.status.features[featureId]);
  const toolOpen = useTools((state) => state.activeToolId !== null);
  const [busy, setBusy] = useState(false);
  if (!feature || feature.type !== 'fit') return null;
  const params = feature.params as unknown as FitParams;
  const draft = draftOf(params);
  const stats = status?.stats ?? {};
  const result = resultValues(status);

  const change = (next: FitDraft) => {
    setBusy(true);
    void updateFit(featureId, params, next).finally(() => setBusy(false));
  };

  return (
    <div data-testid="fit-properties">
      {VALUES_BY_KIND[params.kind].map((name) => {
        const fixed = params.fixed[name];
        const computed = stats[name];
        return (
          <FitValueField
            key={name}
            label={t(`fitPrimitive.values.${name}`)}
            value={fixed ?? (typeof computed === 'number' ? computed : null)}
            fixed={isFixed(draft, name)}
            kind={name === 'halfAngleDeg' ? 'angle' : 'length'}
            min={name === 'offset' ? undefined : 0}
            disabled={busy || toolOpen}
            onFix={(value) => change(fixValue(draft, params.kind, name, value))}
            onRelease={() => change(releaseValue(draft, name))}
          />
        );
      })}
      {result && <FitResultList values={result} />}
      <SnapList
        items={snapItems(appliedSnaps(stats), params.kind, format, t)}
        onRemove={(id) => {
          if (!busy && !toolOpen)
            change(rejectSnap(draft, id as FitDraft['rejectedSnaps'][number]));
        }}
      />
    </div>
  );
}
