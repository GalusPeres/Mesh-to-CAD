import { X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  FILLET_PARAMS_RANGES,
  type FilletParams,
  type FilletParamsInput,
} from '@shared/protocol/generated/feature-fillet';

import { setToolInfoProvider } from '../../automation/toolInfo';
import { featureNames } from '../../features/registry';
import { describeError } from '../../kernel/describeError';
import { kernel } from '../../kernel/kernel';
import { useDocument } from '../../state/documentStore';
import { setDraftHistoryHandler } from '../../state/historyStore';
import { setDraftDirty } from '../../state/toolStore';
import { Button } from '../../ui/Button/Button';
import { IconButton } from '../../ui/IconButton/IconButton';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { NumberField } from '../../ui/NumberField/NumberField';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyRow, PropertyValue } from '../../ui/PropertyRow/PropertyRow';
import { SegmentedControl } from '../../ui/SegmentedControl/SegmentedControl';
import type { PickHit } from '../../viewport/api';
import { ToolPanel } from '../framework/ToolPanel';
import { toFailure } from '../framework/hooks';
import type { ToolPanelProps } from '../framework/types';
import { availableBodies, isPositiveLength, storedParams } from '../extrude/solid/model';
import { SolidResult, useBodyLabel } from '../extrude/solid/SolidSections';
import { useSolidFeature } from '../extrude/solid/useSolidFeature';
import { edgeDraftReducer, initialDraft } from './edgeDraft';
import { edgeForRef, edgeRef, nearestEdge, pickTolerance, touchesFeature } from './edges';
import styles from './FilletPanel.module.css';
import {
  useBodyEdgePayload,
  useEdgePayloads,
  useEdgePickInteraction,
  useSelectedEdgesOverlay,
} from './useEdgePicking';

type Mode = FilletParams['mode'];
type Notice = 'otherBody' | 'ownEdge' | 'notOnBody';
type Measurement =
  | { status: 'running' }
  | { status: 'ok'; radius: number; measured: number; rms: number }
  | { status: 'error'; message: string; details?: string };

const MODES: readonly Mode[] = ['fillet', 'chamfer'];
const DEFAULT_SIZE_MM = 2;
const round3 = (value: number) => Math.round(value * 1000) / 1000;

/** Verrundung and Fase: pick edges in the viewport, choose the size, preview, commit. */
export function FilletPanel({ editTarget, close }: ToolPanelProps) {
  const { t } = useTranslation();
  const snapshot = useDocument((state) => state.snapshot);
  const bodyLabel = useBodyLabel();
  const stored = useMemo(
    () => storedParams<FilletParams>(snapshot, editTarget, 'fillet'),
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

  const [draft, dispatch] = useReducer(
    edgeDraftReducer,
    initialDraft(stored?.targetBody ?? null, stored?.edges ?? []),
  );
  const [mode, setMode] = useState<Mode>(stored?.mode ?? 'fillet');
  const [size, setSize] = useState(stored?.size ?? DEFAULT_SIZE_MM);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [measurement, setMeasurement] = useState<Measurement | null>(null);

  const loadPayload = useEdgePayloads();
  const payload = useBodyEdgePayload(draft.body, loadPayload);
  const faceTags = useMemo(
    () => snapshot?.status.bodies.find((body) => body.id === draft.body)?.faceTags ?? null,
    [snapshot, draft.body],
  );
  useSelectedEdgesOverlay(payload, faceTags, draft.edges);

  const latestDraft = useRef(draft);
  useEffect(() => {
    latestDraft.current = draft;
  });
  useEffect(() => {
    setDraftHistoryHandler({
      undo: () => {
        if (latestDraft.current.past.length === 0) return false;
        dispatch({ type: 'undo' });
        return true;
      },
      redo: () => {
        if (latestDraft.current.future.length === 0) return false;
        dispatch({ type: 'redo' });
        return true;
      },
    });
    return () => setDraftHistoryHandler(null);
  }, []);

  const pick = useCallback(
    (hit: Extract<PickHit, { kind: 'edge' }>) => {
      const current = latestDraft.current;
      if (!bodies.some((body) => body.id === hit.bodyId)) {
        setNotice('notOnBody');
        return;
      }
      if (current.body && current.edges.length && current.body !== hit.bodyId) {
        setNotice('otherBody');
        return;
      }
      const tags = snapshot?.status.bodies.find((body) => body.id === hit.bodyId)?.faceTags;
      void loadPayload(hit.bodyId).then((edges) => {
        if (!edges || !tags) return;
        const nearest = nearestEdge(edges, hit.point, pickTolerance(edges));
        const ref = nearest ? edgeRef(edges, tags, nearest.edge, hit.point) : null;
        if (!nearest || !ref) return;
        if (touchesFeature(ref, editTarget)) {
          setNotice('ownEdge');
          return;
        }
        const chosen = latestDraft.current.edges;
        const existing = chosen.findIndex((item) => edgeForRef(edges, tags, item) === nearest.edge);
        setNotice(null);
        setDraftDirty(true);
        dispatch({
          type: 'toggle',
          body: hit.bodyId,
          ref,
          existing: existing >= 0 ? existing : null,
        });
      });
    },
    [bodies, snapshot, loadPayload, editTarget],
  );
  useEdgePickInteraction(pick);

  const measure = useCallback(() => {
    if (!draft.body || draft.edges.length === 0) return;
    setMeasurement({ status: 'running' });
    kernel()
      .call(
        'fillet.scanRadius',
        { targetBody: draft.body, edges: draft.edges, before: editTarget },
        { lane: 'fillet.scanRadius' },
      )
      .result.then((result) => {
        setMeasurement({ status: 'ok', ...result });
        if (result.radius > 0) setSize(round3(result.radius));
      })
      .catch((error: unknown) => {
        const failure = toFailure(error);
        setMeasurement({
          status: 'error',
          message: describeError(failure, t),
          details: failure.details,
        });
      });
  }, [draft.body, draft.edges, editTarget, t]);

  const params = useMemo<FilletParamsInput | null>(() => {
    if (!draft.body || draft.edges.length === 0 || !isPositiveLength(size)) return null;
    return { targetBody: draft.body, edges: draft.edges, mode, size };
  }, [draft.body, draft.edges, mode, size]);
  const { preview, commit, deviation, previewOk } = useSolidFeature(
    'fillet',
    'fillet',
    editTarget,
    params as Record<string, unknown> | null,
    close,
  );

  useEffect(
    () =>
      setToolInfoProvider(() => ({
        state: { job: measurement?.status === 'running' },
        body: draft.body,
        edges: draft.edges.length,
        mode,
        size,
        measurement,
      })),
    [draft.body, draft.edges, mode, size, measurement],
  );

  const body = bodies.find((item) => item.id === draft.body);
  return (
    <ToolPanel
      toolId="fillet"
      editingName={editTarget ? names.get(editTarget) : undefined}
      canCommit={previewOk}
      busy={commit.busy}
      onCommit={() => void commit.commit()}
      onCancel={close}
    >
      <PanelSection title={t('common:sections.input')}>
        <PropertyValue
          label={t('tools:fillet.body')}
          value={body ? bodyLabel(body) : t('tools:fillet.noBodyYet')}
        />
        <p>{t('tools:fillet.edgeCount', { count: draft.edges.length })}</p>
        <ul className={styles.edges} aria-label={t('tools:fillet.edges')}>
          {draft.edges.map((ref, index) => (
            <li key={`${ref.faces.join('|')}@${ref.point.join(',')}`}>
              <PropertyRow label={t('tools:fillet.edge', { number: index + 1 })}>
                <IconButton
                  icon={X}
                  label={t('tools:fillet.removeEdge')}
                  onClick={() => {
                    setDraftDirty(true);
                    dispatch({ type: 'remove', index });
                  }}
                />
              </PropertyRow>
            </li>
          ))}
        </ul>
        {draft.edges.length === 0 && (
          <InlineMessage severity="info">{t('tools:fillet.pickHint')}</InlineMessage>
        )}
        {notice && (
          <InlineMessage severity="info">{t(`tools:fillet.notices.${notice}`)}</InlineMessage>
        )}
      </PanelSection>
      <PanelSection title={t('common:sections.parameters')}>
        <PropertyRow label={t('tools:fillet.mode')}>
          <SegmentedControl<Mode>
            value={mode}
            ariaLabel={t('tools:fillet.mode')}
            segments={MODES.map((value) => ({ value, label: t(`tools:fillet.modes.${value}`) }))}
            onChange={setMode}
          />
        </PropertyRow>
        <PropertyRow label={t(mode === 'fillet' ? 'tools:fillet.radius' : 'tools:fillet.distance')}>
          <NumberField value={size} min={FILLET_PARAMS_RANGES.size.min} onCommit={setSize} />
        </PropertyRow>
        {mode === 'fillet' && (
          <>
            <Button
              disabled={draft.edges.length === 0 || measurement?.status === 'running'}
              data-testid="fillet-from-scan"
              onClick={measure}
            >
              {t('tools:fillet.fromScan')}
            </Button>
            <MeasurementLine measurement={measurement} />
          </>
        )}
      </PanelSection>
      <SolidResult preview={preview} commitError={commit.error} deviation={deviation} />
    </ToolPanel>
  );
}

function MeasurementLine({ measurement }: { measurement: Measurement | null }) {
  const { t } = useTranslation();
  if (!measurement) return null;
  switch (measurement.status) {
    case 'running':
      return <p>{t('tools:fillet.measuring')}</p>;
    case 'ok':
      return (
        <p>
          {t(measurement.radius > 0 ? 'tools:fillet.measured' : 'tools:fillet.sharp', {
            value: measurement.radius,
            measured: measurement.measured,
            rms: measurement.rms,
          })}
        </p>
      );
    case 'error':
      return (
        <InlineMessage severity="error" details={measurement.details}>
          {measurement.message}
        </InlineMessage>
      );
  }
}
