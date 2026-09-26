import { useCallback, useEffect, useMemo, useReducer, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  DISTANCE_EXTENT_RANGES,
  type ExtrudeParams,
  type ExtrudeParamsInput,
} from '@shared/protocol/generated/feature-extrude';
import type { BodyOperation } from '@shared/protocol/generated/features-common';
import { DEFAULT_TOLERANCE_MM } from '@shared/protocol/generated/limits';

import { featureNames } from '../../features/registry';
import { useDocument } from '../../state/documentStore';
import { objectSelectionStore } from '../../state/objectSelectionStore';
import { Button } from '../../ui/Button/Button';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { NumberField } from '../../ui/NumberField/NumberField';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyRow, PropertyValue } from '../../ui/PropertyRow/PropertyRow';
import { SegmentedControl } from '../../ui/SegmentedControl/SegmentedControl';
import { Select } from '../../ui/Select/Select';
import { ToolPanel } from '../framework/ToolPanel';
import type { ToolPanelProps } from '../framework/types';
import { type Vec3, addScaled } from './extrusionGeometry';
import {
  ORIGIN_PLANES,
  availableBodies,
  defaultTarget,
  isPlane,
  isPositiveLength,
  isSketch,
  storedParams,
  targetProblem,
  usableFeatures,
} from './solid/model';
import { InputProblemMessage, OperationFields, SolidResult } from './solid/SolidSections';
import { useSolidFeature } from './solid/useSolidFeature';
import { scanDistances, useDistanceHandle, usePreviewCaps } from './useExtrusionHandle';

type Direction = ExtrudeParams['direction'];
type ExtentKind = 'distance' | 'toPlane';

const DIRECTIONS: readonly Direction[] = ['normal', 'reversed', 'symmetric'];
const EXTENTS: readonly ExtentKind[] = ['distance', 'toPlane'];
const DEFAULT_DISTANCE_MM = 10;

const round3 = (value: number) => Math.round(value * 1000) / 1000;

/** Extrusion of closed sketch profiles; the distance is pre-filled from the scan. */
export function ExtrudePanel({ editTarget, close }: ToolPanelProps) {
  const { t } = useTranslation();
  const snapshot = useDocument((state) => state.snapshot);
  const stored = useMemo(
    () => storedParams<ExtrudeParams>(snapshot, editTarget, 'extrude'),
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
  const planes = useMemo(
    () => (snapshot ? usableFeatures(snapshot, isPlane, editTarget) : []),
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
  const [loops, setLoops] = useState<string[] | null>(stored?.loops ?? null);
  const [direction, setDirection] = useState<Direction>(stored?.direction ?? 'normal');
  const [extentKind, setExtentKind] = useState<ExtentKind>(stored?.extent.type ?? 'distance');
  const [forward, setForward] = useState(
    stored?.extent.type === 'distance' ? stored.extent.forward : DEFAULT_DISTANCE_MM,
  );
  const [backward, setBackward] = useState(
    stored?.extent.type === 'distance' ? stored.extent.backward : 0,
  );
  const [plane, setPlane] = useState<string>(
    stored?.extent.type === 'toPlane' ? stored.extent.feature : (planes.at(-1) ?? 'XY'),
  );
  const [offset, setOffset] = useState(
    stored?.extent.type === 'toPlane' ? stored.extent.offset : 0,
  );
  const [operation, setOperation] = useState<BodyOperation>(stored?.operation ?? 'newBody');
  const [targetBody, setTargetBody] = useState<string | null>(stored?.targetBody ?? null);
  const [prefill, setPrefill] = useState<'pending' | 'done'>(stored ? 'done' : 'pending');
  const [handleRevision, moveHandle] = useReducer((count: number) => count + 1, 0);

  const problem = targetProblem(operation, targetBody, bodies);
  const lengthsValid =
    extentKind === 'toPlane' ||
    (direction === 'symmetric' ? isPositiveLength(forward) : isPositiveLength(forward + backward));
  const params = useMemo<ExtrudeParamsInput | null>(() => {
    if (!sketch || problem || !lengthsValid) return null;
    return {
      sketch,
      loops,
      direction,
      extent:
        extentKind === 'distance'
          ? { type: 'distance', forward, backward: direction === 'symmetric' ? 0 : backward }
          : { type: 'toPlane', feature: plane, offset },
      operation,
      targetBody: operation === 'newBody' ? null : targetBody,
    };
  }, [
    sketch,
    problem,
    lengthsValid,
    loops,
    direction,
    extentKind,
    forward,
    backward,
    plane,
    offset,
    operation,
    targetBody,
  ]);

  const { preview, commit, previewOk } = useSolidFeature(
    'extrude',
    'extrude',
    editTarget,
    params as Record<string, unknown> | null,
    close,
  );
  const caps = usePreviewCaps(preview.status === 'ok' ? preview.result : null);
  const planePoint: Vec3 | null = useMemo(() => {
    if (!caps || extentKind !== 'distance') return null;
    if (direction === 'symmetric') {
      return addScaled(caps.start, caps.direction, forward / 2);
    }
    return addScaled(caps.start, caps.direction, backward);
    // The plane point only moves with the caps (each preview).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caps, extentKind, direction]);

  const setDistance = useCallback((value: number) => {
    setPrefill('done');
    setForward(value);
  }, []);
  useDistanceHandle({
    planePoint,
    direction: caps?.direction ?? null,
    value: direction === 'symmetric' ? forward / 2 : forward,
    revision: handleRevision,
    onChange: (value) => setDistance(round3(direction === 'symmetric' ? value * 2 : value)),
  });

  const tolerance = snapshot?.document.settings.tolerance ?? DEFAULT_TOLERANCE_MM;
  useEffect(() => {
    if (prefill !== 'pending' || !caps || !planePoint || direction === 'symmetric') return;
    let current = true;
    void scanDistances(caps, planePoint).then(({ ahead, behind }) => {
      if (!current) return;
      setPrefill('done');
      if (ahead === null || ahead <= tolerance) return;
      setForward(round3(ahead));
      // A section through the middle of the part: the scan continues behind the sketch.
      setBackward(behind !== null && behind > tolerance ? round3(behind) : 0);
      moveHandle();
    });
    return () => {
      current = false;
    };
  }, [prefill, caps, planePoint, direction, tolerance]);

  const typed = (setter: (value: number) => void) => (value: number) => {
    setPrefill('done');
    setter(value);
    moveHandle();
  };

  const featureLabel = (id: string) => names.get(id) ?? id;
  const planeLabel = (id: string) =>
    (ORIGIN_PLANES as readonly string[]).includes(id)
      ? t(`tools:extrude.solid.originPlanes.${id}`)
      : featureLabel(id);

  return (
    <ToolPanel
      toolId="extrude"
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
              testId="extrude-sketch"
              options={sketches.map((id) => ({ value: id, label: featureLabel(id) }))}
              onChange={(id) => {
                setSketch(id);
                setLoops(null);
              }}
            />
          </PropertyRow>
        )}
        <PropertyValue
          label={t('tools:extrude.loops')}
          value={
            loops === null
              ? t('tools:extrude.allLoops')
              : t('tools:extrude.someLoops', { count: loops.length })
          }
        />
        {loops !== null && (
          <Button variant="ghost" onClick={() => setLoops(null)}>
            {t('tools:extrude.useAllLoops')}
          </Button>
        )}
      </PanelSection>
      <PanelSection title={t('common:sections.parameters')}>
        <PropertyRow label={t('tools:extrude.direction')}>
          <SegmentedControl<Direction>
            value={direction}
            ariaLabel={t('tools:extrude.direction')}
            segments={DIRECTIONS.map((value) => ({
              value,
              label: t(`tools:extrude.directions.${value}`),
            }))}
            onChange={(value) => {
              setDirection(value);
              moveHandle();
            }}
          />
        </PropertyRow>
        <PropertyRow label={t('tools:extrude.extent')}>
          <SegmentedControl<ExtentKind>
            value={extentKind}
            ariaLabel={t('tools:extrude.extent')}
            segments={EXTENTS.map((value) => ({
              value,
              label: t(`tools:extrude.extents.${value}`),
            }))}
            onChange={setExtentKind}
          />
        </PropertyRow>
        {extentKind === 'distance' ? (
          <>
            <PropertyRow
              label={t(
                direction === 'symmetric' ? 'tools:extrude.totalLength' : 'tools:extrude.distance',
              )}
            >
              <NumberField
                value={forward}
                min={DISTANCE_EXTENT_RANGES.forward.min}
                onCommit={typed(setForward)}
              />
            </PropertyRow>
            {direction !== 'symmetric' && (
              <PropertyRow label={t('tools:extrude.backward')}>
                <NumberField
                  value={backward}
                  min={DISTANCE_EXTENT_RANGES.backward.min}
                  onCommit={typed(setBackward)}
                />
              </PropertyRow>
            )}
          </>
        ) : (
          <>
            <PropertyRow label={t('tools:extrude.plane')}>
              <Select<string>
                value={plane}
                ariaLabel={t('tools:extrude.plane')}
                options={[...ORIGIN_PLANES, ...planes].map((id) => ({
                  value: id,
                  label: planeLabel(id),
                }))}
                onChange={setPlane}
              />
            </PropertyRow>
            <PropertyRow label={t('tools:extrude.offset')}>
              <NumberField value={offset} onCommit={setOffset} />
            </PropertyRow>
          </>
        )}
        {!lengthsValid && (
          <InlineMessage severity="info">{t('tools:extrude.lengthMissing')}</InlineMessage>
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
      <SolidResult preview={preview} commitError={commit.error} />
    </ToolPanel>
  );
}
