import type { LucideIcon } from 'lucide-react';
import type { ButtonHTMLAttributes } from 'react';

import { classNames } from '../../lib/classNames';
import { Tooltip } from '../Tooltip/Tooltip';
import styles from './IconButton.module.css';

export interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  icon: LucideIcon;
  /** Accessible name and tooltip text. */
  label: string;
  shortcut?: string;
  /** One sentence under the label in the tooltip. */
  description?: string;
  /** Toggle buttons pass their state. */
  pressed?: boolean;
}

export function IconButton({
  icon: Icon,
  label,
  shortcut,
  description,
  pressed,
  className,
  type = 'button',
  ...rest
}: IconButtonProps) {
  return (
    <Tooltip label={label} shortcut={shortcut} description={description}>
      <button
        type={type}
        aria-label={label}
        aria-pressed={pressed}
        className={classNames(styles.button, pressed && styles.pressed, className)}
        {...rest}
      >
        <Icon size={16} aria-hidden />
      </button>
    </Tooltip>
  );
}
