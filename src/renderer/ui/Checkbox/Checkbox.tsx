import styles from './Checkbox.module.css';

export interface CheckboxProps {
  checked: boolean;
  label: string;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  testId?: string;
}

/** A checkbox with its label; the whole row is clickable and uses the full panel width. */
export function Checkbox({ checked, label, onChange, disabled, testId }: CheckboxProps) {
  return (
    <label className={styles.row}>
      <input
        type="checkbox"
        className={styles.box}
        checked={checked}
        disabled={disabled}
        data-testid={testId}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className={disabled ? styles.disabled : undefined}>{label}</span>
    </label>
  );
}
