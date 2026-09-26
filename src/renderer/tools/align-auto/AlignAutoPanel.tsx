import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { AlignmentAdjust } from '@shared/protocol/generated/document-model';

import { useDocument } from '../../state/documentStore';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { ToolPanel } from '../framework/ToolPanel';
import { useCommit, usePreview } from '../framework/hooks';
import type { ToolPanelProps } from '../framework/types';
import { type AdjustAction, applyAdjust } from './adjust';
import { commitAlignment, initialAdjust } from './alignmentActions';
import { AdjustControls, AlignmentResult } from './AlignmentSections';
import { useFrameOverlay } from './useFrameOverlay';

/**
 * Automatic alignment: largest plane on XY, the largest plane across it on XZ,
 * origin at the corner of the scan. The panel shows the remaining tilt of the
 * largest plane and draws the new frame over the scan until OK.
 */
export function AlignAutoPanel({ editTarget, close }: ToolPanelProps) {
  const { t } = useTranslation();
  const hasScan = useDocument((state) => !!state.snapshot?.document.scan);
  const revision = useDocument((state) => state.snapshot?.revision ?? null);
  const [adjust, setAdjust] = useState<AlignmentAdjust>(() => initialAdjust('auto', editTarget));

  const params = useMemo(
    () => (hasScan && revision !== null ? { method: 'auto' as const, adjust } : null),
    [hasScan, revision, adjust],
  );
  const preview = usePreview('alignment.preview', params, 'align-auto');
  const matrix = preview.status === 'ok' ? preview.result.matrix : null;
  useFrameOverlay(matrix);

  const apply = useCallback(async () => {
    await commitAlignment('auto', null, adjust);
    close();
  }, [adjust, close]);
  const commit = useCommit(apply);

  return (
    <ToolPanel
      toolId="align-auto"
      editingName={editTarget ? t('tools:alignAuto.alignment') : undefined}
      canCommit={preview.status === 'ok'}
      busy={commit.busy}
      onCommit={() => void commit.commit()}
      onCancel={close}
    >
      <PanelSection title={t('common:sections.parameters')}>
        <AdjustControls
          adjust={adjust}
          onAdjust={(action: AdjustAction) => setAdjust((value) => applyAdjust(value, action))}
        />
      </PanelSection>
      <AlignmentResult
        preview={preview}
        commitError={commit.error}
        idleText={t('tools:alignAuto.noScan')}
      />
    </ToolPanel>
  );
}
