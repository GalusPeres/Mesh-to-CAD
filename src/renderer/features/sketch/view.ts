import { PenTool } from 'lucide-react';

import { openEnds } from '../../tools/section-sketch/draftGeometry';
import type { FeatureView } from '../types';
import { SketchProperties } from './SketchProperties';

export const featureView: FeatureView<'sketch'> = {
  type: 'sketch',
  icon: PenTool,
  editTool: 'section-sketch',
  summary: (params, _format, t) =>
    t('features:sketch.summary', {
      count: params.entities.length,
      profile: t(
        openEnds(params).length ? 'features:sketch.profileOpen' : 'features:sketch.profileClosed',
      ),
    }),
  Properties: SketchProperties,
};
