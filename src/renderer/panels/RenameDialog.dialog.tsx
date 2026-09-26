import { type FormEvent, useState } from 'react';
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
  // Keyed by the feature, so the field starts with the current name each time it opens.
  const [draft, setDraft] = useState<{ key: string; name: string } | null>(null);
  const key = rename?.featureId ?? '';
  const name = draft?.key === key ? draft.name : (rename?.name ?? '');
  const setName = (value: string) => setDraft({ key, name: value });

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
