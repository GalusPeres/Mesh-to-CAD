import * as RadixTooltip from '@radix-ui/react-tooltip';
import type { ReactElement, ReactNode } from 'react';

import styles from './Tooltip.module.css';

export function TooltipProvider({ children }: { children: ReactNode }) {
  return (
    // Not hoverable: a tooltip closes as soon as the pointer leaves its control, so the
    // control next to it (often under the open tooltip's grace area) gets its own.
    <RadixTooltip.Provider delayDuration={500} skipDelayDuration={200} disableHoverableContent>
      {children}
    </RadixTooltip.Provider>
  );
}

export interface TooltipProps {
  /** Name of the control, then optionally its shortcut and one sentence. */
  label: ReactNode;
  shortcut?: string;
  description?: ReactNode;
  children: ReactElement;
  side?: 'top' | 'bottom' | 'left' | 'right';
}

export function Tooltip({ label, shortcut, description, children, side = 'bottom' }: TooltipProps) {
  return (
    <RadixTooltip.Root>
      <RadixTooltip.Trigger asChild>{children}</RadixTooltip.Trigger>
      <RadixTooltip.Portal>
        <RadixTooltip.Content
          className={styles.content}
          side={side}
          sideOffset={4}
          collisionPadding={8}
        >
          <span>{label}</span>
          {shortcut && <span className={styles.shortcut}>{shortcut}</span>}
          {description && <div className={styles.description}>{description}</div>}
        </RadixTooltip.Content>
      </RadixTooltip.Portal>
    </RadixTooltip.Root>
  );
}
