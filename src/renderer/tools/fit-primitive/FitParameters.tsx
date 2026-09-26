import { useTranslation } from 'react-i18next';

import type { FitRelation } from '@shared/protocol/generated/feature-fit';
import type { FitAlternative } from '@shared/protocol/generated/fitting-pipeline';
import type { Primitive, PrimitiveKind } from '@shared/protocol/generated/fitting-primitives';

import { featureNames } from '../../features/registry';
import { inputFeatures } from '../../features/reference/geometry';
import { useFormatter } from '../../i18n/useFormatter';
import { useDocument } from '../../state/documentStore';
import { PropertyRow } from '../../ui/PropertyRow/PropertyRow';
import { SegmentedControl } from '../../ui/SegmentedControl/SegmentedControl';
import { Select } from '../../ui/Select/Select';
import {
  type FitDraft,
  type KindChoice,
  VALUES_BY_KIND,
  type ValueName,
  type Vec3,
  fixValue,
  hasDirection,
  hasPoint,
  isFixed,
  kindOptions,
  primitiveValue,
  primitiveVector,
  releaseValue,
  withKind,
  withRelation,
} from './fitDraft';
import { FitValueField, FitVectorField } from './FitValueField';

type RelationType = 'free' | FitRelation['type'];

export interface FitParametersProps {
  draft: FitDraft;
  onChange: (draft: FitDraft) => void;
  /** The kind shown: the draft's kind, or the automatic choice of the last preview. */
  shown: PrimitiveKind;
  primitive: Primitive | null;
  alternatives: readonly FitAlternative[];
  editTarget: string | null;
}

/** Type, fitted values (Berechnet / Fest) and the direction relation of the fit tool. */
export function FitParameters(props: FitParametersProps) {
  const { draft, onChange, shown, primitive } = props;
  const { t } = useTranslation(['tools', 'features']);
  const format = useFormatter();
  const snapshot = useDocument((state) => state.snapshot);
  const fitted = primitive?.type === shown ? primitive : null;

  const kindLabel = (kind: PrimitiveKind) => t(`features:fit.kinds.${kind}`);
  const options = kindOptions(props.alternatives).map((option) => {
    if (option.value === 'auto') {
      const label = t('fitPrimitive.auto');
      return {
        value: option.value,
        label: primitive ? `${label} (${kindLabel(primitive.type)})` : label,
      };
    }
    const rms =
      option.rms === null
        ? ''
        : ` · ${t('fitPrimitive.rmsShort', { value: format.length(option.rms) })}`;
    return { value: option.value, label: `${kindLabel(option.value)}${rms}` };
  });

  const value = (name: ValueName): number | null => {
    const fixed = draft.fixed[name];
    if (typeof fixed === 'number') return fixed;
    return fitted ? primitiveValue(fitted, name) : null;
  };
  const vector = (name: 'direction' | 'point'): Vec3 | null => {
    const fixed = draft.fixed[name];
    if (fixed) return fixed;
    return fitted ? primitiveVector(fitted, name) : null;
  };

  const relationType: RelationType = draft.relation?.type ?? 'free';
  const targets = snapshot
    ? [
        ...inputFeatures(
          snapshot.document.features,
          snapshot.status.features,
          'axis',
          props.editTarget,
        ),
        ...inputFeatures(
          snapshot.document.features,
          snapshot.status.features,
          'plane',
          props.editTarget,
        ),
      ]
    : [];
  const names = snapshot ? featureNames(snapshot.document.features, t) : new Map<string, string>();
  const targetOptions = [
    ...(['X', 'Y', 'Z'] as const).map((axis) => ({
      value: axis,
      label: t('fitPrimitive.axisName', { axis }),
    })),
    ...targets.map((feature) => ({
      value: feature.id,
      label: names.get(feature.id) ?? feature.id,
    })),
  ];
  const setRelation = (type: RelationType, to: string) =>
    onChange(withRelation(draft, shown, type === 'free' ? null : { type, to }));

  const kindRow = (
    <PropertyRow label={t('fitPrimitive.kind')} htmlFor="fit-kind">
      <Select<KindChoice>
        id="fit-kind"
        testId="fit-kind"
        value={draft.kind}
        options={options}
        onChange={(kind) => onChange(withKind(draft, kind))}
      />
    </PropertyRow>
  );
  // An automatic fit has no values to show until the first result names its type.
  if (draft.kind === 'auto' && !primitive) return kindRow;

  return (
    <>
      {kindRow}
      {VALUES_BY_KIND[shown].map((name) => (
        <FitValueField
          key={`${shown}-${name}`}
          label={t(`fitPrimitive.values.${name}`)}
          value={value(name)}
          fixed={isFixed(draft, name)}
          kind={name === 'halfAngleDeg' ? 'angle' : 'length'}
          min={name === 'offset' ? undefined : 0}
          testId={`fit-value-${name}`}
          onFix={(next) => onChange(fixValue(draft, shown, name, next))}
          onRelease={() => onChange(releaseValue(draft, name))}
        />
      ))}
      {hasDirection(shown) && (
        <>
          <FitVectorField
            label={t(shown === 'plane' ? 'fitPrimitive.values.normal' : 'fitPrimitive.values.axis')}
            kind="direction"
            value={vector('direction')}
            fixed={isFixed(draft, 'direction')}
            onFix={(next) => onChange(fixValue(draft, shown, 'direction', next))}
            onRelease={() => onChange(releaseValue(draft, 'direction'))}
          />
          <PropertyRow label={t('fitPrimitive.relation')}>
            <SegmentedControl<RelationType>
              ariaLabel={t('fitPrimitive.relation')}
              value={relationType}
              segments={(['free', 'parallel', 'perpendicular'] as const).map((type) => ({
                value: type,
                label: t(`fitPrimitive.relations.${type}`),
              }))}
              onChange={(type) => setRelation(type, draft.relation?.to ?? 'Z')}
            />
          </PropertyRow>
          {draft.relation && (
            <PropertyRow label={t('fitPrimitive.relationTarget')} htmlFor="fit-relation-target">
              <Select<string>
                id="fit-relation-target"
                value={draft.relation.to}
                options={targetOptions}
                onChange={(to) => setRelation(relationType, to)}
              />
            </PropertyRow>
          )}
        </>
      )}
      {hasPoint(shown) && (
        <FitVectorField
          label={t(`fitPrimitive.values.point.${shown}`)}
          kind="point"
          value={vector('point')}
          fixed={isFixed(draft, 'point')}
          onFix={(next) => onChange(fixValue(draft, shown, 'point', next))}
          onRelease={() => onChange(releaseValue(draft, 'point'))}
        />
      )}
    </>
  );
}
