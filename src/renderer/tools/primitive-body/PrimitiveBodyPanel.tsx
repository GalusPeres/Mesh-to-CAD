import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  MANUAL_EXTENT_RANGES,
  type PrimitiveBodyParams,
  type PrimitiveBodyParamsInput,
  REGION_EXTENT_RANGES,
} from '@shared/protocol/generated/feature-primitive-body';
import type { BodyOperation } from '@shared/protocol/generated/features-common';

import { featureNames } from '../../features/registry';
import { useDocument } from '../../state/documentStore';
import { objectSelectionStore } from '../../state/objectSelectionStore';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { NumberField } from '../../ui/NumberField/NumberField';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyRow } from '../../ui/PropertyRow/PropertyRow';
import { SegmentedControl } from '../../ui/SegmentedControl/SegmentedControl';
import { Select } from '../../ui/Select/Select';
import { ToolPanel } from '../framework/ToolPanel';
import type { ToolPanelProps } from '../framework/types';
import {
  availableBodies,
  defaultTarget,
  isBodyFit,
  isPositiveLength,
  storedParams,
  targetProblem,
  usableFeatures,
} from '../extrude/solid/model';
import { InputProblemMessage, OperationFields, SolidResult } from '../extrude/solid/SolidSections';
import { useSolidFeature } from '../extrude/solid/useSolidFeature';

type ExtentKind = 'region' | 'manual';
const EXTENTS: readonly ExtentKind[] = ['region', 'manual'];
const CLOSED_KINDS = new Set(['sphere', 'torus']);

/** A solid cylinder, cone, sphere or torus from a fit, cut to the scan's extent. */
export function PrimitiveBodyPanel({ editTarget, close }: ToolPanelProps) {
  const { t } = useTranslation();
  const snapshot = useDocument((state) => state.snapshot);
  const stored = useMemo(
    () => storedParams<PrimitiveBodyParams>(snapshot, editTarget, 'primitiveBody'),
    // Only the parameters the tool was opened with.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [editTarget],
  );
  const names = useMemo(
    () => featureNames(snapshot?.document.features ?? [], t),
    [snapshot?.document.features, t],
  );
  const fits = useMemo(
    () => (snapshot ? usableFeatures(snapshot, isBodyFit, editTarget) : []),
    [snapshot, editTarget],
  );
  const bodies = useMemo(
    () => (snapshot ? availableBodies(snapshot, editTarget) : []),
    [snapshot, editTarget],
  );

  const [fit, setFit] = useState<string | null>(() => {
    if (stored) return stored.fit;
    const selected = objectSelectionStore.getState().selected[0];
    return selected?.kind === 'feature' && fits.includes(selected.id)
      ? selected.id
      : (fits.at(-1) ?? null);
  });
  const [extentKind, setExtentKind] = useState<ExtentKind>(stored?.extent.type ?? 'region');
  const [margin, setMargin] = useState(stored?.extent.type === 'region' ? stored.extent.margin : 0);
  const [start, setStart] = useState(stored?.extent.type === 'manual' ? stored.extent.start : 0);
  const [length, setLength] = useState(
    stored?.extent.type === 'manual' ? stored.extent.length : 10,
  );
  const [operation, setOperation] = useState<BodyOperation>(stored?.operation ?? 'newBody');
  const [targetBody, setTargetBody] = useState<string | null>(stored?.targetBody ?? null);

  const kind = useMemo(() => {
    const feature = snapshot?.document.features.find((item) => item.id === fit);
    return (feature?.params as { kind?: string } | undefined)?.kind ?? null;
  }, [snapshot?.document.features, fit]);
  const closed = kind !== null && CLOSED_KINDS.has(kind);
  const problem = targetProblem(operation, targetBody, bodies);
  const lengthValid = closed || extentKind === 'region' || isPositiveLength(length);

  const params = useMemo<PrimitiveBodyParamsInput | null>(() => {
    if (!fit || problem || !lengthValid) return null;
    return {
      fit,
      extent:
        extentKind === 'region' ? { type: 'region', margin } : { type: 'manual', start, length },
      operation,
      targetBody: operation === 'newBody' ? null : targetBody,
    };
  }, [fit, problem, lengthValid, extentKind, margin, start, length, operation, targetBody]);
  const { preview, commit, deviation, previewOk } = useSolidFeature(
    'primitive-body',
    'primitiveBody',
    editTarget,
    params as Record<string, unknown> | null,
    close,
  );

  return (
    <ToolPanel
      toolId="primitive-body"
      editingName={editTarget ? names.get(editTarget) : undefined}
      canCommit={previewOk}
      busy={commit.busy}
      onCommit={() => void commit.commit()}
      onCancel={close}
    >
      <PanelSection title={t('common:sections.input')}>
        {fits.length === 0 && !fit ? (
          <InlineMessage severity="info">{t('tools:primitiveBody.noFit')}</InlineMessage>
        ) : (
          <PropertyRow label={t('tools:primitiveBody.fit')}>
            <Select<string>
              value={fit ?? ''}
              ariaLabel={t('tools:primitiveBody.fit')}
              testId="primitive-body-fit"
              options={fits.map((id) => ({ value: id, label: names.get(id) ?? id }))}
              onChange={setFit}
            />
          </PropertyRow>
        )}
      </PanelSection>
      <PanelSection title={t('common:sections.parameters')}>
        {closed ? (
          <InlineMessage severity="info">{t('tools:primitiveBody.closed')}</InlineMessage>
        ) : (
          <>
            <PropertyRow label={t('tools:primitiveBody.extent')}>
              <SegmentedControl<ExtentKind>
                value={extentKind}
                ariaLabel={t('tools:primitiveBody.extent')}
                segments={EXTENTS.map((value) => ({
                  value,
                  label: t(`tools:primitiveBody.extents.${value}`),
                }))}
                onChange={setExtentKind}
              />
            </PropertyRow>
            {extentKind === 'region' ? (
              <PropertyRow label={t('tools:primitiveBody.margin')}>
                <NumberField
                  value={margin}
                  min={REGION_EXTENT_RANGES.margin.min}
                  onCommit={setMargin}
                />
              </PropertyRow>
            ) : (
              <>
                <PropertyRow label={t('tools:primitiveBody.start')}>
                  <NumberField value={start} onCommit={setStart} />
                </PropertyRow>
                <PropertyRow label={t('tools:primitiveBody.length')}>
                  <NumberField
                    value={length}
                    min={MANUAL_EXTENT_RANGES.length.min}
                    onCommit={setLength}
                  />
                </PropertyRow>
              </>
            )}
          </>
        )}
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
      <SolidResult preview={preview} commitError={commit.error} deviation={deviation} />
    </ToolPanel>
  );
}
