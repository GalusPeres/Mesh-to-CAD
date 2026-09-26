import type { ReactNode } from 'react';

import styles from './PropertyRow.module.css';

export interface PropertyRowProps {
  label: string;
  /** Id of the control, so clicking the label focuses it. */
  htmlFor?: string;
  children: ReactNode;
}

/** Label and control. Long German labels wrap to a second line instead of being cut off. */
export function PropertyRow({ label, htmlFor, children }: PropertyRowProps) {
  return (
    <div className={styles.row}>
      <label className={styles.label} htmlFor={htmlFor}>
        {label}
      </label>
      <div className={styles.control}>{children}</div>
    </div>
  );
}

/** A read-only value, right-aligned with tabular figures. */
export function PropertyValue({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className={styles.row}>
      <span className={styles.label}>{label}</span>
      <span className={styles.value}>{value}</span>
    </div>
  );
}
