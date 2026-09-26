import type { LucideIcon } from 'lucide-react';

import { classNames } from '../../lib/classNames';
import { Tooltip } from '../Tooltip/Tooltip';
import styles from './ToolButton.module.css';

export interface ToolButtonProps {
  icon: LucideIcon;
  label: string;
  shortcut?: string;
  /** Primary tools show their label next to the icon. */
  showLabel?: boolean;
  active?: boolean;
  disabled?: boolean;
  /** Why the tool is disabled; shown in the tooltip. */
  disabledReason?: string;
  testId?: string;
  onClick: () => void;
}

export function ToolButton(props: ToolButtonProps) {
  const {
    icon: Icon,
    label,
    shortcut,
    showLabel,
    active,
    disabled,
    disabledReason,
    testId,
    onClick,
  } = props;
  return (
    <Tooltip label={label} shortcut={shortcut} description={disabled ? disabledReason : undefined}>
      <button
        type="button"
        className={classNames(
          styles.button,
          active && styles.active,
          showLabel && styles.withLabel,
        )}
        aria-label={showLabel ? undefined : label}
        aria-pressed={active}
        aria-disabled={disabled}
        data-testid={testId}
        onClick={disabled ? undefined : onClick}
      >
        <Icon size={16} aria-hidden />
        {showLabel && <span>{label}</span>}
      </button>
    </Tooltip>
  );
}
