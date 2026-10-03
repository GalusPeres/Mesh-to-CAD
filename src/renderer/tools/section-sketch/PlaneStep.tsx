import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { Feature } from '@shared/protocol/generated/document-model';
import type { SectionResult } from '@shared/protocol/generated/sketch';
import type { SketchSection } from '@shared/protocol/generated/sketch-params';

import { useFormatter } from '../../i18n/useFormatter';
import { describeError } from '../../kernel/describeError';
import { documentStore } from '../../state/documentStore';
import { objectSelectionStore } from '../../state/objectSelectionStore';
import { Checkbox } from '../../ui/Checkbox/Checkbox';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { NumberField } from '../../ui/NumberField/NumberField';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyRow, PropertyValue } from '../../ui/PropertyRow/PropertyRow';
import { Select } from '../../ui/Select/Select';
import { useViewport } from '../../viewport/api';
import type { PreviewState } from '../framework/hooks';
import {
  GLOBAL_AXES,
  PLANE_KINDS,
  type PlaneKind,
  planeKindOf,
  providesAxis,
  providesPlane,
  scanCenter,
  sectionFor,
  usableFeatures,
} from './planeChoice';
import type { SketchDraft } from './useSketchDraft';
import { useSketchViewport } from './useSketchViewport';

const K = 'sectionSketch';
const NO_HIGHLIGHT = { selected: null, pending: [], points: [], gaps: [] };
const NO_HANDLERS = { click: () => undefined, paint: () => undefined, abort: () => false };

interface PlaneStepProps {
  sketch: SketchDraft;
  features: readonly Feature[];
  editTarget: string | null;
  names: ReadonlyMap<string, string>;
  preview: PreviewState<SectionResult>;
}

/** Step 1: plane, cut position and tolerance, with the live section in the viewport. */
export function PlaneStep({ sketch, features, editTarget, names, preview }: PlaneStepProps) {
  const { t } = useTranslation(['tools', 'common']);
  const format = useFormatter();
  const viewport = useViewport();
  const { draft } = sketch;
  const section = draft.section;
  const kind = planeKindOf(section);
  const usable = usableFeatures(features, editTarget);
  const planes = usable.filter(providesPlane);
  const axes = usable.filter(providesAxis);
  const [cutRevision, setCutRevision] = useState(0);
  const dragging = useRef(false);

  const setSection = (next: SketchSection, typed = true) => {
    sketch.edit({ ...draft, section: next });
    if (typed) setCutRevision((value) => value + 1);
  };

  const chooseKind = (next: PlaneKind) => {
    const axis = section.type === 'rotational' ? section.axis : 'Z';
    const center = scanCenter(documentStore.getState().snapshot?.scene.scan);
    setSection(sectionFor(next, section, { plane: planes[0]?.id ?? null, axis }, center));
  };

  // A plane feature clicked in the project tree or the viewport becomes the sketch plane.
  const choosePlane = useRef<(id: string) => void>(() => undefined);
  useEffect(() => {
    choosePlane.current = (id: string) => {
      if (
        section.type === 'planar' &&
        section.plane.type === 'feature' &&
        planes.some((p) => p.id === id)
      ) {
        setSection({ ...section, plane: { type: 'feature', feature: id } });
      }
    };
  });
  useEffect(
    () =>
      objectSelectionStore.subscribe((state) => {
        const picked = state.selected[0];
        if (picked?.kind === 'feature') choosePlane.current(picked.id);
      }),
    [],
  );
  useEffect(() => {
    if (!viewport || kind !== 'feature') return;
    return viewport.addInteraction({
      onPointerDown: (event) => {
        if (event.button !== 0) return false;
        const hit = viewport.pick(event.screen, { kinds: ['item'] });
        if (hit?.kind !== 'item') return false;
        choosePlane.current(hit.owner);
        return true;
      },
    });
  }, [viewport, kind]);

  const result =
    preview.status === 'ok'
      ? preview.result
      : preview.status === 'computing'
        ? preview.previous
        : null;
  const drawing = useMemo(
    () =>
      result
        ? {
            frame: result.frame,
            polylines: result.polylines,
            closed: result.closed,
            folded: result.folded,
          }
        : null,
    [result],
  );
  useSketchViewport({
    step: 'plane',
    section: drawing,
    frame: result?.frame ?? null,
    sketch: null,
    fits: [],
    highlight: NO_HIGHLIGHT,
    cut:
      section.type === 'planar'
        ? {
            value: section.sectionOffset,
            revision: cutRevision,
            change: (value, done) => {
              const next = { ...draft, section: { ...section, sectionOffset: value } };
              if (dragging.current) sketch.adjust(next);
              else sketch.edit(next);
              dragging.current = !done;
            },
          }
        : null,
    handlers: NO_HANDLERS,
  });

  const axisOptions = [
    ...GLOBAL_AXES.map((axis) => ({
      value: axis,
      label: t(`${K}.globalAxis`, { axis }),
    })),
    ...axes.map((feature) => ({ value: feature.id, label: names.get(feature.id) ?? feature.id })),
  ];
  const closedCount = result?.closed.filter(Boolean).length ?? 0;
  const openCount = (result?.closed.length ?? 0) - closedCount;

  return (
    <>
      <PanelSection title={t('common:sections.input')}>
        <PropertyRow label={t(`${K}.planeKind.label`)} htmlFor="sketch-plane-kind">
          <Select<PlaneKind>
            id="sketch-plane-kind"
            testId="sketch-plane-kind"
            value={kind}
            options={PLANE_KINDS.map((value) => ({ value, label: t(`${K}.planeKind.${value}`) }))}
            onChange={chooseKind}
          />
        </PropertyRow>
        {section.type === 'planar' && section.plane.type === 'feature' && (
          <>
            {planes.length ? (
              <PropertyRow label={t(`${K}.planeFeature`)} htmlFor="sketch-plane-feature">
                <Select
                  id="sketch-plane-feature"
                  value={section.plane.feature}
                  options={planes.map((p) => ({ value: p.id, label: names.get(p.id) ?? p.id }))}
                  onChange={(feature) =>
                    setSection({ ...section, plane: { type: 'feature', feature } })
                  }
                />
              </PropertyRow>
            ) : (
              <InlineMessage severity="info">{t(`${K}.noPlaneFeatures`)}</InlineMessage>
            )}
            {planes.length > 0 && (
              <InlineMessage severity="info">{t(`${K}.pickPlane`)}</InlineMessage>
            )}
          </>
        )}
        {(section.type === 'rotational' ||
          (section.type === 'planar' && section.plane.type === 'axisNormal')) && (
          <PropertyRow label={t(`${K}.axis`)} htmlFor="sketch-axis">
            <Select
              id="sketch-axis"
              value={
                section.type === 'rotational'
                  ? section.axis
                  : section.plane.type === 'axisNormal'
                    ? section.plane.axis
                    : 'Z'
              }
              options={axisOptions}
              onChange={(axis) =>
                setSection(
                  section.type === 'rotational'
                    ? { ...section, axis }
                    : { ...section, plane: { type: 'axisNormal', axis } },
                )
              }
            />
          </PropertyRow>
        )}
      </PanelSection>

      <PanelSection title={t('common:sections.parameters')}>
        {section.type === 'planar' ? (
          <>
            <PropertyRow label={t(`${K}.offset`)} htmlFor="sketch-offset">
              <NumberField
                id="sketch-offset"
                value={section.offset}
                onCommit={(offset) => setSection({ ...section, offset })}
              />
            </PropertyRow>
            <PropertyRow label={t(`${K}.sectionOffset`)} htmlFor="sketch-cut">
              <NumberField
                id="sketch-cut"
                value={section.sectionOffset}
                onCommit={(sectionOffset) => setSection({ ...section, sectionOffset })}
              />
            </PropertyRow>
            <Checkbox
              label={t(`${K}.flip`)}
              checked={section.flip}
              onChange={(flip) => setSection({ ...section, flip })}
            />
          </>
        ) : (
          <PropertyRow label={t(`${K}.angle`)} htmlFor="sketch-angle">
            <NumberField
              id="sketch-angle"
              kind="angle"
              value={section.angleDeg}
              onCommit={(angleDeg) => setSection({ ...section, angleDeg })}
            />
          </PropertyRow>
        )}
      </PanelSection>

      <PanelSection title={t('common:sections.options')}>
        <Checkbox
          label={t(`${K}.toleranceAuto`)}
          checked={draft.tolerance === null}
          onChange={(auto) =>
            sketch.edit({ ...draft, tolerance: auto ? null : (result?.suggestedTolerance ?? 0.1) })
          }
        />
        {draft.tolerance !== null && (
          <PropertyRow label={t(`${K}.tolerance`)} htmlFor="sketch-tolerance">
            <NumberField
              id="sketch-tolerance"
              value={draft.tolerance}
              min={0.005}
              step={0.01}
              onCommit={(tolerance) => sketch.edit({ ...draft, tolerance })}
            />
          </PropertyRow>
        )}
      </PanelSection>

      <PanelSection title={t('common:sections.result')}>
        {preview.status === 'computing' && <p>{t('common:tool.computing')}</p>}
        {result && (
          <>
            <PropertyValue
              label={t(`${K}.result.contours`)}
              value={format.list([
                t(`${K}.result.loops`, { count: closedCount }),
                t(`${K}.result.chains`, { count: openCount }),
              ])}
            />
            <PropertyValue label={t(`${K}.result.noise`)} value={format.length(result.noise)} />
            <PropertyValue
              label={t(`${K}.result.suggested`)}
              value={`±${format.length(result.suggestedTolerance)}`}
            />
            {result.folded && (
              <InlineMessage severity="info">{t(`${K}.result.folded`)}</InlineMessage>
            )}
            {result.polylines.length === 0 && (
              <InlineMessage severity="warning">{t(`${K}.result.empty`)}</InlineMessage>
            )}
          </>
        )}
        {preview.status === 'error' && (
          <InlineMessage severity="error" details={preview.error.details}>
            {describeError(preview.error, t)}
          </InlineMessage>
        )}
      </PanelSection>
    </>
  );
}
