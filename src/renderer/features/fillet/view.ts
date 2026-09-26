import { FilletIcon } from '../../ui/icons/customIcons';
import type { FeatureView } from '../types';

export const featureView: FeatureView<'fillet'> = {
  type: 'fillet',
  icon: FilletIcon,
  editTool: 'fillet',
};
