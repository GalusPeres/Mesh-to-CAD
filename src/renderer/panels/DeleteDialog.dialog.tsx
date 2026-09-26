import { useTranslation } from 'react-i18next';

import { featureNames } from '../features/registry';
import { useFormatter } from '../i18n/useFormatter';
import { useDocument } from '../state/documentStore';
import { Button } from '../ui/Button/Button';
import { Dialog } from '../ui/Dialog/Dialog';
import { closeTreeDialogs, deleteFeature, useTreeDialogs } from './treeActions';

/** Asks before a feature is deleted together with the features that use it (docs/DESIGN.md 5.5). */
function DeleteDialog() {
  const { t } = useTranslation(['panels', 'common']);
  const format = useFormatter();
  const remove = useTreeDialogs((state) => state.remove);
  const features = useDocument((state) => state.snapshot?.document.features ?? []);
  const names = featureNames(features, t);
  const name = (id: string) => names.get(id) ?? id;

  return (
    <Dialog
      open={!!remove}
      title={t('delete.title')}
      onOpenChange={(open) => {
        if (!open) closeTreeDialogs();
      }}
      footer={
        <>
          <Button
            data-testid="delete-confirm"
            onClick={() => {
              if (!remove) return;
              closeTreeDialogs();
              void deleteFeature(remove.featureId, true);
            }}
          >
            {t('delete.confirm')}
          </Button>
          <Button variant="primary" onClick={closeTreeDialogs}>
            {t('common:actions.cancel')}
          </Button>
        </>
      }
    >
      {remove &&
        t('delete.withDependents', {
          name: name(remove.featureId),
          dependents: format.list(remove.dependents.map(name)),
        })}
    </Dialog>
  );
}

export const dialog = DeleteDialog;
