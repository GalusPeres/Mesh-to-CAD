// Icons lucide does not have, drawn on its grid: 24 x 24, 2 px stroke,
// round caps and joins, no fill (docs/DESIGN.md 2.6).

import { createLucideIcon } from 'lucide-react';

export const PlaneIcon = createLucideIcon('m2c-plane', [
  ['path', { d: 'M7 5h15l-5 14H2Z', key: 'outline' }],
]);

export const SphereIcon = createLucideIcon('m2c-sphere', [
  ['circle', { cx: '12', cy: '12', r: '9', key: 'outline' }],
  ['ellipse', { cx: '12', cy: '12', rx: '9', ry: '3.5', key: 'equator' }],
]);

export const FilletIcon = createLucideIcon('m2c-fillet', [
  ['path', { d: 'M4 20v-8a8 8 0 0 1 8-8h8', key: 'corner' }],
  ['path', { d: 'M4 4h4M4 4v4', key: 'sharp' }],
]);
