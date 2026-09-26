import { useTranslation } from 'react-i18next';

import { featureNames } from '../features/registry';
import { useFormatter } from '../i18n/useFormatter';
import { useDocument } from '../state/documentStore';
import { Button } from '../ui/Button/Button';
import { Dialog } from '../ui/Dialog/Dialog';
import { closeTreeDialogs, deleteFeature, dependentsQuestion, useTreeDialogs } from './treeActions';

/** Stable fallback, so the store selector does not return a new array on every call. */
const NO_FEATURES: readonly never[] = [];

/**
 * Asks before a feature is deleted together with the features that use it
 * (docs/DESIGN.md 5.5). The destructive button is secondary; Abbrechen is the default.
 */
function DeleteDialog() {
  const { t } = useTranslation(['panels', 'common']);
  const format = useFormatter();
  const remove = useTreeDialogs((state) => state.remove);
  const features = useDocument((state) => state.snapshot?.document.features ?? NO_FEATURES);

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
          <Button variant="primary" data-testid="delete-cancel" onClick={closeTreeDialogs}>
            {t('common:actions.cancel')}
          </Button>
        </>
      }
    >
      {remove &&
        dependentsQuestion(
          remove.featureId,
          remove.dependents,
          featureNames(features, t),
          format,
          t,
        )}
    </Dialog>
  );
}

export const dialog = DeleteDialog;
