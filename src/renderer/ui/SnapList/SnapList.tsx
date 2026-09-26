import { X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { IconButton } from '../IconButton/IconButton';
import styles from './SnapList.module.css';

export interface SnapListItem {
  /** Stable id, passed back to `onRemove` (for example `radius` or `e3.length`). */
  id: string;
  /** What snapped, translated and formatted: "Radius 8,000 mm", "Achse parallel zu Z". */
  text: string;
  /** The measurement the value replaced, formatted: "7,987 ± 0,012". Omitted for relations. */
  measured?: string;
}

export interface SnapListProps {
  items: readonly SnapListItem[];
  onRemove: (id: string) => void;
}

/**
 * Design values applied by snapping, each with the measurement it replaced and a
 * button that removes it (docs/DESIGN.md 4 and 5.2). Used by fits and sketches.
 */
export function SnapList({ items, onRemove }: SnapListProps) {
  const { t } = useTranslation('ui');
  if (items.length === 0) return null;
  return (
    <ul className={styles.list} aria-label={t('snapList.label')}>
      {items.map((item) => (
        <li key={item.id} className={styles.row}>
          <span className={styles.text}>{item.text}</span>
          <span className={styles.measured}>
            {item.measured ? t('snapList.measured', { value: item.measured }) : null}
          </span>
          <IconButton
            icon={X}
            label={t('snapList.remove', { name: item.text })}
            onClick={() => onRemove(item.id)}
          />
        </li>
      ))}
    </ul>
  );
}
