import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { DEVIATION_PARAMS_RANGES } from '@shared/protocol/generated/inspection';

import { useFormatter } from '../../i18n/useFormatter';
import { minimumRange } from '../../inspection/deviationModel';
import {
  carryDeviationTo,
  setDeviationResult,
  setDeviationScheme,
  setDeviationVisible,
  setManualRange,
  setRangeMode,
  useDeviation,
} from '../../inspection/deviationStore';
import { bodyNames } from '../../inspection/names';
import { describeError } from '../../kernel/describeError';
import { kernel } from '../../kernel/kernel';
import { documentStore, useDocument } from '../../state/documentStore';
import { viewStore } from '../../state/viewStore';
import { Checkbox } from '../../ui/Checkbox/Checkbox';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { NumberField } from '../../ui/NumberField/NumberField';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyRow } from '../../ui/PropertyRow/PropertyRow';
import { SegmentedControl } from '../../ui/SegmentedControl/SegmentedControl';
import { Select } from '../../ui/Select/Select';
import type { DeviationScheme } from '../../viewport/palette';
import { ToolPanel } from '../framework/ToolPanel';
import { useCommit, usePreview } from '../framework/hooks';
import type { ToolPanelProps } from '../framework/types';
import { DeviationResultSection } from './DeviationResultSection';

const TOOL_ID = 'deviation';

function sameMembers(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((item) => b.includes(item));
}

/**
 * Compares the scan with the bodies: the map is computed when the panel opens and
 * whenever bodies or the search distance change; scale and scheme only recolour.
 */
export function DeviationPanel({ close }: ToolPanelProps) {
  const { t } = useTranslation(['tools', 'common']);
  const format = useFormatter();
  const snapshot = useDocument((state) => state.snapshot);
  const deviation = useDeviation((state) => state);
  const settings = snapshot?.document.settings;
  const bodies = useMemo(() => snapshot?.status.bodies ?? [], [snapshot]);
  const names = bodyNames(snapshot, t);
  const summary = deviation.summary;

  const [selected, setSelected] = useState<string[]>(() =>
    summary?.bodies.length ? summary.bodies : bodies.map((body) => body.id),
  );
  const [maxDistance, setMaxDistance] = useState(
    () => summary?.maxDistance ?? settings?.deviationMaxDistance ?? 2,
  );
  const [shownBefore] = useState(() => viewStore.getState().deviationVisible);

  useEffect(() => setDeviationVisible(true), []);

  const current = bodies.filter((body) => selected.includes(body.id)).map((body) => body.id);
  const upToDate =
    !!summary &&
    summary.revision === snapshot?.revision &&
    summary.maxDistance === maxDistance &&
    sameMembers(summary.bodies, current);
  const revision = snapshot?.revision;
  const selection = current.join(',');
  const params = useMemo(
    () =>
      upToDate || selection === '' || revision === undefined
        ? null
        : { bodies: selection.split(','), maxDistance },
    [upToDate, selection, maxDistance, revision],
  );
  const preview = usePreview('inspection.deviation', params, TOOL_ID);
  useEffect(() => {
    if (preview.status === 'ok') setDeviationResult(preview.result);
  }, [preview]);

  const commitHandler = useCallback(async () => {
    const latest = documentStore.getState().snapshot;
    if (latest && latest.document.settings.deviationMaxDistance !== maxDistance) {
      const { revision: next } = await kernel().call('doc.apply', {
        baseRevision: latest.revision,
        ops: [
          {
            type: 'setSettings',
            settings: { ...latest.document.settings, deviationMaxDistance: maxDistance },
          },
        ],
        label: 'settings',
      }).result;
      // The search distance is already in the map; the new revision changes nothing else.
      carryDeviationTo(next);
    }
    setDeviationVisible(true);
    close();
  }, [maxDistance, close]);
  const commit = useCommit(commitHandler);

  const cancel = () => {
    setDeviationVisible(shownBefore);
    close();
  };

  if (!snapshot || !settings) return null;
  const tolerance = settings.tolerance;
  const manualInvalid =
    deviation.rangeMode === 'manual' &&
    (deviation.manualRange === null || deviation.manualRange <= minimumRange(tolerance));
  const schemes: { value: DeviationScheme; label: string }[] = [
    { value: 'standard', label: t('deviation.schemes.standard') },
    { value: 'colorBlind', label: t('deviation.schemes.colorBlind') },
  ];

  return (
    <ToolPanel
      toolId={TOOL_ID}
      canCommit={upToDate}
      busy={commit.busy}
      onCommit={() => void commit.commit()}
      onCancel={cancel}
    >
      <PanelSection title={t('common:sections.input')}>
        <div role="group" aria-label={t('deviation.bodies')}>
          {bodies.map((body) => (
            <Checkbox
              key={body.id}
              label={names.get(body.id) ?? body.id}
              checked={selected.includes(body.id)}
              testId={`deviation-body-${body.id}`}
              onChange={(checked) =>
                setSelected(
                  checked ? [...selected, body.id] : selected.filter((id) => id !== body.id),
                )
              }
            />
          ))}
        </div>
        {current.length === 0 && (
          <InlineMessage severity="info">{t('deviation.noBodySelected')}</InlineMessage>
        )}
      </PanelSection>
      <PanelSection title={t('common:sections.parameters')}>
        <PropertyRow label={t('deviation.maxDistance')} htmlFor="deviation-max-distance">
          <NumberField
            id="deviation-max-distance"
            value={maxDistance}
            min={DEVIATION_PARAMS_RANGES.maxDistance.min}
            max={DEVIATION_PARAMS_RANGES.maxDistance.max}
            step={0.5}
            onCommit={setMaxDistance}
          />
        </PropertyRow>
      </PanelSection>
      <PanelSection title={t('common:sections.options')}>
        <PropertyRow label={t('deviation.scaleRange')}>
          <SegmentedControl
            value={deviation.rangeMode}
            ariaLabel={t('deviation.scaleRange')}
            segments={[
              { value: 'auto', label: t('deviation.rangeModes.auto') },
              { value: 'manual', label: t('deviation.rangeModes.manual') },
            ]}
            onChange={setRangeMode}
          />
        </PropertyRow>
        {deviation.rangeMode === 'manual' && (
          <PropertyRow label={t('deviation.range')} htmlFor="deviation-range">
            <NumberField
              id="deviation-range"
              value={deviation.manualRange}
              min={0}
              step={0.1}
              onCommit={setManualRange}
            />
          </PropertyRow>
        )}
        {manualInvalid && (
          <InlineMessage severity="info">
            {t('deviation.rangeTooSmall', { min: format.length(minimumRange(tolerance)) })}
          </InlineMessage>
        )}
        <PropertyRow label={t('deviation.scheme')} htmlFor="deviation-scheme">
          <Select
            id="deviation-scheme"
            value={deviation.scheme}
            options={schemes}
            onChange={setDeviationScheme}
          />
        </PropertyRow>
      </PanelSection>
      <DeviationResultSection
        computing={preview.status === 'computing'}
        summary={upToDate ? summary : null}
        snapshot={snapshot}
      />
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
    </ToolPanel>
  );
}
