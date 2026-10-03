import styles from './SegmentedControl.module.css';

export interface Segment<T extends string> {
  value: T;
  label: string;
}

export interface SegmentedControlProps<T extends string> {
  value: T;
  segments: readonly Segment<T>[];
  onChange: (value: T) => void;
  ariaLabel: string;
  /** Each segment gets the test id `<testId>-<value>`. */
  testId?: string;
}

/** Mutually exclusive options shown side by side (operation, direction). */
export function SegmentedControl<T extends string>({
  value,
  segments,
  onChange,
  ariaLabel,
  testId,
}: SegmentedControlProps<T>) {
  return (
    <div className={styles.control} role="radiogroup" aria-label={ariaLabel}>
      {segments.map((segment) => (
        <button
          key={segment.value}
          type="button"
          role="radio"
          aria-checked={segment.value === value}
          data-testid={testId ? `${testId}-${segment.value}` : undefined}
          className={styles.segment}
          onClick={() => onChange(segment.value)}
        >
          {segment.label}
        </button>
      ))}
    </div>
  );
}
