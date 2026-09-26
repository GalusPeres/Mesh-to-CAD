import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { RepairStep } from '@shared/protocol/generated/mesh-repair';

import { useFormatter } from '../../i18n/useFormatter';
import { Checkbox } from '../../ui/Checkbox/Checkbox';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { ToolPanel } from '../framework/ToolPanel';
import type { ToolPanelProps } from '../framework/types';
import styles from './scanEdit/ScanEdit.module.css';
import { EditResult, ScanInput } from './scanEdit/ScanEditSections';
import { REPAIR_STEPS, toggleStep } from './repairSteps';
import { useScanEdit } from './scanEdit/useScanEdit';

/** Repair steps as checkboxes, each with the count its dry run found. */
export function RepairPanel({ close }: ToolPanelProps) {
  const { t } = useTranslation('tools');
  const format = useFormatter();
  const [selected, setSelected] = useState<readonly RepairStep[]>(
    REPAIR_STEPS.map(({ step }) => step),
  );
  const params = useMemo(() => (selected.length > 0 ? { steps: [...selected] } : null), [selected]);
  const edit = useScanEdit('mesh.repair', params, 'mesh-repair', close);
  const { result } = edit;

  const toggle = (step: RepairStep, on: boolean) => setSelected(toggleStep(selected, step, on));
  const nonOrientable = result?.counts.nonOrientableFaces ?? 0;

  return (
    <ToolPanel
      toolId="mesh-repair"
      canCommit={edit.canCommit}
      busy={edit.commit.busy}
      onCommit={() => void edit.commit.commit()}
      onCancel={close}
    >
      <ScanInput />
      <PanelSection title={t('common:sections.parameters')}>
        {REPAIR_STEPS.map(({ step, count }) => {
          const value = result?.counts[count];
          return (
            <div key={step} className={styles.step}>
              <Checkbox
                checked={selected.includes(step)}
                label={t(`meshRepair.steps.${step}`)}
                testId={`repair-step-${step}`}
                onChange={(on) => toggle(step, on)}
              />
              <span className={styles.count} data-testid={`repair-count-${step}`}>
                {selected.includes(step) && value !== undefined ? format.count(value) : '–'}
              </span>
            </div>
          );
        })}
      </PanelSection>
      <EditResult
        edit={edit}
        nothingToDo={t('meshRepair.nothingToDo')}
        rows={
          result
            ? [{ label: t('meshRepair.shared.facesAfter'), value: format.count(result.faceCount) }]
            : []
        }
      >
        {nonOrientable > 0 && (
          <InlineMessage severity="warning">
            {t('meshRepair.nonOrientable', { count: nonOrientable })}
          </InlineMessage>
        )}
      </EditResult>
    </ToolPanel>
  );
}
