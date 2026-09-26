import { Check, TriangleAlert } from 'lucide-react';
import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { ErrorInfo } from '@shared/protocol/generated/document-results';
import type {
  AutoSurfaceParams,
  SurfaceDetail,
  SurfaceSmoothing,
} from '@shared/protocol/generated/feature-auto-surface';
import { MIN_FIT_FACES } from '@shared/protocol/generated/limits';

import { featureNames } from '../../features/registry';
import { useFormatter } from '../../i18n/useFormatter';
import { describeError } from '../../kernel/describeError';
import { kernel } from '../../kernel/kernel';
import { selectedFaces } from '../../selection/api';
import { useSelectionState } from '../../selection/selectionStore';
import { currentRevision, useDocument } from '../../state/documentStore';
import { Button } from '../../ui/Button/Button';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { ProgressBar } from '../../ui/ProgressBar/ProgressBar';
import { PropertyRow, PropertyValue } from '../../ui/PropertyRow/PropertyRow';
import { SegmentedControl } from '../../ui/SegmentedControl/SegmentedControl';
import { ToolPanel } from '../framework/ToolPanel';
import { useCommit } from '../framework/hooks';
import type { ToolPanelProps } from '../framework/types';
import styles from './AutoSurfacePanel.module.css';
import {
  DEFAULT_DETAIL,
  DEFAULT_SMOOTHING,
  DETAILS,
  SMOOTHINGS,
  type Source,
  autoSurfaceInput,
  autoSurfaceOps,
  surfaceStats,
} from './model';
import {
  AUTO_SURFACE_TOOL_ID,
  type AutoSurfacePreview,
  useAutoSurfacePreview,
} from './useAutoSurfacePreview';
import { useEditedFaces } from './useEditedFaces';

const KEY = 'tools:autoSurface';

type TFunction = ReturnType<typeof useTranslation>['t'];

function featureError(error: ErrorInfo, t: TFunction): string {
  const message = t(`errors:${error.code}`, { ...error.params, defaultValue: '' });
  return message || t('common:unexpectedError');
}

/** The selected triangles, recomputed whenever the selection changes. */
function useSelection(active: boolean): Uint32Array | null {
  const scanKey = useDocument((state) => state.snapshot?.document.scan?.key ?? null);
  const version = useSelectionState((state) => state.version);
  return useMemo(
    () => (active && scanKey ? selectedFaces(scanKey) : null),
    // `version` changes whenever the selection does.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [active, scanKey, version],
  );
}

/**
 * Auto-Flächen: the scan (or the selected triangles) becomes a network of B-spline
 * patches on a fitted Catmull-Clark cage, a solid body when the scan is closed.
 */
export function AutoSurfacePanel({ editTarget, close }: ToolPanelProps) {
  const { t } = useTranslation();
  const format = useFormatter();
  const snapshot = useDocument((state) => state.snapshot);
  const stored = useMemo(() => {
    const feature = snapshot?.document.features.find((item) => item.id === editTarget);
    return feature?.type === 'autoSurface'
      ? (feature.params as unknown as AutoSurfaceParams)
      : null;
    // Only the parameters the tool was opened with.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editTarget]);
  const [detail, setDetail] = useState<SurfaceDetail>(stored?.detail ?? DEFAULT_DETAIL);
  const [smoothing, setSmoothing] = useState<SurfaceSmoothing>(
    stored?.smoothing ?? DEFAULT_SMOOTHING,
  );
  // A feature made from selected triangles opens with its triangles as the selection.
  const [chosenSource, setSource] = useState<Source | null>(null);
  const source: Source = chosenSource ?? (stored?.faces ? 'selection' : 'scan');
  const edited = useEditedFaces(editTarget);

  const selection = useSelection(edited.ready && source === 'selection');
  const input = useMemo(
    () =>
      edited.ready ? autoSurfaceInput(source, selection, detail, smoothing, MIN_FIT_FACES) : null,
    [edited.ready, source, selection, detail, smoothing],
  );
  const revision = snapshot?.revision ?? null;
  const ops = useMemo(
    () => (input ? autoSurfaceOps(editTarget, input) : null),
    [input, editTarget],
  );
  const previewParams = useMemo(
    () => (ops && revision !== null ? { baseRevision: revision, ops } : null),
    [ops, revision],
  );
  const { preview, cancel, restart } = useAutoSurfacePreview(previewParams);

  const apply = useCallback(async () => {
    const baseRevision = currentRevision();
    if (!ops || baseRevision === null) return;
    await kernel().call('doc.apply', { baseRevision, ops, label: 'autoSurface' }).result;
    close();
  }, [ops, close]);
  const commit = useCommit(apply);

  const names = useMemo(
    () => featureNames(snapshot?.document.features ?? [], t),
    [snapshot?.document.features, t],
  );
  const state = preview.status === 'ok' ? preview.result.status?.state : undefined;
  const canCommit = state === 'ok' || state === 'warning';
  const selectionCount = selection?.length ?? 0;

  return (
    <ToolPanel
      toolId={AUTO_SURFACE_TOOL_ID}
      editingName={editTarget ? names.get(editTarget) : undefined}
      canCommit={canCommit}
      busy={commit.busy}
      onCommit={() => void commit.commit()}
      onCancel={close}
    >
      <PanelSection title={t('common:sections.input')}>
        <PropertyRow label={t(`${KEY}.source`)}>
          <SegmentedControl<Source>
            value={source}
            ariaLabel={t(`${KEY}.source`)}
            segments={[
              { value: 'scan', label: t(`${KEY}.sources.scan`) },
              { value: 'selection', label: t(`${KEY}.sources.selection`) },
            ]}
            onChange={setSource}
          />
        </PropertyRow>
        {source === 'selection' && (
          <>
            <PropertyValue label={t(`${KEY}.triangles`)} value={format.count(selectionCount)} />
            {selectionCount < MIN_FIT_FACES && (
              <p className={styles.hint}>
                {t(`${KEY}.selectionMissing`, { min: format.count(MIN_FIT_FACES) })}
              </p>
            )}
          </>
        )}
      </PanelSection>
      <PanelSection title={t('common:sections.parameters')}>
        <PropertyRow label={t(`${KEY}.detail`)}>
          <SegmentedControl<SurfaceDetail>
            value={detail}
            ariaLabel={t(`${KEY}.detail`)}
            segments={DETAILS.map((value) => ({ value, label: t(`${KEY}.details.${value}`) }))}
            onChange={setDetail}
          />
        </PropertyRow>
        <PropertyRow label={t(`${KEY}.smoothing`)}>
          <SegmentedControl<SurfaceSmoothing>
            value={smoothing}
            ariaLabel={t(`${KEY}.smoothing`)}
            segments={SMOOTHINGS.map((value) => ({
              value,
              label: t(`${KEY}.smoothingLevels.${value}`),
            }))}
            onChange={setSmoothing}
          />
        </PropertyRow>
      </PanelSection>
      <PanelSection title={t('common:sections.result')}>
        <PreviewState preview={preview} onCancel={cancel} onRestart={restart} />
        {commit.error && (
          <InlineMessage severity="error" details={commit.error.details}>
            {describeError(commit.error, t)}
          </InlineMessage>
        )}
      </PanelSection>
    </ToolPanel>
  );
}

interface PreviewStateProps {
  preview: AutoSurfacePreview;
  onCancel: () => void;
  onRestart: () => void;
}

function PreviewState({ preview, onCancel, onRestart }: PreviewStateProps) {
  const { t } = useTranslation();
  switch (preview.status) {
    case 'idle':
      return <p className={styles.hint}>{t(`${KEY}.inputsFirst`)}</p>;
    case 'computing': {
      const label = preview.stage ? t(`progress:${preview.stage}`) : t('common:tool.computing');
      return (
        <div className={styles.progress} data-testid="auto-surface-progress">
          <ProgressBar fraction={preview.fraction} label={label} />
          <div className={styles.progressRow}>
            <span className={styles.hint}>{label}</span>
            <Button variant="ghost" data-testid="auto-surface-stop" onClick={onCancel}>
              {t(`${KEY}.stop`)}
            </Button>
          </div>
        </div>
      );
    }
    case 'cancelled':
      return (
        <div className={styles.progressRow}>
          <span className={styles.hint}>{t(`${KEY}.stopped`)}</span>
          <Button data-testid="auto-surface-restart" onClick={onRestart}>
            {t(`${KEY}.compute`)}
          </Button>
        </div>
      );
    case 'error':
      return (
        <InlineMessage severity="error" details={preview.error.details}>
          {describeError(preview.error, t)}
        </InlineMessage>
      );
    case 'ok':
      return <SurfaceResult preview={preview} />;
  }
}

function SurfaceResult({ preview }: { preview: Extract<AutoSurfacePreview, { status: 'ok' }> }) {
  const { t } = useTranslation();
  const format = useFormatter();
  const status = preview.result.status;
  const stats = surfaceStats(status);
  const body = preview.result.bodies[0];
  const valid = body?.valid ?? false;
  const Verdict = valid ? Check : TriangleAlert;
  return (
    <div data-testid="auto-surface-result">
      {status?.error && (
        <InlineMessage severity="error" details={status.error.details ?? undefined}>
          {featureError(status.error, t)}
        </InlineMessage>
      )}
      {status?.issues.map((issue) => (
        <InlineMessage key={issue.code} severity="warning">
          {t(`issues:${issue.code}`, issue.params)}
        </InlineMessage>
      ))}
      {stats && (
        <>
          <PropertyValue label={t(`${KEY}.result.patches`)} value={format.count(stats.patches)} />
          {stats.rms !== null && (
            <PropertyValue label={t(`${KEY}.result.rms`)} value={format.length(stats.rms)} />
          )}
          {stats.p95 !== null && (
            <PropertyValue label={t(`${KEY}.result.p95`)} value={format.length(stats.p95)} />
          )}
          {stats.max !== null && (
            <PropertyValue label={t(`${KEY}.result.max`)} value={format.length(stats.max)} />
          )}
          <PropertyValue
            label={t(`${KEY}.result.shape`)}
            value={
              stats.closed ? (
                <span className={styles.verdict}>
                  {t(`${KEY}.result.${valid ? 'validSolid' : 'invalidSolid'}`)}
                  <Verdict size={12} aria-hidden className={valid ? styles.pass : styles.fail} />
                </span>
              ) : (
                t(`${KEY}.result.openSurface`)
              )
            }
          />
          {body && (
            <PropertyValue label={t(`${KEY}.result.volume`)} value={format.volume(body.volume)} />
          )}
        </>
      )}
    </div>
  );
}
