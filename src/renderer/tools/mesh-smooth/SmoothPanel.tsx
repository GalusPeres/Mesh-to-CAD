import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { SET_SMOOTHING_PARAMS_RANGES } from '@shared/protocol/generated/mesh';

import { describeError } from '../../kernel/describeError';
import { kernel } from '../../kernel/kernel';
import { useDocument } from '../../state/documentStore';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { NumberField } from '../../ui/NumberField/NumberField';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { PropertyRow, PropertyValue } from '../../ui/PropertyRow/PropertyRow';
import { ToolPanel } from '../framework/ToolPanel';
import { useCommit } from '../framework/hooks';
import type { ToolPanelProps } from '../framework/types';
import styles from '../mesh-repair/scanEdit/ScanEdit.module.css';
import { DEFAULT_SMOOTHING_ITERATIONS } from '../mesh-repair/scanEdit/scanEditModel';
import { ScanInput } from '../mesh-repair/scanEdit/ScanEditSections';

const { min, max } = SET_SMOOTHING_PARAMS_RANGES.iterations;

/** Display smoothing of the scan; fits and deviations always use the measured points. */
export function SmoothPanel({ close }: ToolPanelProps) {
  const { t } = useTranslation('tools');
  const current = useDocument((state) => state.snapshot?.document.scan?.displaySmoothing ?? 0);
  const [iterations, setIterations] = useState(
    current === 0 ? DEFAULT_SMOOTHING_ITERATIONS : current,
  );

  const apply = useCallback(async () => {
    await kernel().call('mesh.setSmoothing', { iterations }).result;
    close();
  }, [iterations, close]);
  const commit = useCommit(apply);

  return (
    <ToolPanel
      toolId="mesh-smooth"
      canCommit={iterations !== current}
      busy={commit.busy}
      onCommit={() => void commit.commit()}
      onCancel={close}
    >
      <ScanInput />
      <PanelSection title={t('common:sections.parameters')}>
        <PropertyRow label={t('meshSmooth.iterations')} htmlFor="smooth-iterations">
          <NumberField
            id="smooth-iterations"
            kind="count"
            min={min}
            max={max}
            value={iterations}
            onCommit={(value) => setIterations(Math.round(value))}
          />
        </PropertyRow>
        <p className={styles.hint}>{t('meshSmooth.offHint')}</p>
      </PanelSection>
      <PanelSection title={t('common:sections.result')}>
        <PropertyValue
          label={t('meshSmooth.current')}
          value={current === 0 ? t('meshSmooth.off') : t('meshSmooth.passes', { count: current })}
        />
        <p className={styles.hint}>{t('meshSmooth.displayOnly')}</p>
        {commit.error && (
          <InlineMessage severity="error" details={commit.error.details}>
            {describeError(commit.error, t)}
          </InlineMessage>
        )}
      </PanelSection>
    </ToolPanel>
  );
}
