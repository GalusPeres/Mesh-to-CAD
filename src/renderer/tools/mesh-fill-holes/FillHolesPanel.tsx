import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useFormatter } from '../../i18n/useFormatter';
import { NumberField } from '../../ui/NumberField/NumberField';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyRow } from '../../ui/PropertyRow/PropertyRow';
import { ToolPanel } from '../framework/ToolPanel';
import type { ToolPanelProps } from '../framework/types';
import styles from '../mesh-repair/scanEdit/ScanEdit.module.css';
import { DEFAULT_MAX_PERIMETER_MM } from '../mesh-repair/scanEdit/scanEditModel';
import { EditResult, ScanInput } from '../mesh-repair/scanEdit/ScanEditSections';
import { useScanEdit } from '../mesh-repair/scanEdit/useScanEdit';

/** Closes holes up to a perimeter; the new triangles never enter fits or statistics. */
export function FillHolesPanel({ close }: ToolPanelProps) {
  const { t } = useTranslation('tools');
  const format = useFormatter();
  const [maxPerimeter, setMaxPerimeter] = useState(DEFAULT_MAX_PERIMETER_MM);
  const params = useMemo(() => ({ maxPerimeter }), [maxPerimeter]);
  const edit = useScanEdit('mesh.fillHoles', params, 'mesh-fill-holes', close, 'filled');
  const counts = edit.result?.counts;

  return (
    <ToolPanel
      toolId="mesh-fill-holes"
      canCommit={edit.canCommit}
      busy={edit.commit.busy}
      onCommit={() => void edit.commit.commit()}
      onCancel={close}
    >
      <ScanInput />
      <PanelSection title={t('common:sections.parameters')}>
        <PropertyRow label={t('meshFillHoles.maxPerimeter')} htmlFor="fill-holes-perimeter">
          <NumberField
            id="fill-holes-perimeter"
            kind="length"
            min={0}
            max={100_000}
            step={5}
            value={maxPerimeter}
            onCommit={setMaxPerimeter}
          />
        </PropertyRow>
      </PanelSection>
      <EditResult
        edit={edit}
        nothingToDo={t('meshFillHoles.nothingToDo')}
        rows={
          counts
            ? [
                {
                  label: t('meshFillHoles.filledHoles'),
                  value: format.count(counts.filledHoles ?? 0),
                },
                { label: t('meshFillHoles.openHoles'), value: format.count(counts.openHoles ?? 0) },
                {
                  label: t('meshFillHoles.addedFaces'),
                  value: format.count(counts.addedFaces ?? 0),
                },
              ]
            : []
        }
      >
        <p className={styles.hint}>{t('meshFillHoles.syntheticHint')}</p>
      </EditResult>
    </ToolPanel>
  );
}
