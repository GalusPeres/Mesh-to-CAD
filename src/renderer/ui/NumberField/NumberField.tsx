import { type KeyboardEvent, useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { createFormatter } from '../../i18n/format';
import { localeFor } from '../../i18n/useFormatter';
import { classNames } from '../../lib/classNames';
import { type NumberKind, parseNumberInput } from '../../lib/numberInput';
import styles from './NumberField.module.css';

export interface NumberFieldProps {
  value: number | null;
  onCommit: (value: number) => void;
  kind?: NumberKind;
  /** Unit shown inside the field; lengths default to mm, angles to °. */
  unit?: string;
  decimals?: number;
  step?: number;
  min?: number;
  max?: number;
  id?: string;
  disabled?: boolean;
  /** Computed values (not fixed by the user) are shown in the secondary colour. */
  computed?: boolean;
  ariaLabel?: string;
}

const DEFAULT_DECIMALS: Record<NumberKind, number> = { length: 3, angle: 2, count: 0, plain: 3 };

/**
 * Numeric input: accepts expressions and units, formats on blur, steps with the
 * arrow keys (Shift: ten steps). The mouse wheel never changes the value.
 */
export function NumberField(props: NumberFieldProps) {
  const { value, onCommit, kind = 'length', decimals = DEFAULT_DECIMALS[kind], step = 1 } = props;
  const { t, i18n } = useTranslation();
  const language = i18n.language === 'en' ? 'en' : 'de';
  const format = (number: number | null) =>
    number === null ? '' : createFormatter(localeFor(language)).number(number, decimals);
  const [text, setText] = useState(format(value));
  const [error, setError] = useState<string | null>(null);
  const generatedId = useId();
  const id = props.id ?? generatedId;
  const unit = props.unit ?? (kind === 'length' ? 'mm' : kind === 'angle' ? '°' : undefined);

  // Reformat when the value, the language or the precision changes (not on every
  // keystroke): state adjusted during render, as React recommends for derived state.
  const shownKey = `${value ?? ''}|${language}|${decimals}`;
  const [shown, setShown] = useState(shownKey);
  if (shown !== shownKey) {
    setShown(shownKey);
    setText(format(value));
    setError(null);
  }

  const clamp = (number: number) =>
    Math.min(props.max ?? Infinity, Math.max(props.min ?? -Infinity, number));

  const commit = () => {
    const parsed = parseNumberInput(text, { language, kind });
    if (!parsed.ok) {
      if (parsed.reason === 'empty') {
        setText(format(value));
        return;
      }
      setError(
        t(parsed.reason === 'ambiguous' ? 'ui:numberField.ambiguous' : 'ui:numberField.invalid'),
      );
      return;
    }
    const next = clamp(parsed.value);
    setError(null);
    setText(format(next));
    if (next !== value) onCommit(next);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') commit();
    if (event.key === 'Escape') {
      setText(format(value));
      setError(null);
    }
    if ((event.key === 'ArrowUp' || event.key === 'ArrowDown') && value !== null) {
      event.preventDefault();
      const delta = (event.key === 'ArrowUp' ? 1 : -1) * step * (event.shiftKey ? 10 : 1);
      onCommit(clamp(value + delta));
    }
  };

  return (
    <div className={styles.wrapper}>
      <div
        className={classNames(
          styles.field,
          error && styles.invalid,
          props.disabled && styles.disabled,
        )}
      >
        <input
          id={id}
          className={classNames(styles.input, props.computed && styles.computed)}
          value={text}
          disabled={props.disabled}
          inputMode="decimal"
          aria-label={props.ariaLabel}
          aria-invalid={!!error}
          aria-describedby={error ? `${id}-error` : undefined}
          onChange={(event) => setText(event.target.value)}
          onBlur={commit}
          onKeyDown={onKeyDown}
        />
        {unit && <span className={styles.unit}>{unit}</span>}
      </div>
      {error && (
        <div id={`${id}-error`} className={styles.message}>
          {error}
        </div>
      )}
    </div>
  );
}
