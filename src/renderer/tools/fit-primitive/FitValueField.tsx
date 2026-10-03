import { Lock, LockOpen } from 'lucide-react';
import { useId } from 'react';
import { useTranslation } from 'react-i18next';

import { useFormatter } from '../../i18n/useFormatter';
import { IconButton } from '../../ui/IconButton/IconButton';
import { NumberField } from '../../ui/NumberField/NumberField';
import { PropertyRow } from '../../ui/PropertyRow/PropertyRow';
import type { Vec3 } from './fitDraft';
import styles from './FitValueField.module.css';

export interface FitValueFieldProps {
  label: string;
  /** The fixed value, or the computed one; null while nothing is computed yet. */
  value: number | null;
  fixed: boolean;
  kind: 'length' | 'angle';
  /** Lower bound of typed values (radii and angles are positive). */
  min?: number;
  onFix: (value: number) => void;
  onRelease: () => void;
  disabled?: boolean;
  testId?: string;
}

/**
 * A fitted value with its state: Berechnet (computed by the fit, secondary colour)
 * or Fest (kept by the fit). Typing a value fixes it (docs/DESIGN.md 4, 5.2).
 */
export function FitValueField(props: FitValueFieldProps) {
  const { t } = useTranslation('tools');
  const id = useId();
  const { value, fixed } = props;
  const toggle = () => {
    if (fixed) props.onRelease();
    else if (value !== null) props.onFix(value);
  };
  return (
    <PropertyRow label={props.label} htmlFor={id}>
      <div className={styles.field} data-testid={props.testId}>
        <IconButton
          icon={fixed ? Lock : LockOpen}
          label={t(fixed ? 'fitPrimitive.fixedHint' : 'fitPrimitive.computedHint')}
          pressed={fixed}
          className={styles.toggle}
          disabled={props.disabled || (!fixed && value === null)}
          onClick={toggle}
        />
        <NumberField
          id={id}
          value={value}
          kind={props.kind}
          computed={!fixed}
          disabled={props.disabled}
          min={props.min}
          onCommit={props.onFix}
        />
      </div>
    </PropertyRow>
  );
}

export interface FitVectorFieldProps {
  label: string;
  value: Vec3 | null;
  fixed: boolean;
  /** Directions show three decimals without a unit, points in millimetres. */
  kind: 'direction' | 'point';
  onFix: (value: Vec3) => void;
  onRelease: () => void;
  disabled?: boolean;
}

/** A direction or point: computed or fixed as a whole, shown as its three components. */
export function FitVectorField(props: FitVectorFieldProps) {
  const { t } = useTranslation('tools');
  const format = useFormatter();
  const { value, fixed } = props;
  const text = value
    ? value.map((component) => format.number(component, props.kind === 'point' ? 3 : 4)).join('; ')
    : '–';
  const toggle = () => {
    if (fixed) props.onRelease();
    else if (value !== null) props.onFix(value);
  };
  return (
    <PropertyRow label={props.label}>
      <div className={styles.field}>
        <IconButton
          icon={fixed ? Lock : LockOpen}
          label={t(fixed ? 'fitPrimitive.fixedHint' : 'fitPrimitive.computedHint')}
          pressed={fixed}
          className={styles.toggle}
          disabled={props.disabled || (!fixed && value === null)}
          onClick={toggle}
        />
        <span className={fixed ? styles.vector : styles.computedVector}>
          {text}
          {props.kind === 'point' && value ? ' mm' : ''}
        </span>
      </div>
    </PropertyRow>
  );
}
