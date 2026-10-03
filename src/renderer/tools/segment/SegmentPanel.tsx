import { Cone, Cylinder, type LucideIcon, Torus } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { PrimitiveKind } from '@shared/protocol/generated/fitting-primitives';
import { SEGMENT_PARAMS_RANGES, type SegmentedRegion } from '@shared/protocol/generated/regions';

import { useFormatter } from '../../i18n/useFormatter';
import { describeError } from '../../kernel/describeError';
import { kernel } from '../../kernel/kernel';
import { useSelectedFaceCount } from '../../selection/api';
import { selectedFacesAt } from '../../selection/selectedFacesAt';
import { useSelectionState } from '../../selection/selectionStore';
import { useDocument } from '../../state/documentStore';
import { setDisplayMode } from '../../state/viewStore';
import { Button } from '../../ui/Button/Button';
import { Checkbox } from '../../ui/Checkbox/Checkbox';
import { PlaneIcon, SphereIcon } from '../../ui/icons/customIcons';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { NumberField } from '../../ui/NumberField/NumberField';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { ProgressBar } from '../../ui/ProgressBar/ProgressBar';
import { PropertyRow, PropertyValue } from '../../ui/PropertyRow/PropertyRow';
import { getViewport } from '../../viewport/api';
import { REGION_PALETTE } from '../../viewport/palette';
import { useCommit } from '../framework/hooks';
import { ToolPanel } from '../framework/ToolPanel';
import type { ToolPanelProps } from '../framework/types';
import styles from './SegmentPanel.module.css';
import { type PreviewParams, useSegmentPreview } from './useSegmentPreview';

export const DEFAULT_SENSITIVITY = 50;
export const DEFAULT_MIN_AREA = 2;

const KIND_ICONS: Record<PrimitiveKind, LucideIcon> = {
  plane: PlaneIcon,
  cylinder: Cylinder,
  cone: Cone,
  sphere: SphereIcon,
  torus: Torus,
};

/** Largest regions first; the list is what the user checks before OK. */
export function sortedRegions(regions: readonly SegmentedRegion[]): SegmentedRegion[] {
  return [...regions].sort((a, b) => b.faceCount - a.faceCount || a.label - b.label);
}

function RegionList({ regions }: { regions: readonly SegmentedRegion[] }) {
  const { t } = useTranslation(['tools', 'panels', 'selection']);
  const format = useFormatter();
  return (
    <ul className={styles.list} data-testid="segment-regions">
      {sortedRegions(regions).map((region) => {
        const Icon = KIND_ICONS[region.kind];
        const kindName = t(`panels:regionKind.${region.kind}`);
        return (
          <li key={region.label} className={styles.row}>
            <span
              className={styles.swatch}
              style={{ background: REGION_PALETTE[region.colorIndex % REGION_PALETTE.length] }}
              aria-hidden
            />
            <Icon size={16} aria-label={kindName} />
            <span className={styles.name}>
              {t('selection:regions.defaultName', { number: region.label })}
            </span>
            <span className={styles.value}>{format.length(region.rms)}</span>
            <span className={styles.value}>{format.count(region.faceCount)}</span>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Segmentieren: splits the scan (or the selection) into regions of single
 * shapes. The dry run shows the regions in colour; OK stores them.
 */
export function SegmentPanel({ close }: ToolPanelProps) {
  const { t } = useTranslation();
  const format = useFormatter();
  const scan = useDocument((state) => state.snapshot?.document.scan ?? null);
  const revision = useDocument((state) => state.snapshot?.revision ?? null);
  const selectionCount = useSelectedFaceCount();
  const [sensitivity, setSensitivity] = useState(DEFAULT_SENSITIVITY);
  const [minArea, setMinArea] = useState(DEFAULT_MIN_AREA);
  const [onlySelection, setOnlySelection] = useState(false);
  const selectionOnly = onlySelection && selectionCount > 0;
  const selectionVersion = useSelectionState((state) => state.version);
  const scanKey = scan?.key ?? null;

  const params = useMemo<PreviewParams | null>(() => {
    if (!scanKey || revision === null) return null;
    return {
      scanKey,
      sensitivity,
      minArea,
      faces: selectionOnly ? selectedFacesAt(scanKey, selectionVersion) : null,
    };
  }, [scanKey, revision, sensitivity, minArea, selectionOnly, selectionVersion]);

  const { preview, cancel, restart } = useSegmentPreview(params);
  const result =
    preview.status === 'ok'
      ? preview.result
      : preview.status === 'computing'
        ? preview.previous
        : null;

  useEffect(() => {
    const view = getViewport()?.scan;
    if (!view) return;
    if (result?.labels && result.colorIndex && view.scanKey === scanKey) {
      view.setRegions(result.labels, result.colorIndex);
    }
  }, [result, scanKey]);
  useEffect(() => () => getViewport()?.scan.setRegions(null, null), []);

  const run = useCallback(async () => {
    if (!params) return;
    await kernel().call('regions.segment', { ...params, dryRun: false }).result;
    getViewport()?.scan.setRegions(null, null);
    setDisplayMode('regions');
    close();
  }, [params, close]);
  const commit = useCommit(run);
  const canCommit = preview.status === 'ok' && preview.result.regions.length > 0;
  const ranges = SEGMENT_PARAMS_RANGES;

  return (
    <ToolPanel
      toolId="segment"
      canCommit={canCommit}
      busy={commit.busy}
      onCommit={() => void commit.commit()}
      onCancel={close}
    >
      <PanelSection title={t('common:sections.input')}>
        <PropertyValue
          label={t('tools:segment.scan')}
          value={
            scan
              ? t('common:status.faces', {
                  count: scan.faceCount,
                  formatted: format.count(scan.faceCount),
                })
              : t('errors:regions.noScan')
          }
        />
        <Checkbox
          checked={onlySelection}
          disabled={selectionCount === 0}
          label={t('tools:segment.onlySelection', {
            count: selectionCount,
            formatted: format.count(selectionCount),
          })}
          testId="segment-only-selection"
          onChange={setOnlySelection}
        />
      </PanelSection>
      <PanelSection title={t('common:sections.parameters')}>
        <PropertyRow label={t('tools:segment.sensitivity')} htmlFor="segment-sensitivity">
          <div className={styles.slider}>
            <input
              type="range"
              className={styles.range}
              min={ranges.sensitivity.min}
              max={ranges.sensitivity.max}
              step={1}
              value={sensitivity}
              aria-label={t('tools:segment.sensitivity')}
              data-testid="segment-sensitivity-slider"
              onChange={(event) => setSensitivity(Number(event.currentTarget.value))}
            />
            <span className={styles.sliderField}>
              <NumberField
                id="segment-sensitivity"
                kind="count"
                min={ranges.sensitivity.min}
                max={ranges.sensitivity.max}
                value={sensitivity}
                onCommit={(value) => setSensitivity(Math.round(value))}
              />
            </span>
          </div>
        </PropertyRow>
        <p className={styles.hint}>{t('tools:segment.sensitivityHint')}</p>
        <PropertyRow label={t('tools:segment.minArea')} htmlFor="segment-min-area">
          <NumberField
            id="segment-min-area"
            kind="plain"
            unit={t('tools:segment.areaUnit')}
            decimals={1}
            step={0.5}
            min={ranges.minArea.min}
            max={ranges.minArea.max}
            value={minArea}
            onCommit={setMinArea}
          />
        </PropertyRow>
      </PanelSection>
      <PanelSection title={t('common:sections.result')}>
        {preview.status === 'computing' && (
          <div className={styles.progress}>
            <ProgressBar
              fraction={preview.fraction}
              label={preview.stage ? t(`progress:${preview.stage}`) : t('common:tool.computing')}
            />
            <div className={styles.progressRow}>
              <span className={styles.hint}>
                {preview.stage ? t(`progress:${preview.stage}`) : t('common:tool.computing')}
              </span>
              <Button variant="ghost" data-testid="segment-cancel-preview" onClick={cancel}>
                {t('tools:segment.stop')}
              </Button>
            </div>
          </div>
        )}
        {preview.status === 'cancelled' && (
          <div className={styles.progressRow}>
            <span className={styles.hint}>{t('tools:segment.stopped')}</span>
            <Button data-testid="segment-restart" onClick={restart}>
              {t('tools:segment.compute')}
            </Button>
          </div>
        )}
        {preview.status === 'error' && (
          <InlineMessage severity="error" details={preview.error.details}>
            {describeError(preview.error, t)}
          </InlineMessage>
        )}
        {commit.error && (
          <InlineMessage severity="error" details={commit.error.details}>
            {describeError(commit.error, t)}
          </InlineMessage>
        )}
        {result && (
          <>
            <PropertyValue
              label={t('tools:segment.found')}
              value={t('tools:segment.regionCount', { count: result.regions.length })}
            />
            {result.regions.length === 0 ? (
              <p className={styles.hint}>{t('tools:segment.nothingFound')}</p>
            ) : (
              <RegionList regions={result.regions} />
            )}
          </>
        )}
      </PanelSection>
    </ToolPanel>
  );
}
