import type { ButtonHTMLAttributes } from 'react';

import { classNames } from '../../lib/classNames';
import styles from './Button.module.css';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** One primary button per panel or dialog. */
  variant?: ButtonVariant;
}

export function Button({
  variant = 'secondary',
  className,
  type = 'button',
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={classNames(styles.button, styles[variant], className)}
      {...rest}
    />
  );
}
