import type { TFunction } from 'i18next';

import type { ReferenceDefinition } from '@shared/protocol/generated/feature-reference';

import type { Formatter } from '../../i18n/format';
import { documentStore } from '../../state/documentStore';
import { PlaneIcon } from '../../ui/icons/customIcons';
import { featureNames } from '../registry';
import type { FeatureView } from '../types';
import { ReferenceProperties } from './ReferenceProperties';

/** Display name of an input: an origin plane or axis, or a feature's name. */
function inputName(input: string, t: TFunction): string {
  const snapshot = documentStore.getState().snapshot;
  const names = snapshot ? featureNames(snapshot.document.features, t) : new Map<string, string>();
  return names.get(input) ?? t(`tools:referenceGeometry.origin.${input}`);
}

function summary(definition: ReferenceDefinition, format: Formatter, t: TFunction): string {
  switch (definition.type) {
    case 'offsetPlane':
      return t('features:reference.summary.offsetPlane', {
        plane: inputName(definition.plane, t),
        distance: format.length(definition.distance, { signed: true }),
      });
    case 'planeThroughAxis':
      return t('features:reference.summary.planeThroughAxis', {
        axis: inputName(definition.axis, t),
        angle: format.angle(definition.angleDeg),
      });
    case 'midPlane':
    case 'axisFromPlanes':
      return t(`features:reference.summary.${definition.type}`, {
        a: inputName(definition.a, t),
        b: inputName(definition.b, t),
      });
  }
}

export const featureView: FeatureView<'reference'> = {
  type: 'reference',
  icon: PlaneIcon,
  editTool: 'reference-geometry',
  baseName: (params, t) =>
    t(`features:reference.kinds.${params.definition.type === 'axisFromPlanes' ? 'axis' : 'plane'}`),
  summary: (params, format, t) => summary(params.definition, format, t),
  Properties: ReferenceProperties,
};
