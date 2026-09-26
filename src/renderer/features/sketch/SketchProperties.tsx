import { RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useDocument } from '../../state/documentStore';
import { useTools } from '../../state/toolStore';
import { openTool } from '../../tools/framework/toolActions';
import { Button } from '../../ui/Button/Button';

/** Refit offered when the sketch no longer matches the scan or its profile is open. */
export function SketchProperties({ featureId }: { featureId: string }) {
  const { t } = useTranslation('features');
  const status = useDocument((state) => state.snapshot?.status.features[featureId]);
  const toolOpen = useTools((state) => state.activeToolId !== null);
  const needsRefit = status?.issues.some(
    (issue) => issue.code === 'sketch.deviatesFromScan' || issue.code === 'sketch.sectionEmpty',
  );
  if (!needsRefit) return null;
  return (
    <Button
      disabled={toolOpen}
      data-testid="sketch-refit"
      onClick={() => void openTool('section-sketch', { refit: true }, featureId)}
    >
      <RefreshCw size={16} aria-hidden /> {t('sketch.refit')}
    </Button>
  );
}
