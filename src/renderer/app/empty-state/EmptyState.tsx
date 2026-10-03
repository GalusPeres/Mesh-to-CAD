import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { RecentFile } from '@shared/bridge';

import { openExample } from '../../help/examples';
import { useJobs } from '../../state/jobStore';
import { Button } from '../../ui/Button/Button';
import { commandById, runCommand } from '../commands/registry';
import styles from './EmptyState.module.css';
import { openRecent, recentRows } from './recentFiles';

/** Import is the primary start action; opening a project appears once its command exists. */
const IMPORT_COMMAND = 'file.importScan';
const OPEN_PROJECT_COMMAND = 'file.openProject';

function useRecentFiles(): RecentFile[] {
  const [files, setFiles] = useState<RecentFile[]>([]);
  useEffect(() => {
    let current = true;
    window.m2c.recent
      .list()
      .then((list) => {
        if (current) setFiles(recentRows(list));
      })
      .catch(() => undefined);
    return () => {
      current = false;
    };
  }, []);
  return files;
}

/** Text only, left-aligned in the viewport; no illustration (docs/DESIGN.md 5.8). */
export function EmptyState() {
  const { t } = useTranslation(['common', 'help']);
  const recent = useRecentFiles();
  const ready = useJobs((state) => state.kernel.state === 'ready');
  const importScan = commandById(IMPORT_COMMAND);
  const openProject = commandById(OPEN_PROJECT_COMMAND);

  return (
    <section className={styles.empty} aria-labelledby="empty-title" data-testid="empty-state">
      <h1 id="empty-title" className={styles.title}>
        {t('empty.title')}
      </h1>
      <p className={styles.text}>{t('empty.text')}</p>
      <div className={styles.actions}>
        {importScan && (
          <Button
            variant="primary"
            data-testid="empty-import"
            onClick={() => void runCommand(importScan)}
          >
            {t(importScan.label)}
          </Button>
        )}
        {openProject && (
          <Button data-testid="empty-open-project" onClick={() => void runCommand(openProject)}>
            {t(openProject.label)}
          </Button>
        )}
        <Button
          data-testid="empty-open-example"
          disabled={!ready}
          onClick={() => void openExample('bracket')}
        >
          {t('help:examples.open')}
        </Button>
      </div>
      {recent.length > 0 && (
        <>
          <h2 className={styles.recentTitle}>{t('empty.recent')}</h2>
          <ul className={styles.recent} data-testid="empty-recent">
            {recent.map((file, index) => (
              <li key={file.id}>
                <button
                  type="button"
                  className={styles.recentRow}
                  data-testid={`empty-recent-${index}`}
                  disabled={!ready}
                  onClick={() => void openRecent(file)}
                >
                  <span className={styles.recentName}>{file.name}</span>
                  <span className={styles.recentFolder}>{file.folder}</span>
                  <span className={styles.recentDate}>
                    {t('help:start.openedAt', {
                      date: new Date(file.openedAt),
                      formatParams: { date: { dateStyle: 'medium' } },
                    })}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
