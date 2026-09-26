import { ChevronDown } from 'lucide-react';

import styles from './Select.module.css';

export interface SelectOption<T extends string> {
  value: T;
  label: string;
}

export interface SelectProps<T extends string> {
  value: T;
  options: readonly SelectOption<T>[];
  onChange: (value: T) => void;
  id?: string;
  disabled?: boolean;
  ariaLabel?: string;
  testId?: string;
}

/** A native select: the popup is the platform list, keyboard behaviour comes for free. */
export function Select<T extends string>({
  value,
  options,
  onChange,
  id,
  disabled,
  ariaLabel,
  testId,
}: SelectProps<T>) {
  return (
    <div className={styles.wrapper}>
      <select
        id={id}
        className={styles.select}
        value={value}
        disabled={disabled}
        aria-label={ariaLabel}
        data-testid={testId}
        onChange={(event) => onChange(event.target.value as T)}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <ChevronDown className={styles.chevron} size={16} aria-hidden />
    </div>
  );
}
