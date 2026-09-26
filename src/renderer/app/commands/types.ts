import type { LucideIcon } from 'lucide-react';

export interface Shortcut {
  /** `KeyboardEvent.key`, compared case-insensitively (`'I'`, `'Enter'`, `'['`). */
  key: string;
  ctrl?: boolean;
  shift?: boolean;
  alt?: boolean;
}

/**
 * Where a shortcut applies. `viewport` shortcuts work while the viewport or the
 * tree has focus and never in text fields; `sketch` ones only in sketch mode.
 * A key resolves in the order sketch, viewport, global.
 */
export type ShortcutScope = 'global' | 'viewport' | 'sketch';

export type MenuId = 'file' | 'edit' | 'view' | 'help';

export interface MenuPlacement {
  menu: MenuId;
  /** Items are grouped by this number; groups are separated by a line. */
  group: number;
  order: number;
}

/** Everything a user can trigger: menus, shortcuts and the shortcut help come from these. */
export interface AppCommand {
  /** Dotted id, also used for test ids: `menu-item-<id>`. */
  id: string;
  /** i18n key including the namespace, e.g. `common:commands.undo`. */
  label: string;
  icon?: LucideIcon;
  shortcuts?: readonly Shortcut[];
  scope?: ShortcutScope;
  /** Also runs while a text field has focus (file commands). */
  inTextFields?: boolean;
  placement?: MenuPlacement;
  isEnabled?(): boolean;
  isChecked?(): boolean;
  run(): void | Promise<void>;
}
