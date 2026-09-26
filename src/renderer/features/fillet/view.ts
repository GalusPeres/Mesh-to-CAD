import { FilletIcon } from '../../ui/icons/customIcons';
import type { FeatureView } from '../types';

export const featureView: FeatureView<'fillet'> = {
  type: 'fillet',
  icon: FilletIcon,
  editTool: 'fillet',
  baseName: (params, t) => t(`features:fillet.modes.${params.mode}`),
  summary: (params, format, t) =>
    t(`features:fillet.summary.${params.mode}`, {
      size: format.length(params.size),
      count: params.edges.length,
    }),
};
