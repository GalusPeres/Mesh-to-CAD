import { classNames } from '../../lib/classNames';
import styles from './ProgressBar.module.css';

export interface ProgressBarProps {
  /** 0..1, or null while the work cannot report progress (a long native call). */
  fraction: number | null;
  label: string;
}

/**
 * A static bar; the indeterminate state is a dimmed full bar, not an animation
 * (docs/DESIGN.md 2.5: no spinners, elapsed time appears after 10 s instead).
 */
export function ProgressBar({ fraction, label }: ProgressBarProps) {
  const indeterminate = fraction === null;
  const percent = indeterminate ? 100 : Math.round(Math.min(1, Math.max(0, fraction)) * 100);
  return (
    <div
      className={styles.track}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={indeterminate ? undefined : percent}
    >
      <div
        className={classNames(styles.fill, indeterminate && styles.indeterminate)}
        style={{ width: `${percent}%` }}
      />
    </div>
  );
}
