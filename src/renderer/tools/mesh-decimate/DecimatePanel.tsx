import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { MAX_WORKING_FACES } from '@shared/protocol/generated/limits';

import { useFormatter } from '../../i18n/useFormatter';
import { useDocument } from '../../state/documentStore';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { NumberField } from '../../ui/NumberField/NumberField';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyRow } from '../../ui/PropertyRow/PropertyRow';
import { ToolPanel } from '../framework/ToolPanel';
import type { ToolPanelProps } from '../framework/types';
import styles from '../mesh-repair/scanEdit/ScanEdit.module.css';
import {
  MIN_DECIMATE_TARGET,
  defaultDecimateTarget,
  isValidDecimateTarget,
} from '../mesh-repair/scanEdit/scanEditModel';
import { EditResult, ScanInput } from '../mesh-repair/scanEdit/ScanEditSections';
import { useScanEdit } from '../mesh-repair/scanEdit/useScanEdit';

/**
 * Reduces the triangle count. The reduction itself runs alone in the computing
 * process, with progress and cancel in the status bar.
 */
export function DecimatePanel({ close }: ToolPanelProps) {
  const { t } = useTranslation('tools');
  const format = useFormatter();
  const faceCount = useDocument((state) => state.snapshot?.document.scan?.faceCount ?? 0);
  const [target, setTarget] = useState(() => defaultDecimateTarget(faceCount));
  const valid = isValidDecimateTarget(target, faceCount);
  const params = useMemo(() => (valid ? { targetFaces: target } : null), [valid, target]);
  const edit = useScanEdit('mesh.decimate', params, 'mesh-decimate', close);
  const counts = edit.result?.counts;

  return (
    <ToolPanel
      toolId="mesh-decimate"
      canCommit={edit.canCommit && valid}
      busy={edit.commit.busy}
      onCommit={() => void edit.commit.commit()}
      onCancel={close}
    >
      <ScanInput />
      <PanelSection title={t('common:sections.parameters')}>
        <PropertyRow label={t('meshDecimate.target')} htmlFor="decimate-target">
          <NumberField
            id="decimate-target"
            kind="count"
            min={MIN_DECIMATE_TARGET}
            max={MAX_WORKING_FACES}
            step={10_000}
            unit={t('meshDecimate.trianglesUnit')}
            value={target}
            onCommit={(value) => setTarget(Math.round(value))}
          />
        </PropertyRow>
        {!valid && (
          <InlineMessage severity="warning">
            {t('meshDecimate.invalidTarget', {
              min: MIN_DECIMATE_TARGET,
              max: Math.max(MIN_DECIMATE_TARGET, Math.min(faceCount - 1, MAX_WORKING_FACES)),
            })}
          </InlineMessage>
        )}
      </PanelSection>
      <EditResult
        edit={edit}
        nothingToDo={t('meshDecimate.nothingToDo')}
        rows={
          counts && valid
            ? [
                { label: t('meshDecimate.before'), value: format.count(counts.facesBefore ?? 0) },
                { label: t('meshDecimate.after'), value: format.count(counts.facesAfter ?? 0) },
              ]
            : []
        }
      >
        <p className={styles.hint}>{t('meshDecimate.hint')}</p>
      </EditResult>
    </ToolPanel>
  );
}
