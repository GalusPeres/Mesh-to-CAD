import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useFormatter } from '../../i18n/useFormatter';
import { NumberField } from '../../ui/NumberField/NumberField';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyRow } from '../../ui/PropertyRow/PropertyRow';
import { ToolPanel } from '../framework/ToolPanel';
import type { ToolPanelProps } from '../framework/types';
import {
  DEFAULT_MIN_PART_FACES,
  DEFAULT_MIN_PART_PERCENT,
} from '../mesh-repair/scanEdit/scanEditModel';
import { EditResult, ScanInput } from '../mesh-repair/scanEdit/ScanEditSections';
import { useScanEdit } from '../mesh-repair/scanEdit/useScanEdit';

/**
 * Removes loose parts (turntable remains, debris). A part stays when it reaches
 * both limits; the largest part always stays.
 */
export function RemoveSmallPartsPanel({ close }: ToolPanelProps) {
  const { t } = useTranslation('tools');
  const format = useFormatter();
  const [percent, setPercent] = useState(DEFAULT_MIN_PART_PERCENT);
  const [minFaces, setMinFaces] = useState(DEFAULT_MIN_PART_FACES);
  const params = useMemo(() => ({ minRatio: percent / 100, minFaces }), [percent, minFaces]);
  const edit = useScanEdit('mesh.removeSmallParts', params, 'mesh-remove-small-parts', close);
  const counts = edit.result?.counts;

  return (
    <ToolPanel
      toolId="mesh-remove-small-parts"
      canCommit={edit.canCommit}
      busy={edit.commit.busy}
      onCommit={() => void edit.commit.commit()}
      onCancel={close}
    >
      <ScanInput />
      <PanelSection title={t('common:sections.parameters')}>
        <PropertyRow label={t('meshRemoveSmallParts.minShare')} htmlFor="small-parts-share">
          <NumberField
            id="small-parts-share"
            kind="plain"
            decimals={1}
            unit="%"
            min={0}
            max={100}
            step={0.5}
            value={percent}
            onCommit={setPercent}
          />
        </PropertyRow>
        <PropertyRow label={t('meshRemoveSmallParts.minFaces')} htmlFor="small-parts-faces">
          <NumberField
            id="small-parts-faces"
            kind="count"
            min={0}
            max={1_000_000}
            step={50}
            value={minFaces}
            onCommit={(value) => setMinFaces(Math.round(value))}
          />
        </PropertyRow>
      </PanelSection>
      <EditResult
        edit={edit}
        nothingToDo={t('meshRemoveSmallParts.nothingToDo')}
        rows={
          counts && edit.result
            ? [
                {
                  label: t('meshRemoveSmallParts.removedParts'),
                  value: format.count(counts.removedParts ?? 0),
                },
                {
                  label: t('meshRemoveSmallParts.removedFaces'),
                  value: format.count(counts.removedFaces ?? 0),
                },
                {
                  label: t('meshRepair.shared.facesAfter'),
                  value: format.count(edit.result.faceCount),
                },
              ]
            : []
        }
      />
    </ToolPanel>
  );
}
