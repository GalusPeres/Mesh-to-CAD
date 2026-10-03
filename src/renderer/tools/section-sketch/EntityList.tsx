import { Check, TriangleAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { EntityFitInfo } from '@shared/protocol/generated/sketch';
import type { SketchParams } from '@shared/protocol/generated/sketch-params';

import { useFormatter } from '../../i18n/useFormatter';
import { entitySize } from './describe';
import { groupOf, sketchGroups } from './sketchGroups';
import { shapeLabel, shapeSizeText } from './shapeSizes';
import styles from './SketchPanel.module.css';

const K = 'sectionSketch';

interface EntityListProps {
  sketch: SketchParams;
  labels: ReadonlyMap<string, string>;
  fits: readonly EntityFitInfo[];
  /** An entity id or a shape id. */
  selected: string | null;
  onSelect: (id: string | null) => void;
}

interface Row {
  id: string;
  name: string;
  size: string;
  /** Largest deviation of the row's entities (mm). */
  deviation: number | null;
  passed: boolean | null;
}

function worst(fits: (EntityFitInfo | undefined)[]): Pick<Row, 'deviation' | 'passed'> {
  const judged = fits.filter((fit) => fit?.maxDistance != null) as EntityFitInfo[];
  if (!judged.length) return { deviation: null, passed: null };
  return {
    deviation: Math.max(...judged.map((fit) => fit.maxDistance ?? 0)),
    passed: judged.every((fit) => fit.passed !== false),
  };
}

/** One row per shape (a button), free profile and single entity: name, size, deviation. */
export function EntityList({ sketch, labels, fits, selected, onSelect }: EntityListProps) {
  const { t } = useTranslation('tools');
  const format = useFormatter();
  if (sketch.entities.length === 0) return <p className={styles.hint}>{t(`${K}.noEntities`)}</p>;
  const verdicts = new Map(fits.map((fit) => [fit.entity, fit]));
  const groups = sketchGroups(sketch);
  const rows: Row[] = groups.map((group) => {
    const quality = worst(group.entities.map((id) => verdicts.get(id)));
    if (group.shape) {
      return {
        id: group.id,
        name: shapeLabel(group.shape, t),
        size: shapeSizeText(sketch, group.shape, format),
        ...quality,
      };
    }
    if (group.kind === 'profile') {
      return {
        id: group.id,
        name: t(`${K}.profileRow`, { number: group.id.slice(1) }),
        size: t(`${K}.entityCount`, { count: group.entities.length }),
        ...quality,
      };
    }
    const entity = sketch.entities.find((candidate) => candidate.id === group.id);
    return {
      id: group.id,
      name: `${labels.get(group.id) ?? group.id}${
        entity?.origin === 'drawn' ? ` · ${t(`${K}.drawn`)}` : ''
      }`,
      size: entity ? entitySize(sketch, entity, format) : '',
      ...quality,
    };
  });
  const owner = groupOf(groups, selected)?.id;
  return (
    <ul className={styles.list} aria-label={t(`${K}.entities`)}>
      {rows.map((row) => {
        const deviation =
          row.deviation !== null
            ? t(`${K}.deviation`, { value: format.length(row.deviation) })
            : undefined;
        const pressed = row.id === selected || row.id === owner;
        return (
          <li key={row.id}>
            <button
              type="button"
              className={styles.row}
              aria-pressed={pressed}
              title={deviation}
              data-testid={`sketch-entity-${row.id}`}
              onClick={() => onSelect(row.id === selected ? null : row.id)}
            >
              <span className={styles.name}>{row.name}</span>
              <span className={styles.value}>{row.size}</span>
              {row.passed === true && (
                <Check size={12} className={styles.pass} aria-label={deviation} />
              )}
              {row.passed === false && (
                <TriangleAlert size={12} className={styles.fail} aria-label={deviation} />
              )}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
