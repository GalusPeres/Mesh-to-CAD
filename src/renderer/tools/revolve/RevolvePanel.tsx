import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  REVOLVE_PARAMS_RANGES,
  type RevolveAxis,
  type RevolveParams,
  type RevolveParamsInput,
} from '@shared/protocol/generated/feature-revolve';
import type { BodyOperation } from '@shared/protocol/generated/features-common';

import { featureNames } from '../../features/registry';
import { useDocument } from '../../state/documentStore';
import { objectSelectionStore } from '../../state/objectSelectionStore';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { NumberField } from '../../ui/NumberField/NumberField';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyRow } from '../../ui/PropertyRow/PropertyRow';
import { Select } from '../../ui/Select/Select';
import { ToolPanel } from '../framework/ToolPanel';
import type { ToolPanelProps } from '../framework/types';
import {
  ORIGIN_AXES,
  availableBodies,
  defaultTarget,
  isAxis,
  isSketch,
  storedParams,
  targetProblem,
  usableFeatures,
} from '../extrude/solid/model';
import { InputProblemMessage, OperationFields, SolidResult } from '../extrude/solid/SolidSections';
import { useSolidFeature } from '../extrude/solid/useSolidFeature';
import { axisKey, parseAxisKey, sketchLines } from './axes';

/** Revolution of closed sketch profiles about a sketch line, a fitted axis or X/Y/Z. */
export function RevolvePanel({ editTarget, close }: ToolPanelProps) {
  const { t } = useTranslation();
  const snapshot = useDocument((state) => state.snapshot);
  const stored = useMemo(
    () => storedParams<RevolveParams>(snapshot, editTarget, 'revolve'),
    // Only the parameters the tool was opened with.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [editTarget],
  );
  const names = useMemo(
    () => featureNames(snapshot?.document.features ?? [], t),
    [snapshot?.document.features, t],
  );
  const sketches = useMemo(
    () => (snapshot ? usableFeatures(snapshot, isSketch, editTarget) : []),
    [snapshot, editTarget],
  );
  const axes = useMemo(
    () => (snapshot ? usableFeatures(snapshot, isAxis, editTarget) : []),
    [snapshot, editTarget],
  );
  const bodies = useMemo(
    () => (snapshot ? availableBodies(snapshot, editTarget) : []),
    [snapshot, editTarget],
  );

  const [sketch, setSketch] = useState<string | null>(() => {
    if (stored) return stored.sketch;
    const selected = objectSelectionStore.getState().selected[0];
    return selected?.kind === 'feature' && sketches.includes(selected.id)
      ? selected.id
      : (sketches.at(-1) ?? null);
  });
  const lines = useMemo(
    () => sketchLines(snapshot?.document.features.find((feature) => feature.id === sketch)),
    [snapshot?.document.features, sketch],
  );
  const [axis, setAxis] = useState<RevolveAxis>(
    stored?.axis ??
      (axes.length
        ? { type: 'featureAxis', feature: axes.at(-1)! }
        : { type: 'globalAxis', axis: 'Z' }),
  );
  const [angle, setAngle] = useState(stored?.angleDeg ?? 360);
  const [operation, setOperation] = useState<BodyOperation>(stored?.operation ?? 'newBody');
  const [targetBody, setTargetBody] = useState<string | null>(stored?.targetBody ?? null);

  const problem = targetProblem(operation, targetBody, bodies);
  const angleValid = angle > 0 && angle <= REVOLVE_PARAMS_RANGES.angleDeg.max;
  const params = useMemo<RevolveParamsInput | null>(() => {
    if (!sketch || problem || !angleValid) return null;
    return {
      sketch,
      loops: stored?.sketch === sketch ? stored.loops : null,
      axis,
      angleDeg: angle,
      operation,
      targetBody: operation === 'newBody' ? null : targetBody,
    };
  }, [sketch, problem, angleValid, stored, axis, angle, operation, targetBody]);
  const { preview, commit, previewOk } = useSolidFeature(
    'revolve',
    'revolve',
    editTarget,
    params as Record<string, unknown> | null,
    close,
  );

  const axisOptions = [
    ...ORIGIN_AXES.map((id) => ({
      value: axisKey({ type: 'globalAxis', axis: id }),
      label: t(`tools:extrude.solid.originAxes.${id}`),
    })),
    ...axes.map((id) => ({
      value: axisKey({ type: 'featureAxis', feature: id }),
      label: names.get(id) ?? id,
    })),
    ...lines.map((id) => ({
      value: axisKey({ type: 'sketchLine', entity: id }),
      label: t('tools:revolve.sketchLine', { id }),
    })),
  ];

  return (
    <ToolPanel
      toolId="revolve"
      editingName={editTarget ? names.get(editTarget) : undefined}
      canCommit={previewOk}
      busy={commit.busy}
      onCommit={() => void commit.commit()}
      onCancel={close}
    >
      <PanelSection title={t('common:sections.input')}>
        {sketches.length === 0 && !sketch ? (
          <InlineMessage severity="info">{t('tools:extrude.noSketch')}</InlineMessage>
        ) : (
          <PropertyRow label={t('tools:extrude.sketch')}>
            <Select<string>
              value={sketch ?? ''}
              ariaLabel={t('tools:extrude.sketch')}
              testId="revolve-sketch"
              options={sketches.map((id) => ({ value: id, label: names.get(id) ?? id }))}
              onChange={setSketch}
            />
          </PropertyRow>
        )}
        <PropertyRow label={t('tools:revolve.axis')}>
          <Select<string>
            value={axisKey(axis)}
            ariaLabel={t('tools:revolve.axis')}
            testId="revolve-axis"
            options={axisOptions}
            onChange={(key) => {
              const parsed = parseAxisKey(key);
              if (parsed) setAxis(parsed);
            }}
          />
        </PropertyRow>
      </PanelSection>
      <PanelSection title={t('common:sections.parameters')}>
        <PropertyRow label={t('tools:revolve.angle')}>
          <NumberField
            value={angle}
            kind="angle"
            min={REVOLVE_PARAMS_RANGES.angleDeg.min}
            max={REVOLVE_PARAMS_RANGES.angleDeg.max}
            onCommit={setAngle}
          />
        </PropertyRow>
      </PanelSection>
      <PanelSection title={t('common:sections.options')}>
        <OperationFields
          operation={operation}
          targetBody={targetBody}
          bodies={bodies}
          onOperation={(value) => {
            setOperation(value);
            if (value !== 'newBody' && !targetBody) setTargetBody(defaultTarget(bodies));
          }}
          onTargetBody={setTargetBody}
        />
        <InputProblemMessage problem={problem} />
      </PanelSection>
      <SolidResult preview={preview} commitError={commit.error} />
    </ToolPanel>
  );
}
