import * as RadixDialog from '@radix-ui/react-dialog';
import type { ReactNode } from 'react';

import { classNames } from '../../lib/classNames';
import styles from './Dialog.module.css';

export interface DialogProps {
  open: boolean;
  title: string;
  children: ReactNode;
  /** Buttons, right-aligned: the primary action first, then *Abbrechen*. */
  footer: ReactNode;
  wide?: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Modal dialogs are only for decisions that can lose data and for settings. */
export function Dialog({ open, title, children, footer, wide, onOpenChange }: DialogProps) {
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className={styles.scrim} />
        <RadixDialog.Content
          className={classNames(styles.dialog, wide && styles.wide)}
          aria-describedby={undefined}
        >
          <RadixDialog.Title className={styles.title}>{title}</RadixDialog.Title>
          <div className={styles.body}>{children}</div>
          <div className={styles.footer}>{footer}</div>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
