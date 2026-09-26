import { useTranslation } from 'react-i18next';

import { Button } from '../../ui/Button/Button';
import { commandById, runCommand } from '../commands/registry';
import styles from './EmptyState.module.css';

/** Start actions, shown in the order given; an action appears once its command exists. */
const START_COMMANDS = ['file.importScan', 'file.openProject', 'file.openExample'] as const;

/** Text only, left-aligned in the viewport; no illustration (docs/DESIGN.md 5.8). */
export function EmptyState() {
  const { t } = useTranslation();
  const commands = START_COMMANDS.map(commandById).filter((command) => command !== undefined);
  return (
    <section className={styles.empty} aria-labelledby="empty-title">
      <h1 id="empty-title" className={styles.title}>
        {t('empty.title')}
      </h1>
      <p className={styles.text}>{t('empty.text')}</p>
      <div className={styles.actions}>
        {commands.map((command, index) => (
          <Button
            key={command.id}
            variant={index === 0 ? 'primary' : 'secondary'}
            data-testid={index === 0 ? 'empty-import' : `empty-${command.id}`}
            onClick={() => void runCommand(command)}
          >
            {t(command.label)}
          </Button>
        ))}
      </div>
    </section>
  );
}
