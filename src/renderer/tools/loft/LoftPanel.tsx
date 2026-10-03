import { useCallback, useEffect, useMemo, useReducer, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { BodyOperation } from '@shared/protocol/generated/features-common';
import type { LoftInput, LoftParams } from '@shared/protocol/generated/feature-loft';

import { featureNames } from '../../features/registry';
import { useFormatter } from '../../i18n/useFormatter';
import { describeError } from '../../kernel/describeError';
import { kernel } from '../../kernel/kernel';
import { selectedFaces, useSelectedFaceCount } from '../../selection/api';
import { useDocument } from '../../state/documentStore';
import { Checkbox } from '../../ui/Checkbox/Checkbox';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { NumberField } from '../../ui/NumberField/NumberField';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyRow, PropertyValue } from '../../ui/PropertyRow/PropertyRow';
import { Select } from '../../ui/Select/Select';
import {
  ORIGIN_AXES,
  ORIGIN_PLANES,
  availableBodies,
  defaultTarget,
  isPlane,
  storedParams,
  targetProblem,
  usableFeatures,
} from '../extrude/solid/model';
import { InputProblemMessage, OperationFields, SolidResult } from '../extrude/solid/SolidSections';
import { useSolidFeature } from '../extrude/solid/useSolidFeature';
import { ToolPanel } from '../framework/ToolPanel';
import type { ToolPanelProps } from '../framework/types';
import {
  DEFAULT_SECTIONS,
  SECTION_RANGE,
  axisOptions,
  clampSections,
  rangeProblem,
  round3,
} from './loftDraft';
import { PlaneEnds } from './PlaneEnds';
import { useLoftAxis, useRangeHandles } from './useLoftAxis';

const KEY = 'tools:loft';

/** Stored triangles of an edited loft that sections only part of the scan. */
function useStoredFaces(editTarget: string | null, restricted: boolean): Uint32Array | null {
  const [faces, setFaces] = useState<Uint32Array | null>(null);
  useEffect(() => {
    if (!editTarget || !restricted) return;
    let current = true;
    void kernel()
      .call('freeform.featureFaces', { featureId: editTarget })
      .result.then((result) => {
        if (current) setFaces(result.faces);
      });
    return () => {
      current = false;
    };
  }, [editTarget, restricted]);
  return faces;
}

/** A solid lofted through sections of the scan along an axis. */
export function LoftPanel({ editTarget, close }: ToolPanelProps) {
  const { t } = useTranslation();
  const format = useFormatter();
  const snapshot = useDocument((state) => state.snapshot);
  const stored = useMemo(
    () => storedParams<LoftParams>(snapshot, editTarget, 'loft'),
    // Only the parameters the tool was opened with.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [editTarget],
  );
  const names = useMemo(
    () => featureNames(snapshot?.document.features ?? [], t),
    [snapshot?.document.features, t],
  );
  const axes = useMemo(
    () => (snapshot ? axisOptions(snapshot, editTarget) : []),
    [snapshot, editTarget],
  );
  const bodies = useMemo(
    () => (snapshot ? availableBodies(snapshot, editTarget) : []),
    [snapshot, editTarget],
  );
  const planes = useMemo(
    () => (snapshot ? usableFeatures(snapshot, isPlane, editTarget) : []),
    [snapshot, editTarget],
  );

  const [path, setPath] = useState<string>(stored?.path ?? 'Z');
  const [range, setRange] = useState<[number, number] | null>(
    stored ? [stored.start, stored.end] : null,
  );
  const [sections, setSections] = useState(stored?.sectionCount ?? DEFAULT_SECTIONS);
  const [startPlane, setStartPlane] = useState<string | null>(stored?.startPlane ?? null);
  const [endPlane, setEndPlane] = useState<string | null>(stored?.endPlane ?? null);
  const [onlySelection, setOnlySelection] = useState(!!stored?.faces);
  const [operation, setOperation] = useState<BodyOperation>(stored?.operation ?? 'newBody');
  const [targetBody, setTargetBody] = useState<string | null>(
    stored?.targetBody ?? defaultTarget(bodies),
  );
  const [handleRevision, moveHandles] = useReducer((count: number) => count + 1, 0);

  const selectionCount = useSelectedFaceCount();
  const scanKey = snapshot?.document.scan?.key ?? null;
  const storedFaces = useStoredFaces(editTarget, !!stored?.faces);
  const faces = useMemo(() => {
    if (!onlySelection || !scanKey) return null;
    return selectionCount > 0 ? selectedFaces(scanKey) : storedFaces;
  }, [onlySelection, scanKey, selectionCount, storedFaces]);

  const axisState = useLoftAxis(path, faces, snapshot?.revision ?? null);
  const axis = axisState.status === 'ok' ? axisState.axis : null;
  // Until start or end are set, they follow the stretch of the scan the kernel found
  // loftable along the chosen axis (its walls, not the buttons or a flat slope).
  const shown = useMemo(
    () => range ?? (axis ? ([round3(axis.start), round3(axis.end)] as [number, number]) : null),
    [range, axis],
  );
  const [start, end] = shown ?? [0, 0];
  const setStart = useCallback(
    (value: number) => setRange([round3(value), shown?.[1] ?? round3(value)]),
    [shown],
  );
  const setEnd = useCallback(
    (value: number) => setRange([shown?.[0] ?? round3(value), round3(value)]),
    [shown],
  );
  useRangeHandles({ axis, start, end, revision: handleRevision, onStart: setStart, onEnd: setEnd });

  const problem = targetProblem(operation, targetBody, bodies);
  const hasRange = shown !== null;
  const invalidRange = hasRange ? rangeProblem(start, end) : null;
  const params = useMemo<LoftInput | null>(() => {
    if (!hasRange || problem || invalidRange || (onlySelection && !faces)) return null;
    return {
      path,
      start,
      end,
      sectionCount: sections,
      faces,
      operation,
      targetBody: operation === 'newBody' ? null : targetBody,
      startPlane,
      endPlane,
    };
  }, [
    hasRange,
    problem,
    invalidRange,
    onlySelection,
    faces,
    path,
    start,
    end,
    sections,
    operation,
    targetBody,
    startPlane,
    endPlane,
  ]);
  const { preview, commit, previewOk } = useSolidFeature(
    'loft',
    'loft',
    editTarget,
    params as Record<string, unknown> | null,
    close,
  );

  const axisLabel = (id: string) =>
    (ORIGIN_AXES as readonly string[]).includes(id)
      ? t(`tools:extrude.solid.originAxes.${id}`)
      : (names.get(id) ?? id);
  const planeLabel = (id: string) =>
    (ORIGIN_PLANES as readonly string[]).includes(id)
      ? t(`tools:extrude.solid.originPlanes.${id}`)
      : (names.get(id) ?? id);
  const typed = (update: (value: number) => void) => (value: number) => {
    update(value);
    moveHandles();
  };

  return (
    <ToolPanel
      toolId="loft"
      editingName={editTarget ? names.get(editTarget) : undefined}
      canCommit={previewOk}
      busy={commit.busy}
      onCommit={() => void commit.commit()}
      onCancel={close}
    >
      <PanelSection title={t('common:sections.input')}>
        <PropertyRow label={t(`${KEY}.axis`)}>
          <Select<string>
            value={path}
            ariaLabel={t(`${KEY}.axis`)}
            testId="loft-axis"
            options={axes.map((id) => ({ value: id, label: axisLabel(id) }))}
            onChange={(value) => {
              setPath(value);
              setRange(null);
            }}
          />
        </PropertyRow>
        <Checkbox
          checked={onlySelection}
          label={t(`${KEY}.onlySelection`)}
          onChange={(checked) => {
            setOnlySelection(checked);
            setRange(null);
          }}
        />
        {onlySelection && (
          <PropertyValue label={t(`${KEY}.triangles`)} value={format.count(faces?.length ?? 0)} />
        )}
        {axisState.status === 'error' && (
          <InlineMessage severity="error" details={axisState.error.details}>
            {describeError(axisState.error, t)}
          </InlineMessage>
        )}
        {axis && (
          <PropertyValue
            label={t(`${KEY}.extent`)}
            value={`${format.length(axis.low, { signed: true })} … ${format.length(axis.high, { signed: true })}`}
          />
        )}
      </PanelSection>
      <PanelSection title={t('common:sections.parameters')}>
        <PropertyRow label={t(`${KEY}.start`)}>
          <NumberField value={shown ? start : null} onCommit={typed(setStart)} />
        </PropertyRow>
        <PropertyRow label={t(`${KEY}.end`)}>
          <NumberField value={shown ? end : null} onCommit={typed(setEnd)} />
        </PropertyRow>
        {invalidRange && <InlineMessage severity="info">{t(`${KEY}.emptyRange`)}</InlineMessage>}
        <PropertyRow label={t(`${KEY}.sections`)}>
          <NumberField
            kind="count"
            value={sections}
            min={SECTION_RANGE.min}
            max={SECTION_RANGE.max}
            onCommit={(value) => setSections(clampSections(value))}
          />
        </PropertyRow>
        <PlaneEnds
          planes={planes}
          startPlane={startPlane}
          endPlane={endPlane}
          label={planeLabel}
          onStartPlane={setStartPlane}
          onEndPlane={setEndPlane}
        />
      </PanelSection>
      <PanelSection title={t('common:sections.options')}>
        <OperationFields
          operation={operation}
          targetBody={targetBody}
          bodies={bodies}
          onOperation={setOperation}
          onTargetBody={setTargetBody}
        />
        <InputProblemMessage problem={problem} />
      </PanelSection>
      <SolidResult preview={preview} commitError={commit.error} />
    </ToolPanel>
  );
}
