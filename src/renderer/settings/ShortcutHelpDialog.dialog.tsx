import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { allCommands } from '../app/commands/registry';
import { Button } from '../ui/Button/Button';
import { Dialog } from '../ui/Dialog/Dialog';
import { closeDialog, useOpenDialog } from './appDialogStore';
import styles from './SettingsDialog.module.css';
import { shortcutSections } from './shortcutHelp';

/** Every shortcut, generated from the command registry (docs/DESIGN.md 7.2). */
function ShortcutHelpDialog() {
  const { t, i18n } = useTranslation(['settings', 'common']);
  const open = useOpenDialog() === 'shortcuts';
  const sections = useMemo(
    () => (open ? shortcutSections(allCommands(), t, i18n.language) : []),
    [open, t, i18n.language],
  );

  return (
    <Dialog
      open={open}
      wide
      title={t('shortcuts.title')}
      onOpenChange={(next) => {
        if (!next) closeDialog();
      }}
      footer={
        <Button variant="primary" data-testid="shortcuts-close" onClick={closeDialog}>
          {t('common:actions.close')}
        </Button>
      }
    >
      <p className={styles.hint}>{t('shortcuts.scopeHint')}</p>
      {sections.map((section) => (
        <section key={section.id} data-testid={`shortcuts-${section.id}`}>
          <h3 className={styles.heading}>{section.title}</h3>
          <table className={styles.table}>
            <tbody>
              {section.rows.map((row) => (
                <tr key={row.id}>
                  <th scope="row">{row.label}</th>
                  <td>{row.keys.join(t('shortcuts.or'))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </Dialog>
  );
}

export const dialog = ShortcutHelpDialog;
