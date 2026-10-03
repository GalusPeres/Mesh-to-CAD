import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { STL_PARAMS_RANGES } from '@shared/protocol/generated/export';

import { useFormatter } from '../../i18n/useFormatter';
import { ExportBodyList, exportableSelection } from '../../inspection/export/ExportBodyList';
import { ExportResultSection } from '../../inspection/export/ExportResultSection';
import { type ExportOutcome, runExport, safeFileName } from '../../inspection/export/exportFlow';
import { usePreflight } from '../../inspection/export/usePreflight';
import { projectName } from '../../inspection/names';
import { useDocument } from '../../state/documentStore';
import { showMessage } from '../../state/messageStore';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { NumberField } from '../../ui/NumberField/NumberField';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyRow } from '../../ui/PropertyRow/PropertyRow';
import { ToolPanel } from '../framework/ToolPanel';
import { useCommit } from '../framework/hooks';
import type { ToolPanelProps } from '../framework/types';
import styles from './ExportStlPanel.module.css';

const TOOL_ID = 'export-stl';
const DEFAULT_DEFLECTION_MM = 0.01;

/** STL export of the chosen bodies, tessellated with the given accuracy. */
export function ExportStlPanel({ close }: ToolPanelProps) {
  const { t } = useTranslation(['tools', 'inspection', 'common']);
  const format = useFormatter();
  const snapshot = useDocument((state) => state.snapshot);
  const preflight = usePreflight();
  const [selected, setSelected] = useState<string[]>(
    () => snapshot?.status.bodies.map((body) => body.id) ?? [],
  );
  const [deflection, setDeflection] = useState(DEFAULT_DEFLECTION_MM);
  const [done, setDone] = useState<{ outcome: ExportOutcome; message: string } | null>(null);
  const bodies = exportableSelection(preflight, selected);
  const project = projectName(snapshot, t('common:untitled'));

  const exportStl = useCallback(async () => {
    const outcome = await runExport(
      'exportStl',
      { bodies, deflection },
      {
        title: t('exportStl.dialogTitle'),
        filterName: t('exportStl.filterName'),
        defaultName: `${safeFileName(project)}.stl`,
      },
    );
    if (!outcome) return;
    const triangles = outcome.result.triangles ?? 0;
    // Parenthetical details, not a sentence: "(2 Körper, 184 KB)" as in DESIGN.md 8.3.
    const details = [
      t('inspection:export.bodyCount', { count: outcome.result.bodies }),
      t('inspection:export.triangleCount', {
        count: triangles,
        formatted: format.count(triangles),
      }),
      format.bytes(outcome.result.bytes),
    ].join(', ');
    const message = t('exportStl.saved', { file: outcome.result.fileName, details });
    setDone({ outcome, message });
    showMessage('success', message);
  }, [bodies, deflection, project, format, t]);
  const commit = useCommit(exportStl);

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
      <PanelSection title={t('common:sections.parameters')}>
        <PropertyRow label={t('exportStl.deflection')} htmlFor="export-stl-deflection">
          <NumberField
            id="export-stl-deflection"
            value={deflection}
            min={STL_PARAMS_RANGES.deflection.min}
            max={STL_PARAMS_RANGES.deflection.max}
            step={0.005}
            onCommit={setDeflection}
          />
        </PropertyRow>
        <p className={styles.hint}>{t('exportStl.deflectionHint')}</p>
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
