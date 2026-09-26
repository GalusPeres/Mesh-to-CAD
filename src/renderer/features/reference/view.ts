import { PlaneIcon } from '../../ui/icons/customIcons';
import type { FeatureView } from '../types';

export const featureView: FeatureView<'reference'> = {
  type: 'reference',
  icon: PlaneIcon,
  editTool: 'reference-geometry',
  baseName: (params, t) => t(`features:reference.kinds.${params.definition.type}`),
};
