import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { LengthUnit } from '@shared/protocol/generated/document-model';
import type { ImportReport } from '@shared/protocol/generated/mesh';

import { useFormatter } from '../../i18n/useFormatter';
import { describeError } from '../../kernel/describeError';
import { kernel } from '../../kernel/kernel';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyRow, PropertyValue } from '../../ui/PropertyRow/PropertyRow';
import { Select } from '../../ui/Select/Select';
import { ToolPanel } from '../framework/ToolPanel';
import { useCommit } from '../framework/hooks';
import type { ToolPanelProps } from '../framework/types';

const UNIT_SCALE: Record<LengthUnit, number> = { mm: 1, cm: 10, m: 1000, in: 25.4 };
const UNITS: readonly LengthUnit[] = ['mm', 'cm', 'm', 'in'];

/** Confirms the unit of a loaded file before it becomes the scan. */
export function ImportPanel({ activation, close }: ToolPanelProps) {
  const report = activation as ImportReport;
  const { t } = useTranslation(['tools', 'common']);
  const format = useFormatter();
  const [unit, setUnit] = useState<LengthUnit>(report.suggestedUnit);

  const commitImport = useCallback(async () => {
    await kernel().call('mesh.commitImport', { pendingId: report.pendingId, unit }).result;
    close();
  }, [report.pendingId, unit, close]);
  const commit = useCommit(commitImport);

  const cancel = useCallback(() => {
    kernel()
      .call('mesh.discardImport', { pendingId: report.pendingId })
      .result.catch(() => undefined);
    close();
  }, [report.pendingId, close]);

  const scale = UNIT_SCALE[unit];
  const size = report.boundsMax.map((max, axis) => (max - (report.boundsMin[axis] ?? 0)) * scale);
  const sizeText = size.map((value) => format.number(value, 3)).join(' × ') + ' mm';

  return (
    <ToolPanel
      toolId="import-mesh"
      canCommit={!report.requiresReduction}
      busy={commit.busy}
      onCommit={() => void commit.commit()}
      onCancel={cancel}
    >
      <PanelSection title={t('common:sections.input')}>
        <PropertyValue label={t('importMesh.file')} value={report.fileName} />
        <PropertyValue label={t('importMesh.triangles')} value={format.count(report.faceCount)} />
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
        {report.suggestedUnit !== 'mm' && (
          <InlineMessage severity="info">{t('importMesh.unitHint')}</InlineMessage>
        )}
        {report.requiresReduction && (
          <InlineMessage severity="warning">{t('importMesh.reductionRequired')}</InlineMessage>
        )}
      </PanelSection>
      {commit.error && (
        <InlineMessage severity="error" details={commit.error.details}>
          {describeError(commit.error, t)}
        </InlineMessage>
      )}
    </ToolPanel>
  );
}
