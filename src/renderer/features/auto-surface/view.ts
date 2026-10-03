import { Grid3x3 } from 'lucide-react';

import { statusOfParams } from '../freeform-patch/statusOf';
import type { FeatureView } from '../types';
import { surfaceStats } from '../../tools/auto-surface/model';
import { AutoSurfaceProperties } from './AutoSurfaceProperties';

export const featureView: FeatureView<'autoSurface'> = {
  type: 'autoSurface',
  icon: Grid3x3,
  editTool: 'auto-surface',
  summary: (params, format, t) => {
    const detail = t(`features:autoSurface.details.${params.detail}`);
    const stats = surfaceStats(statusOfParams(params));
    if (!stats) return detail;
    return t('features:autoSurface.summary', {
      detail,
      patches: format.count(stats.patches),
    });
  },
  Properties: AutoSurfaceProperties,
};
