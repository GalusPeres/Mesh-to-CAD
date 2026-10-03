import { Check, TriangleAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { EntityFitInfo } from '@shared/protocol/generated/sketch';
import type { SketchParams } from '@shared/protocol/generated/sketch-params';

import { useFormatter } from '../../i18n/useFormatter';
import { entitySize } from './describe';
import styles from './SketchPanel.module.css';

const K = 'sectionSketch';

interface EntityListProps {
  sketch: SketchParams;
  labels: ReadonlyMap<string, string>;
  fits: readonly EntityFitInfo[];
  selected: string | null;
  onSelect: (id: string | null) => void;
}

/** One row per entity: name, length or radius, largest deviation and the pass/fail icon. */
export function EntityList({ sketch, labels, fits, selected, onSelect }: EntityListProps) {
  const { t } = useTranslation('tools');
  const format = useFormatter();
  if (sketch.entities.length === 0) return <p className={styles.hint}>{t(`${K}.noEntities`)}</p>;
  const verdicts = new Map(fits.map((fit) => [fit.entity, fit]));
  return (
    <ul className={styles.list} aria-label={t(`${K}.entities`)}>
      {sketch.entities.map((entity) => {
        const fit = verdicts.get(entity.id);
        const deviation =
          fit?.maxDistance != null
            ? t(`${K}.deviation`, { value: format.length(fit.maxDistance) })
            : null;
        const origin = entity.origin === 'drawn' ? ` · ${t(`${K}.drawn`)}` : '';
        return (
          <li key={entity.id}>
            <button
              type="button"
              className={styles.row}
              aria-pressed={entity.id === selected}
              title={deviation ?? undefined}
              data-testid={`sketch-entity-${entity.id}`}
              onClick={() => onSelect(entity.id === selected ? null : entity.id)}
            >
              <span className={styles.name}>
                {labels.get(entity.id)}
                {origin}
              </span>
              <span className={styles.value}>{entitySize(sketch, entity, format)}</span>
              {fit?.passed === true && (
                <Check size={12} className={styles.pass} aria-label={deviation ?? undefined} />
              )}
              {fit?.passed === false && (
                <TriangleAlert
                  size={12}
                  className={styles.fail}
                  aria-label={deviation ?? undefined}
                />
              )}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
