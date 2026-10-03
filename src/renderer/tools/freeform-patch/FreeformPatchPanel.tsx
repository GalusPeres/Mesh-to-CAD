import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { FreeformPatchParams } from '@shared/protocol/generated/feature-freeform-patch';
import { MIN_FIT_FACES } from '@shared/protocol/generated/limits';

import { featureNames } from '../../features/registry';
import { useFormatter } from '../../i18n/useFormatter';
import { describeError } from '../../kernel/describeError';
import { kernel } from '../../kernel/kernel';
import { regionName } from '../../panels/treeModel';
import { selectedFaces } from '../../selection/api';
import { useSelectionState } from '../../selection/selectionStore';
import { currentRevision, useDocument } from '../../state/documentStore';
import { Checkbox } from '../../ui/Checkbox/Checkbox';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { NumberField } from '../../ui/NumberField/NumberField';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyRow, PropertyValue } from '../../ui/PropertyRow/PropertyRow';
import { SegmentedControl } from '../../ui/SegmentedControl/SegmentedControl';
import { Select } from '../../ui/Select/Select';
import { ToolPanel } from '../framework/ToolPanel';
import { useCommit, usePreview } from '../framework/hooks';
import type { ToolPanelProps } from '../framework/types';
import styles from './FreeformPatchPanel.module.css';
import {
  DEFAULT_MARGIN_MM,
  DEFAULT_SPANS,
  SMOOTHING_LEVELS,
  SPAN_RANGE,
  type SmoothingLevel,
  clampSpans,
  regionFaces,
  smoothingLevel,
  useEditedFeatureFaces,
} from './patchInput';
import { PatchResultList } from './PatchResultList';
import { usePatchViewport } from './usePatchViewport';

const KEY = 'tools:freeformPatch';
type Source = 'selection' | 'region';

/** The triangles the patch is fitted to: the working selection or a region. */
function useInputFaces(
  source: Source,
  regionId: string | null,
  ready: boolean,
): Uint32Array | null {
  const scanKey = useDocument((state) => state.snapshot?.document.scan?.key ?? null);
  const regionsKey = useDocument((state) => state.snapshot?.scene.regions ?? null);
  const region = useDocument(
    (state) => state.snapshot?.document.regions.items.find((item) => item.id === regionId) ?? null,
  );
  const version = useSelectionState((state) => state.version);
  const [regionInput, setRegionInput] = useState<{ key: string; faces: Uint32Array } | null>(null);
  const regionKey = region && regionsKey ? `${regionsKey}:${region.label}` : null;

  useEffect(() => {
    if (source !== 'region' || !region || !regionsKey || !regionKey) return;
    let current = true;
    void regionFaces(regionsKey, region.label).then((faces) => {
      if (current) setRegionInput({ key: regionKey, faces });
    });
    return () => {
      current = false;
    };
  }, [source, region, regionsKey, regionKey]);

  const selection = useMemo(
    () => (ready && source === 'selection' && scanKey ? selectedFaces(scanKey) : null),
    // `version` changes whenever the selection does.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [ready, source, scanKey, version],
  );
  if (source === 'selection') return selection;
  return regionInput?.key === regionKey ? regionInput.faces : null;
}

/** A B-spline patch fitted to scan triangles, drawn over the scan until OK. */
export function FreeformPatchPanel({ editTarget, close }: ToolPanelProps) {
  const { t } = useTranslation();
  const format = useFormatter();
  const snapshot = useDocument((state) => state.snapshot);
  const stored = useMemo(() => {
    const feature = snapshot?.document.features.find((item) => item.id === editTarget);
    return feature?.type === 'freeformPatch'
      ? (feature.params as unknown as FreeformPatchParams)
      : null;
    // Only the parameters the tool was opened with.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editTarget]);
  const regions = snapshot?.document.regions.items ?? [];
  const [source, setSource] = useState<Source>(stored?.sourceRegion ? 'region' : 'selection');
  const [regionId, setRegionId] = useState<string | null>(stored?.sourceRegion ?? null);
  const [autoSpans, setAutoSpans] = useState(stored ? stored.spans === null : true);
  const [spans, setSpans] = useState<[number, number]>(stored?.spans ?? DEFAULT_SPANS);
  const [smoothing, setSmoothing] = useState<SmoothingLevel>(
    stored ? smoothingLevel(stored.smoothing) : 'medium',
  );
  const [margin, setMargin] = useState(stored?.margin ?? DEFAULT_MARGIN_MM);
  const ready = useEditedFeatureFaces(editTarget);
  const faces = useInputFaces(source, regionId, ready);
  const enough = faces !== null && faces.length >= MIN_FIT_FACES;

  const params = useMemo(
    () =>
      enough
        ? {
            faces,
            spans: autoSpans ? null : spans,
            smoothing: SMOOTHING_LEVELS[smoothing],
            margin,
          }
        : null,
    [enough, faces, autoSpans, spans, smoothing, margin],
  );
  const preview = usePreview('freeform.preview', params, 'freeform-patch');
  const result = preview.status === 'ok' ? preview.result : null;
  usePatchViewport(params?.faces ?? null, result, preview.status === 'computing');

  const apply = useCallback(async () => {
    const baseRevision = currentRevision();
    if (!params || baseRevision === null) return;
    const featureParams = {
      ...params,
      sourceRegion: source === 'region' ? regionId : null,
    };
    const op = editTarget
      ? { type: 'updateFeature' as const, id: editTarget, params: featureParams }
      : { type: 'addFeature' as const, feature: { type: 'freeformPatch', params: featureParams } };
    await kernel().call('doc.apply', { baseRevision, ops: [op], label: 'freeformPatch' }).result;
    close();
  }, [params, source, regionId, editTarget, close]);
  const commit = useCommit(apply);

  const names = useMemo(
    () => featureNames(snapshot?.document.features ?? [], t),
    [snapshot?.document.features, t],
  );
  const count = faces?.length ?? 0;
  const tolerance = snapshot?.document.settings.tolerance ?? 0;

  return (
    <ToolPanel
      toolId="freeform-patch"
      editingName={editTarget ? names.get(editTarget) : undefined}
      canCommit={result !== null}
      busy={commit.busy}
      onCommit={() => void commit.commit()}
      onCancel={close}
    >
      <PanelSection title={t('common:sections.input')}>
        {regions.length > 0 && (
          <PropertyRow label={t(`${KEY}.source`)}>
            <SegmentedControl<Source>
              value={source}
              ariaLabel={t(`${KEY}.source`)}
              segments={[
                { value: 'selection', label: t(`${KEY}.sources.selection`) },
                { value: 'region', label: t(`${KEY}.sources.region`) },
              ]}
              onChange={setSource}
            />
          </PropertyRow>
        )}
        {source === 'region' && (
          <PropertyRow label={t(`${KEY}.region`)}>
            <Select<string>
              value={regionId ?? ''}
              ariaLabel={t(`${KEY}.region`)}
              options={[
                ...(regionId ? [] : [{ value: '', label: t(`${KEY}.choose`) }]),
                ...regions.map((region) => ({ value: region.id, label: regionName(region, t) })),
              ]}
              onChange={(value) => setRegionId(value || null)}
            />
          </PropertyRow>
        )}
        <PropertyValue label={t(`${KEY}.triangles`)} value={format.count(count)} />
        {!enough && (
          <p className={styles.hint}>
            {t(`${KEY}.inputMissing`, { min: format.count(MIN_FIT_FACES) })}
          </p>
        )}
      </PanelSection>
      <PanelSection title={t('common:sections.parameters')}>
        <Checkbox checked={autoSpans} label={t(`${KEY}.autoSpans`)} onChange={setAutoSpans} />
        {!autoSpans &&
          (['u', 'v'] as const).map((direction, index) => (
            <PropertyRow key={direction} label={t(`${KEY}.spans.${direction}`)}>
              <NumberField
                kind="count"
                value={spans[index] ?? SPAN_RANGE.min}
                min={SPAN_RANGE.min}
                max={SPAN_RANGE.max}
                onCommit={(value) =>
                  setSpans((current) =>
                    index === 0 ? [clampSpans(value), current[1]] : [current[0], clampSpans(value)],
                  )
                }
              />
            </PropertyRow>
          ))}
        <PropertyRow label={t(`${KEY}.smoothing`)}>
          <SegmentedControl<SmoothingLevel>
            value={smoothing}
            ariaLabel={t(`${KEY}.smoothing`)}
            segments={(['low', 'medium', 'high'] as const).map((value) => ({
              value,
              label: t(`${KEY}.smoothingLevels.${value}`),
            }))}
            onChange={setSmoothing}
          />
        </PropertyRow>
        <PropertyRow label={t(`${KEY}.margin`)}>
          <NumberField value={margin} min={0} max={50} onCommit={setMargin} />
        </PropertyRow>
      </PanelSection>
      <PanelSection title={t('common:sections.result')}>
        {preview.status === 'idle' && <p className={styles.hint}>{t(`${KEY}.inputsFirst`)}</p>}
        {preview.status === 'computing' && (
          <p className={styles.hint}>{t('common:tool.computing')}</p>
        )}
        {preview.status === 'error' && (
          <InlineMessage severity="error" details={preview.error.details}>
            {describeError(preview.error, t)}
          </InlineMessage>
        )}
        {result && <PatchResultList result={result} tolerance={tolerance} />}
        {commit.error && (
          <InlineMessage severity="error" details={commit.error.details}>
            {describeError(commit.error, t)}
          </InlineMessage>
        )}
      </PanelSection>
    </ToolPanel>
  );
}
