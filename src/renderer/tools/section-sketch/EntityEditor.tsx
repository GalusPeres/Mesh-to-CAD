import { Lock } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { SketchEntity, SketchParams } from '@shared/protocol/generated/sketch-params';

import { IconButton } from '../../ui/IconButton/IconButton';
import { NumberField } from '../../ui/NumberField/NumberField';
import { PropertyRow } from '../../ui/PropertyRow/PropertyRow';
import { pointOf, xy } from './draftGeometry';
import { releaseDimension, releasePoint, setLineValue, setPoint, setRoundValue } from './edits';
import { lineAngle, lineLength } from './sketchMath';
import styles from './SketchPanel.module.css';

const K = 'sectionSketch';

interface FieldProps {
  id: string;
  label: string;
  value: number;
  kind?: 'length' | 'angle';
  /** Typed by the user and kept by refits; shows a button that releases it. */
  fixed: boolean;
  /** Follows from the fit (secondary colour) rather than from a typed value. */
  computed: boolean;
  onCommit: (value: number) => void;
  onRelease: () => void;
}

function Field({
  id,
  label,
  value,
  kind = 'length',
  fixed,
  computed,
  onCommit,
  onRelease,
}: FieldProps) {
  const { t } = useTranslation('tools');
  return (
    <PropertyRow label={label} htmlFor={id}>
      <div className={styles.field}>
        <NumberField id={id} value={value} kind={kind} computed={computed} onCommit={onCommit} />
        {fixed && (
          <IconButton
            icon={Lock}
            label={`${t(`${K}.fixedValue`)} · ${t(`${K}.release`)}`}
            onClick={onRelease}
          />
        )}
      </div>
    </PropertyRow>
  );
}

interface EntityEditorProps {
  sketch: SketchParams;
  entity: SketchEntity;
  onEdit: (next: SketchParams) => void;
}

/** Numeric editing of one entity; the kernel refits the sketch around the typed values. */
export function EntityEditor({ sketch, entity, onEdit }: EntityEditorProps) {
  const { t } = useTranslation('tools');
  const dimension = (kind: string) =>
    sketch.dimensions.some((d) => d.entity === entity.id && d.kind === kind);
  const field = (key: string) => `sketch-${entity.id}-${key}`;
  const fitted = entity.origin === 'fit';

  if (entity.type === 'line') {
    const start = pointOf(sketch, entity.start);
    const end = pointOf(sketch, entity.end);
    const point = (which: 'start' | 'end', axis: 0 | 1) => {
      const target = which === 'start' ? start : end;
      const key = `${which}${axis ? 'Y' : 'X'}`;
      return (
        <Field
          key={key}
          id={field(key)}
          label={t(`${K}.field.${key}`)}
          value={xy(target)[axis]}
          fixed={target.fixed}
          computed={!target.fixed}
          onCommit={(value) =>
            onEdit(setPoint(sketch, target.id, axis ? [target.x, value] : [value, target.y]))
          }
          onRelease={() => onEdit(releasePoint(sketch, target.id))}
        />
      );
    };
    return (
      <>
        {point('start', 0)}
        {point('start', 1)}
        {point('end', 0)}
        {point('end', 1)}
        <Field
          id={field('length')}
          label={t(`${K}.field.length`)}
          value={lineLength(xy(start), xy(end))}
          fixed={dimension('length')}
          computed={fitted && !dimension('length')}
          onCommit={(value) => onEdit(setLineValue(sketch, entity.id, 'length', value))}
          onRelease={() => onEdit(releaseDimension(sketch, entity.id, 'length'))}
        />
        <Field
          id={field('angle')}
          label={t(`${K}.field.angle`)}
          kind="angle"
          value={lineAngle(xy(start), xy(end))}
          fixed={dimension('angle')}
          computed={fitted && !dimension('angle')}
          onCommit={(value) => onEdit(setLineValue(sketch, entity.id, 'angle', value))}
          onRelease={() => onEdit(releaseDimension(sketch, entity.id, 'angle'))}
        />
      </>
    );
  }

  const rounds = [
    ['centerX', entity.center[0]],
    ['centerY', entity.center[1]],
    ['radius', entity.radius],
  ] as const;
  return (
    <>
      {rounds.map(([kind, value]) => (
        <Field
          key={kind}
          id={field(kind)}
          label={t(`${K}.field.${kind}`)}
          value={value}
          fixed={dimension(kind)}
          computed={fitted && !dimension(kind)}
          onCommit={(next) => onEdit(setRoundValue(sketch, entity.id, kind, next))}
          onRelease={() => onEdit(releaseDimension(sketch, entity.id, kind))}
        />
      ))}
    </>
  );
}
