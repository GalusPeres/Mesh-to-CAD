import { type FormEvent, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '../ui/Button/Button';
import { Dialog } from '../ui/Dialog/Dialog';
import { PropertyRow } from '../ui/PropertyRow/PropertyRow';
import {
  closeRegionDialogs,
  documentRegions,
  renameRegion,
  useRegionDialogs,
} from './regionActions';
import styles from './RegionRenameDialog.module.css';

/** Rename a region; an empty name returns to "Bereich N". */
function RegionRenameDialog() {
  const { t } = useTranslation(['selection', 'common']);
  const rename = useRegionDialogs((state) => state.rename);
  const [draft, setDraft] = useState<{ key: string; name: string } | null>(null);
  const key = rename?.regionId ?? '';
  const name = draft?.key === key ? draft.name : (rename?.name ?? '');

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    const region = documentRegions().find((item) => item.id === rename?.regionId);
    closeRegionDialogs();
    if (region) void renameRegion(region, name);
  };

  return (
    <Dialog
      open={!!rename}
      title={t('regions.renameTitle')}
      onOpenChange={(open) => {
        if (!open) closeRegionDialogs();
      }}
      footer={
        <>
          <Button variant="primary" data-testid="region-rename-ok" onClick={() => submit()}>
            {t('common:actions.ok')}
          </Button>
          <Button onClick={closeRegionDialogs}>{t('common:actions.cancel')}</Button>
        </>
      }
    >
      <form onSubmit={submit}>
        <PropertyRow label={t('regions.name')} htmlFor="region-rename-name">
          <input
            id="region-rename-name"
            data-testid="region-rename-name"
            className={styles.input}
            value={name}
            maxLength={80}
            autoFocus
            onFocus={(event) => event.currentTarget.select()}
            onChange={(event) => setDraft({ key, name: event.currentTarget.value })}
          />
        </PropertyRow>
        <p className={styles.hint}>{t('regions.renameHint')}</p>
      </form>
    </Dialog>
  );
}

export const dialog = RegionRenameDialog;
