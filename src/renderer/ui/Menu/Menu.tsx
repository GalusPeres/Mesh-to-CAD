import * as Dropdown from '@radix-ui/react-dropdown-menu';
import type { LucideIcon } from 'lucide-react';
import type { ReactElement, ReactNode } from 'react';

import styles from './Menu.module.css';

export interface MenuProps {
  trigger: ReactElement;
  children: ReactNode;
  align?: 'start' | 'end';
}

/** A dropdown menu; items are `MenuItem`, `MenuSeparator` and `MenuSub`. */
export function Menu({ trigger, children, align = 'start' }: MenuProps) {
  return (
    <Dropdown.Root modal={false}>
      <Dropdown.Trigger asChild>{trigger}</Dropdown.Trigger>
      <Dropdown.Portal>
        <Dropdown.Content
          className={styles.content}
          align={align}
          sideOffset={2}
          collisionPadding={8}
        >
          {children}
        </Dropdown.Content>
      </Dropdown.Portal>
    </Dropdown.Root>
  );
}

export interface MenuItemProps {
  label: string;
  icon?: LucideIcon;
  shortcut?: string;
  disabled?: boolean;
  checked?: boolean;
  testId?: string;
  onSelect: () => void;
}

export function MenuItem({
  label,
  icon: Icon,
  shortcut,
  disabled,
  checked,
  testId,
  onSelect,
}: MenuItemProps) {
  const content = (
    <>
      <span className={styles.icon} aria-hidden>
        {Icon && <Icon size={16} />}
      </span>
      <span className={styles.label}>{label}</span>
      {shortcut && <span className={styles.shortcut}>{shortcut}</span>}
    </>
  );
  if (checked !== undefined) {
    return (
      <Dropdown.CheckboxItem
        className={styles.item}
        checked={checked}
        disabled={disabled}
        data-testid={testId}
        onSelect={onSelect}
      >
        {content}
      </Dropdown.CheckboxItem>
    );
  }
  return (
    <Dropdown.Item
      className={styles.item}
      disabled={disabled}
      data-testid={testId}
      onSelect={onSelect}
    >
      {content}
    </Dropdown.Item>
  );
}

export function MenuSeparator() {
  return <Dropdown.Separator className={styles.separator} />;
}

export function MenuSub({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Dropdown.Sub>
      <Dropdown.SubTrigger className={styles.item}>
        <span className={styles.icon} aria-hidden />
        <span className={styles.label}>{label}</span>
        <span className={styles.chevron} aria-hidden>
          ›
        </span>
      </Dropdown.SubTrigger>
      <Dropdown.Portal>
        <Dropdown.SubContent className={styles.content} sideOffset={2} collisionPadding={8}>
          {children}
        </Dropdown.SubContent>
      </Dropdown.Portal>
    </Dropdown.Sub>
  );
}
