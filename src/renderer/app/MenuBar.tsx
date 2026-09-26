import { useTranslation } from 'react-i18next';

import { Menu, MenuItem, MenuSeparator } from '../ui/Menu/Menu';
import { formatShortcut } from './commands/keymap';
import { menuGroups, runCommand } from './commands/registry';
import type { MenuId } from './commands/types';
import styles from './MenuBar.module.css';

const MENUS: readonly MenuId[] = ['file', 'edit', 'view', 'help'];

/** The items of one menu. Rendered when the menu opens, so enabled states are current. */
function MenuCommands({ menu }: { menu: MenuId }) {
  const { t, i18n } = useTranslation();
  return menuGroups(menu).map((group, index) => (
    <div key={index} role="presentation">
      {index > 0 && <MenuSeparator />}
      {group.map((command) => (
        <MenuItem
          key={command.id}
          label={t(command.label)}
          icon={command.icon}
          shortcut={command.shortcuts?.[0] && formatShortcut(command.shortcuts[0], i18n.language)}
          disabled={command.isEnabled ? !command.isEnabled() : false}
          checked={command.isChecked?.()}
          testId={`menu-item-${command.id}`}
          onSelect={() => void runCommand(command)}
        />
      ))}
    </div>
  ));
}

/** Datei, Bearbeiten, Ansicht, Hilfe: built from the command registry; empty menus are hidden. */
export function MenuBar() {
  const { t } = useTranslation();
  return (
    <nav className={styles.bar}>
      {MENUS.filter((menu) => menuGroups(menu).length > 0).map((menu) => (
        <Menu
          key={menu}
          trigger={
            <button type="button" className={styles.trigger} data-testid={`menu-${menu}`}>
              {t(`menu.${menu}`)}
            </button>
          }
        >
          <MenuCommands menu={menu} />
        </Menu>
      ))}
    </nav>
  );
}
