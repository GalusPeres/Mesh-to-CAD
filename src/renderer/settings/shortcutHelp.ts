// The shortcut help (Ctrl+/) is generated from the command registry, so it lists
// exactly the keys that work. Keys that panels handle themselves (the tool panel's
// Enter/Esc and the project tree's F2, Entf, H) are added from their definitions.

import type { TFunction } from 'i18next';

import { formatShortcut } from '../app/commands/keymap';
import type { AppCommand, Shortcut } from '../app/commands/types';
import { TREE_KEYS } from '../panels/treeMenu';

export interface ShortcutRow {
  id: string;
  label: string;
  keys: string[];
}

export interface ShortcutSection {
  id: string;
  title: string;
  rows: ShortcutRow[];
}

/** Section of a command, from the first part of its id (`view.fitAll` -> view). */
const SECTION_OF_PREFIX: Record<string, string> = {
  file: 'file',
  edit: 'edit',
  view: 'view',
  tool: 'tools',
  selection: 'selection',
  sketch: 'sketch',
  help: 'help',
  app: 'application',
};

const SECTION_ORDER = [
  'file',
  'edit',
  'view',
  'tools',
  'selection',
  'sketch',
  'toolPanel',
  'tree',
  'help',
  'application',
  'other',
];

const TOOL_PANEL_KEYS: readonly { id: string; shortcut: Shortcut }[] = [
  { id: 'commit', shortcut: { key: 'Enter' } },
  { id: 'apply', shortcut: { key: 'Enter', shift: true } },
  { id: 'cancel', shortcut: { key: 'Escape' } },
];

function commandOrder(command: AppCommand): [number, number] {
  return [command.placement?.group ?? 99, command.placement?.order ?? 99];
}

export function shortcutSections(
  commands: readonly AppCommand[],
  t: TFunction,
  language: string,
): ShortcutSection[] {
  const sections = new Map<string, ShortcutRow[]>();
  const add = (section: string, row: ShortcutRow) =>
    sections.set(section, [...(sections.get(section) ?? []), row]);

  const withKeys = commands
    .filter((command) => command.shortcuts?.length)
    .map((command, index) => ({ command, index }))
    .sort((a, b) => {
      const [groupA, orderA] = commandOrder(a.command);
      const [groupB, orderB] = commandOrder(b.command);
      return groupA - groupB || orderA - orderB || a.index - b.index;
    });
  for (const { command } of withKeys) {
    const prefix = command.id.split('.')[0] ?? '';
    add(SECTION_OF_PREFIX[prefix] ?? 'other', {
      id: command.id,
      label: t(command.label),
      keys: (command.shortcuts ?? []).map((shortcut) => formatShortcut(shortcut, language)),
    });
  }
  for (const { id, shortcut } of TOOL_PANEL_KEYS) {
    add('toolPanel', {
      id: `toolPanel.${id}`,
      label: t(`settings:shortcuts.toolPanel.${id}`),
      keys: [formatShortcut(shortcut, language)],
    });
  }
  const treeRows = new Map<string, ShortcutRow>();
  for (const [action, shortcut] of Object.entries(TREE_KEYS)) {
    const key = formatShortcut(shortcut, language);
    // Hide and show share H; the help lists the key once.
    const label = t(`settings:shortcuts.tree.${action === 'show' ? 'hide' : action}`);
    treeRows.set(label, { id: `tree.${action}`, label, keys: [key] });
  }
  treeRows.forEach((row) => add('tree', row));

  return SECTION_ORDER.flatMap((id) => {
    const rows = sections.get(id);
    return rows?.length ? [{ id, title: t(`settings:shortcuts.sections.${id}`), rows }] : [];
  });
}
