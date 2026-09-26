import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { LengthUnit } from '@shared/protocol/generated/document-model';
import { MAX_WORKING_FACES } from '@shared/protocol/generated/limits';
import type { ImportReport } from '@shared/protocol/generated/mesh';

import { useFormatter } from '../../i18n/useFormatter';
import { describeError } from '../../kernel/describeError';
import { kernel } from '../../kernel/kernel';
import { markUntitled } from '../../project/projectStore';
import { setStage } from '../../state/toolStore';
import { Checkbox } from '../../ui/Checkbox/Checkbox';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { NumberField } from '../../ui/NumberField/NumberField';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyRow, PropertyValue } from '../../ui/PropertyRow/PropertyRow';
import { Select } from '../../ui/Select/Select';
import { ToolPanel } from '../framework/ToolPanel';
import { useCommit } from '../framework/hooks';
import type { ToolPanelProps } from '../framework/types';
import styles from './ImportPanel.module.css';
import {
  MIN_REDUCE_TARGET,
  UNITS,
  defaultReduceTarget,
  isValidReduceTarget,
  noiseFor,
  sizeInFileUnits,
  sizeInMillimetres,
  toleranceFor,
} from './importUnits';

/**
 * Confirms how a loaded file becomes the scan of a new project: its unit (the
 * file does not store one) and, for very large scans, the reduction.
 */
export function ImportPanel({ activation, close }: ToolPanelProps) {
  const report = activation as ImportReport;
  const { t } = useTranslation(['tools', 'common']);
  const format = useFormatter();
  const [unit, setUnit] = useState<LengthUnit>(report.suggestedUnit);
  const [reduce, setReduce] = useState(report.reductionRequired);
  const [target, setTarget] = useState(() => defaultReduceTarget(report.faceCount));

  const targetValid = isValidReduceTarget(target, report.faceCount);
  const canCommit = !reduce || targetValid;

  const commitImport = useCallback(async () => {
    const reduceTo = reduce ? target : null;
    const params = { pendingId: report.pendingId, unit, reduceTo };
    await kernel().call('mesh.commitImport', params).result;
    markUntitled();
    setStage('prepare');
    close();
  }, [report.pendingId, unit, reduce, target, close]);
  const commit = useCommit(commitImport);

  // While the import is committed, cancelling goes through the status bar (it stops the job).
  const cancel = useCallback(() => {
    if (commit.busy) return;
    kernel()
      .call('mesh.discardImport', { pendingId: report.pendingId })
      .result.catch(() => undefined);
    close();
  }, [report.pendingId, close, commit.busy]);

  const size = sizeInMillimetres(report, unit);
  const sizeText = `${size.map((value) => format.number(value, 3)).join(' × ')} mm`;
  const fileSize = sizeInFileUnits(report)
    .map((value) => format.number(value, 3))
    .join(' × ');
  const noise = noiseFor(report, unit);

  return (
    <ToolPanel
      toolId="import-mesh"
      canCommit={canCommit}
      busy={commit.busy}
      onCommit={() => void commit.commit()}
      onCancel={cancel}
    >
      <PanelSection title={t('common:sections.input')}>
        <PropertyValue label={t('importMesh.file')} value={report.fileName} />
        <PropertyValue label={t('importMesh.triangles')} value={format.count(report.faceCount)} />
        {(report.counts.nonFiniteFaces ?? 0) > 0 && (
          <InlineMessage severity="warning">
            {t('importMesh.nonFiniteFaces', { count: report.counts.nonFiniteFaces })}
          </InlineMessage>
        )}
      </PanelSection>
      <PanelSection title={t('common:sections.parameters')}>
        <PropertyRow label={t('importMesh.unit')} htmlFor="import-unit">
          <Select<LengthUnit>
            id="import-unit"
            testId="import-unit"
            value={unit}
            options={UNITS.map((value) => ({ value, label: t(`common:units.${value}`) }))}
            onChange={setUnit}
          />
        </PropertyRow>
        <PropertyValue label={t('importMesh.size')} value={sizeText} />
        {report.suggestedUnit === 'm' && (
          <InlineMessage severity="info">
            {t('importMesh.smallScan', { size: fileSize })}
          </InlineMessage>
        )}
      </PanelSection>
      <PanelSection title={t('common:sections.options')}>
        <Checkbox
          checked={reduce}
          disabled={report.reductionRequired}
          label={t('importMesh.reduce')}
          testId="import-reduce"
          onChange={setReduce}
        />
        {reduce && (
          <PropertyRow label={t('importMesh.reduceTo')} htmlFor="import-reduce-target">
            <NumberField
              id="import-reduce-target"
              kind="count"
              value={target}
              min={MIN_REDUCE_TARGET}
              step={100_000}
              unit={t('importMesh.trianglesUnit')}
              onCommit={(value) => setTarget(Math.round(value))}
            />
          </PropertyRow>
        )}
        {reduce && !targetValid && (
          <InlineMessage severity="warning">
            {t('importMesh.invalidTarget', {
              min: MIN_REDUCE_TARGET,
              max: Math.min(report.faceCount - 1, MAX_WORKING_FACES),
            })}
          </InlineMessage>
        )}
        {report.reductionRequired && (
          <InlineMessage severity="info">
            {t('importMesh.reductionRequired', { faces: report.faceCount })}
          </InlineMessage>
        )}
      </PanelSection>
      <PanelSection title={t('common:sections.result')}>
        <PropertyValue
          label={t('importMesh.noise')}
          value={noise === null ? t('importMesh.noNoise') : format.length(noise)}
        />
        <PropertyValue
          label={t('importMesh.tolerance')}
          value={`±${format.length(toleranceFor(report, unit))}`}
        />
        <p className={styles.hint}>{t('importMesh.toleranceHint')}</p>
      </PanelSection>
      {commit.error && (
        <InlineMessage severity="error" details={commit.error.details}>
          {describeError(commit.error, t)}
        </InlineMessage>
      )}
    </ToolPanel>
  );
}
