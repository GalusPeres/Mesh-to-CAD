import {
  Axis3d,
  Box,
  Boxes,
  CircleDashed,
  Cone,
  Crosshair,
  Cylinder,
  FileBox,
  History,
  type LucideIcon,
  Move3d,
  Shapes,
  Square,
  Torus,
  Waves,
  Wrench,
} from 'lucide-react';

import { featureView } from '../features/registry';
import { PlaneIcon, SphereIcon } from '../ui/icons/customIcons';
import type { ProjectNodeIcon } from './treeModel';

const FIXED_ICONS: Record<string, LucideIcon> = {
  scan: FileBox,
  operation: Wrench,
  regions: Shapes,
  bodies: Boxes,
  body: Box,
  origin: Crosshair,
  plane: Square,
  axes: Axis3d,
  history: History,
  alignment: Move3d,
  'region:plane': PlaneIcon,
  'region:cylinder': Cylinder,
  'region:cone': Cone,
  'region:sphere': SphereIcon,
  'region:torus': Torus,
  'region:freeform': Waves,
  'region:unknown': CircleDashed,
};

/** Row icon: a fixed icon per group and region type, the feature view's icon for features. */
export function treeIcon(icon: ProjectNodeIcon | undefined): LucideIcon | undefined {
  if (!icon) return undefined;
  if (icon.startsWith('feature:')) return featureView(icon.slice('feature:'.length))?.icon;
  return FIXED_ICONS[icon];
}
