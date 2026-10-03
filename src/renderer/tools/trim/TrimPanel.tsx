import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type {
  TrimParams,
  TrimParamsInput,
  TrimTool,
} from '@shared/protocol/generated/feature-trim';

import { featureNames } from '../../features/registry';
import { useDocument } from '../../state/documentStore';
import { objectSelectionStore } from '../../state/objectSelectionStore';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyRow } from '../../ui/PropertyRow/PropertyRow';
import { SegmentedControl } from '../../ui/SegmentedControl/SegmentedControl';
import { Select } from '../../ui/Select/Select';
import { ToolPanel } from '../framework/ToolPanel';
import type { ToolPanelProps } from '../framework/types';
import {
  ORIGIN_PLANES,
  availableBodies,
  defaultTarget,
  isPatch,
  isPlane,
  storedParams,
  usableFeatures,
} from '../extrude/solid/model';
import { BodySelect, SolidResult, useBodyLabel } from '../extrude/solid/SolidSections';
import { useSolidFeature } from '../extrude/solid/useSolidFeature';

type Side = TrimParams['keep'];
const SIDES: readonly Side[] = ['front', 'back'];

const toolKey = (tool: TrimTool) => `${tool.type}:${tool.feature}`;

function parseToolKey(key: string): TrimTool | null {
  const [type, feature] = key.split(':');
  if (!feature || (type !== 'plane' && type !== 'patch')) return null;
  return { type, feature };
}

/** Körper teilen: cut a body with a plane or a freeform patch and keep one side. */
export function TrimPanel({ editTarget, close }: ToolPanelProps) {
  const { t } = useTranslation();
  const snapshot = useDocument((state) => state.snapshot);
  const bodyLabel = useBodyLabel();
  const stored = useMemo(
    () => storedParams<TrimParams>(snapshot, editTarget, 'trim'),
    // Only the parameters the tool was opened with.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [editTarget],
  );
  const names = useMemo(
    () => featureNames(snapshot?.document.features ?? [], t),
    [snapshot?.document.features, t],
  );
  const bodies = useMemo(
    () => (snapshot ? availableBodies(snapshot, editTarget) : []),
    [snapshot, editTarget],
  );
  const planes = useMemo(
    () => (snapshot ? usableFeatures(snapshot, isPlane, editTarget) : []),
    [snapshot, editTarget],
  );
  const patches = useMemo(
    () => (snapshot ? usableFeatures(snapshot, isPatch, editTarget) : []),
    [snapshot, editTarget],
  );

  const [targetBody, setTargetBody] = useState<string | null>(() => {
    if (stored) return stored.targetBody;
    const selected = objectSelectionStore.getState().selected[0];
    return selected?.kind === 'body' && bodies.some((body) => body.id === selected.id)
      ? selected.id
      : defaultTarget(bodies);
  });
  const [tool, setTool] = useState<TrimTool>(
    stored?.tool ?? { type: 'plane', feature: planes.at(-1) ?? 'XY' },
  );
  const [keep, setKeep] = useState<Side>(stored?.keep ?? 'back');

  const params = useMemo<TrimParamsInput | null>(
    () => (targetBody ? { targetBody, tool, keep } : null),
    [targetBody, tool, keep],
  );
  const { preview, commit, deviation, previewOk } = useSolidFeature(
    'trim',
    'trim',
    editTarget,
    params as Record<string, unknown> | null,
    close,
  );

  const toolOptions = [
    ...ORIGIN_PLANES.map((id) => ({
      value: toolKey({ type: 'plane', feature: id }),
      label: t(`tools:extrude.solid.originPlanes.${id}`),
    })),
    ...planes.map((id) => ({
      value: toolKey({ type: 'plane', feature: id }),
      label: names.get(id) ?? id,
    })),
    ...patches.map((id) => ({
      value: toolKey({ type: 'patch', feature: id }),
      label: names.get(id) ?? id,
    })),
  ];

  return (
    <ToolPanel
      toolId="trim"
      editingName={editTarget ? names.get(editTarget) : undefined}
      canCommit={previewOk}
      busy={commit.busy}
      onCommit={() => void commit.commit()}
      onCancel={close}
    >
      <PanelSection title={t('common:sections.input')}>
        {bodies.length === 0 ? (
          <InlineMessage severity="info">{t('tools:trim.noBody')}</InlineMessage>
        ) : (
          <BodySelect
            label={t('tools:trim.body')}
            value={targetBody}
            bodies={bodies}
            bodyLabel={bodyLabel}
            testId="trim-body"
            onChange={setTargetBody}
          />
        )}
        <PropertyRow label={t('tools:trim.tool')}>
          <Select<string>
            value={toolKey(tool)}
            ariaLabel={t('tools:trim.tool')}
            testId="trim-tool"
            options={toolOptions}
            onChange={(key) => {
              const parsed = parseToolKey(key);
              if (parsed) setTool(parsed);
            }}
          />
        </PropertyRow>
      </PanelSection>
      <PanelSection title={t('common:sections.parameters')}>
        <PropertyRow label={t('tools:trim.keep')}>
          <SegmentedControl<Side>
            value={keep}
            ariaLabel={t('tools:trim.keep')}
            segments={SIDES.map((value) => ({ value, label: t(`tools:trim.sides.${value}`) }))}
            onChange={setKeep}
          />
        </PropertyRow>
      </PanelSection>
      <SolidResult preview={preview} commitError={commit.error} deviation={deviation} />
    </ToolPanel>
  );
}
