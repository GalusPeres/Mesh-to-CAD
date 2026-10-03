import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { Feature } from '@shared/protocol/generated/document-model';
import type { SketchParams } from '@shared/protocol/generated/sketch-params';

import { featureNames } from '../../features/registry';
import { useFormatter } from '../../i18n/useFormatter';
import { describeError } from '../../kernel/describeError';
import { type KernelFailure, isSilentFailure } from '../../kernel/KernelFailure';
import { kernel } from '../../kernel/kernel';
import { documentStore, useDocument } from '../../state/documentStore';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { ToolPanel } from '../framework/ToolPanel';
import { toFailure, useCommit, usePreview } from '../framework/hooks';
import { closeTool } from '../framework/toolActions';
import type { ToolPanelProps } from '../framework/types';
import { sectionText } from './describe';
import { PlaneStep } from './PlaneStep';
import { emptySketch, scanCenter, sectionFor } from './planeChoice';
import { SketchStep } from './SketchStep';
import { FIT_LANE, useSketchDraft } from './useSketchDraft';

/** Stable fallback, so the store selector does not return a new array on every call. */
const NO_FEATURES: readonly never[] = [];

const TOOL_ID = 'section-sketch';

function isRefitRequest(activation: unknown): boolean {
  return typeof activation === 'object' && activation !== null && 'refit' in activation;
}

function storedSketch(feature: Feature | undefined): SketchParams | null {
  return feature?.type === 'sketch' ? (feature.params as unknown as SketchParams) : null;
}

/** Section sketch: choose the plane (step 1), then fit and edit the sketch (step 2). */
export function SketchPanel({ activation, editTarget, close }: ToolPanelProps) {
  const { t } = useTranslation(['tools', 'common']);
  const format = useFormatter();
  const features = useDocument((state) => state.snapshot?.document.features ?? NO_FEATURES);
  const hasScan = useDocument((state) => !!state.snapshot?.document.scan);
  const edited = editTarget ? features.find((feature) => feature.id === editTarget) : undefined;

  const [initial] = useState<SketchParams>(() => {
    const stored = storedSketch(edited);
    if (stored) return stored;
    const scan = documentStore.getState().snapshot?.scene.scan;
    const start = emptySketch({
      type: 'planar',
      plane: { type: 'standard', plane: 'XY' },
      offset: 0,
      sectionOffset: 0,
      xDirection: null,
      flip: false,
    });
    return {
      ...start,
      section: sectionFor('XY', start.section, { plane: null, axis: 'Z' }, scanCenter(scan)),
    };
  });
  const [step, setStep] = useState<'plane' | 'sketch'>(
    initial.entities.length ? 'sketch' : 'plane',
  );
  const sketch = useSketchDraft(initial, step === 'sketch');
  const { draft } = sketch;

  const sectionKey = JSON.stringify(draft.section);
  const sectionParams = useMemo(
    () => (hasScan ? { section: JSON.parse(sectionKey) as SketchParams['section'] } : null),
    [sectionKey, hasScan],
  );
  const section = usePreview('sketch.section', sectionParams, TOOL_ID);
  const sectionResult =
    section.status === 'ok'
      ? section.result
      : section.status === 'computing'
        ? section.previous
        : null;

  const names = useMemo(() => {
    const withDraft = edited
      ? features
      : [...features, { id: '', type: 'sketch', name: null, suppressed: false, params: null }];
    return featureNames(withDraft, t);
  }, [features, edited, t]);
  const sketchName = names.get(editTarget ?? '') ?? '';

  // "Neu anpassen" in the properties of a sketch opens the tool with a new fit.
  const [refitOnOpen] = useState(() => isRefitRequest(activation) && !!edited);
  const [fitting, setFitting] = useState(refitOnOpen);
  const [fitError, setFitError] = useState<KernelFailure | null>(null);
  const { accept } = sketch;
  const runFit = useCallback(
    (source: SketchParams) => {
      const base = {
        ...emptySketch(source.section),
        tolerance: source.tolerance,
        rejectedSnaps: source.rejectedSnaps,
      };
      return kernel()
        .call('sketch.autoFit', { sketch: base, refit: false }, { lane: FIT_LANE })
        .result.then((result) => {
          accept(result);
          setStep('sketch');
          setFitError(null);
        })
        .catch((error: unknown) => {
          if (!isSilentFailure(error)) setFitError(toFailure(error));
        })
        .finally(() => setFitting(false));
    },
    [accept],
  );
  const fitSection = useCallback(() => {
    setFitting(true);
    void runFit(draft);
  }, [runFit, draft]);
  useEffect(() => {
    if (refitOnOpen) void runFit(initial);
  }, [refitOnOpen, runFit, initial]);

  const finish = useCallback(async () => {
    const params = (await sketch.settled()) as unknown as Record<string, unknown>;
    const revision = documentStore.getState().snapshot?.revision ?? 0;
    const op = editTarget
      ? { type: 'updateFeature' as const, id: editTarget, params }
      : { type: 'addFeature' as const, feature: { type: 'sketch', params } };
    await kernel().call('doc.apply', { baseRevision: revision, ops: [op], label: 'sketch' }).result;
    close();
  }, [sketch, editTarget, close]);
  const commit = useCommit(finish);

  const planeText = sectionText(draft.section, names, format, t);
  const caption = t('tools:sectionSketch.caption.title', { name: sketchName, plane: planeText });

  const canCommit =
    step === 'plane'
      ? section.status === 'ok' && section.result.polylines.length > 0 && !fitting
      : draft.entities.length > 0;

  return (
    <ToolPanel
      toolId={TOOL_ID}
      editingName={edited ? sketchName : undefined}
      canCommit={canCommit}
      busy={commit.busy || fitting}
      onCommit={() => (step === 'plane' ? fitSection() : void commit.commit())}
      onCancel={() => void closeTool()}
    >
      {!hasScan && <InlineMessage severity="info">{t('sectionSketch.noScan')}</InlineMessage>}
      {step === 'plane' ? (
        <PlaneStep
          sketch={sketch}
          features={features}
          editTarget={editTarget}
          names={names}
          preview={section}
        />
      ) : (
        <SketchStep
          sketch={sketch}
          section={sectionResult}
          caption={caption}
          planeText={planeText}
          onChangePlane={() => setStep('plane')}
          onRefit={fitSection}
          refitting={fitting}
        />
      )}
      {fitError && (
        <InlineMessage severity="error" details={fitError.details}>
          {describeError(fitError, t)}
        </InlineMessage>
      )}
      {commit.error && (
        <InlineMessage severity="error" details={commit.error.details}>
          {describeError(commit.error, t)}
        </InlineMessage>
      )}
    </ToolPanel>
  );
}
