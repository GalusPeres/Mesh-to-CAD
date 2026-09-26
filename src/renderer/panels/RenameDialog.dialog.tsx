import { type FormEvent, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '../ui/Button/Button';
import { Dialog } from '../ui/Dialog/Dialog';
import { PropertyRow } from '../ui/PropertyRow/PropertyRow';
import styles from './TreeDialogs.module.css';
import { closeTreeDialogs, renameFeature, useTreeDialogs } from './treeActions';

/** Rename a history entry (F2); an empty name restores the default name. */
function RenameDialog() {
  const { t } = useTranslation(['panels', 'common']);
  const rename = useTreeDialogs((state) => state.rename);
  const [name, setName] = useState('');
  useEffect(() => setName(rename?.name ?? ''), [rename]);

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    if (!rename) return;
    closeTreeDialogs();
    void renameFeature(rename.featureId, name);
  };

  return (
    <Dialog
      open={!!rename}
      title={t('rename.title')}
      onOpenChange={(open) => {
        if (!open) closeTreeDialogs();
      }}
      footer={
        <>
          <Button variant="primary" data-testid="rename-ok" onClick={() => submit()}>
            {t('common:actions.ok')}
          </Button>
          <Button onClick={closeTreeDialogs}>{t('common:actions.cancel')}</Button>
        </>
      }
    >
      <form onSubmit={submit}>
        <PropertyRow label={t('rename.name')} htmlFor="rename-name">
          <input
            id="rename-name"
            data-testid="rename-name"
            className={styles.input}
            value={name}
            maxLength={80}
            autoFocus
            onFocus={(event) => event.currentTarget.select()}
            onChange={(event) => setName(event.currentTarget.value)}
          />
        </PropertyRow>
        <p className={styles.hint}>{t('rename.hint')}</p>
      </form>
    </Dialog>
  );
}

export const dialog = RenameDialog;
