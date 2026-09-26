import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { ReferenceParams } from '@shared/protocol/generated/feature-reference';

import { i18n } from '../../i18n';
import { KernelFailure } from '../../kernel/KernelFailure';
import { describeError } from '../../kernel/describeError';
import { kernel } from '../../kernel/kernel';
import { currentRevision, useDocument } from '../../state/documentStore';
import { showMessage } from '../../state/messageStore';
import { useTools } from '../../state/toolStore';
import { NumberField } from '../../ui/NumberField/NumberField';
import { PropertyRow } from '../../ui/PropertyRow/PropertyRow';

async function updateReference(featureId: string, params: ReferenceParams): Promise<void> {
  const baseRevision = currentRevision();
  if (baseRevision === null) return;
  const ops = [{ type: 'updateFeature' as const, id: featureId, params: { ...params } }];
  try {
    await kernel().call('doc.apply', { baseRevision, ops, label: 'reference' }).result;
  } catch (error) {
    if (!(error instanceof KernelFailure)) throw error;
    showMessage('error', describeError(error, i18n.t), error.details);
  }
}

/** The editable value of an offset plane or a plane through an axis. */
export function ReferenceProperties({ featureId }: { featureId: string }) {
  const { t } = useTranslation('tools');
  const feature = useDocument((state) =>
    state.snapshot?.document.features.find((item) => item.id === featureId),
  );
  const toolOpen = useTools((state) => state.activeToolId !== null);
  const [busy, setBusy] = useState(false);
  if (!feature || feature.type !== 'reference') return null;
  const params = feature.params as unknown as ReferenceParams;
  const definition = params.definition;
  const change = (next: ReferenceParams) => {
    setBusy(true);
    void updateReference(featureId, next).finally(() => setBusy(false));
  };

  if (definition.type === 'offsetPlane') {
    return (
      <PropertyRow label={t('referenceGeometry.distance')} htmlFor={`${featureId}-distance`}>
        <NumberField
          id={`${featureId}-distance`}
          value={definition.distance}
          kind="length"
          disabled={busy || toolOpen}
          onCommit={(distance) => change({ definition: { ...definition, distance } })}
        />
      </PropertyRow>
    );
  }
  if (definition.type === 'planeThroughAxis') {
    return (
      <PropertyRow label={t('referenceGeometry.angle')} htmlFor={`${featureId}-angle`}>
        <NumberField
          id={`${featureId}-angle`}
          value={definition.angleDeg}
          kind="angle"
          step={15}
          disabled={busy || toolOpen}
          onCommit={(angleDeg) => change({ definition: { ...definition, angleDeg } })}
        />
      </PropertyRow>
    );
  }
  return null;
}
