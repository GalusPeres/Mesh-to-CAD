import type { TFunction } from 'i18next';
import type { LucideIcon } from 'lucide-react';
import type { ComponentType } from 'react';

import type { FeatureTypeId, FeatureTypes } from '@shared/protocol/generated/index';

import type { Formatter } from '../i18n/format';

/**
 * How the renderer presents one feature type, discovered from
 * `features/<folder>/view.ts`. Strings live under `features:<type>`.
 */
export interface FeatureView<T extends FeatureTypeId = FeatureTypeId> {
  type: T;
  icon: LucideIcon;
  /** Tool that edits this feature type (double-click in the tree). */
  editTool?: string;
  /** Base of the default name, e.g. "Zylinder" for "Zylinder 2". Default: `features:<type>.name`. */
  baseName?(params: FeatureTypes[T]['params'], t: TFunction): string;
  /** One-line summary for the tree and the properties panel ("12,000 mm, Abziehen"). */
  summary?(params: FeatureTypes[T]['params'], format: Formatter, t: TFunction): string;
  /** Editable values shown in the properties panel when the feature is selected. */
  Properties?: ComponentType<{ featureId: string }>;
}
