import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { StepSchema } from '@shared/protocol/generated/export-api';

import { useFormatter } from '../../i18n/useFormatter';
import { ExportBodyList, exportableSelection } from '../../inspection/export/ExportBodyList';
import { ExportResultSection } from '../../inspection/export/ExportResultSection';
import {
  type ExportOutcome,
  productNames,
  runExport,
  safeFileName,
} from '../../inspection/export/exportFlow';
import { usePreflight } from '../../inspection/export/usePreflight';
import { bodyNames, projectName } from '../../inspection/names';
import { documentStore, useDocument } from '../../state/documentStore';
import { showMessage } from '../../state/messageStore';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyRow, PropertyValue } from '../../ui/PropertyRow/PropertyRow';
import { Select } from '../../ui/Select/Select';
import { ToolPanel } from '../framework/ToolPanel';
import { useCommit } from '../framework/hooks';
import type { ToolPanelProps } from '../framework/types';

const TOOL_ID = 'export-step';

/**
 * STEP export of the chosen bodies. OK asks for the file; the kernel writes it, reads
 * it back and compares it with the bodies before it replaces the target.
 */
export function ExportStepPanel({ close }: ToolPanelProps) {
  const { t } = useTranslation(['tools', 'inspection', 'common']);
  const format = useFormatter();
  const snapshot = useDocument((state) => state.snapshot);
  const preflight = usePreflight();
  const [selected, setSelected] = useState<string[]>(
    () => snapshot?.status.bodies.map((body) => body.id) ?? [],
  );
  const [schema, setSchema] = useState<StepSchema>('AP214');
  const [done, setDone] = useState<{ outcome: ExportOutcome; message: string } | null>(null);
  const bodies = exportableSelection(preflight, selected);
  const project = projectName(snapshot, t('common:untitled'));

  const exportStep = useCallback(async () => {
    const names = productNames(
      project,
      bodies,
      bodyNames(documentStore.getState().snapshot, t),
      (name, body) => t('inspection:export.productWithBody', { project: name, body }),
    );
    const outcome = await runExport(
      'exportStep',
      { bodies, names, schema },
      {
        title: t('exportStep.dialogTitle'),
        filterName: t('exportStep.filterName'),
        defaultName: `${safeFileName(project)}.step`,
      },
    );
    if (!outcome) return;
    // Parenthetical details, not a sentence: "(2 Körper, 184 KB)" as in DESIGN.md 8.3.
    const details = [
      t('inspection:export.bodyCount', { count: outcome.result.bodies }),
      format.bytes(outcome.result.bytes),
    ].join(', ');
    const message = t('exportStep.saved', { file: outcome.result.fileName, details });
    setDone({ outcome, message });
    showMessage('success', message);
  }, [bodies, project, schema, format, t]);
  const commit = useCommit(exportStep);

  const schemas: { value: StepSchema; label: string }[] = [
    { value: 'AP214', label: t('exportStep.schemas.AP214') },
    { value: 'AP242', label: t('exportStep.schemas.AP242') },
  ];

  return (
    <ToolPanel
      toolId={TOOL_ID}
      canCommit={bodies.length > 0}
      busy={commit.busy}
      onCommit={() => void commit.commit()}
      onCancel={close}
    >
      <PanelSection title={t('common:sections.input')}>
        <ExportBodyList preflight={preflight} selected={selected} onChange={setSelected} />
        {preflight.status === 'ok' && bodies.length === 0 && (
          <InlineMessage severity="info">{t('inspection:export.noneSelected')}</InlineMessage>
        )}
      </PanelSection>
      <PanelSection title={t('common:sections.options')}>
        <PropertyRow label={t('exportStep.schema')} htmlFor="export-step-schema">
          <Select
            id="export-step-schema"
            testId="export-step-schema"
            value={schema}
            options={schemas}
            onChange={setSchema}
          />
        </PropertyRow>
        <PropertyValue label={t('inspection:export.productName')} value={project} />
      </PanelSection>
      <ExportResultSection
        busy={commit.busy}
        message={done?.message ?? null}
        revealToken={done?.outcome.revealToken ?? null}
        error={commit.error}
      />
    </ToolPanel>
  );
}
