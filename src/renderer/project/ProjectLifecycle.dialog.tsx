import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '../ui/Button/Button';
import { Dialog } from '../ui/Dialog/Dialog';
import { confirmUnsavedChanges } from './fileActions';
import { useProjectStatus, windowTitle } from './projectStore';
import { useUnsavedQuestion } from './unsavedChanges';

/**
 * Keeps the window title current (`halterung* - Mesh-to-CAD`), asks about unsaved
 * changes before the window closes, and shows that question for New and Open.
 */
function ProjectLifecycle() {
  const { t } = useTranslation('project');
  const question = useUnsavedQuestion();
  const { name, unsaved } = useProjectStatus();

  useEffect(() => {
    window.m2c.window.setTitle(windowTitle(name, unsaved));
  }, [name, unsaved]);

  useEffect(
    () =>
      window.m2c.window.onBeforeClose(() => {
        void confirmUnsavedChanges().then((close) => {
          if (close) window.m2c.window.confirmClose();
        });
      }),
    [],
  );

  return (
    <Dialog
      open={!!question}
      title={t('unsaved.title')}
      onOpenChange={(open) => {
        if (!open) question?.answer('cancel');
      }}
      footer={
        <>
          <Button
            variant="primary"
            data-testid="unsaved-save"
            onClick={() => question?.answer('save')}
          >
            {t('unsaved.save')}
          </Button>
          <Button data-testid="unsaved-discard" onClick={() => question?.answer('discard')}>
            {t('unsaved.discard')}
          </Button>
          <Button data-testid="unsaved-cancel" onClick={() => question?.answer('cancel')}>
            {t('common:actions.cancel')}
          </Button>
        </>
      }
    >
      {question && t('unsaved.text', { name: question.name })}
    </Dialog>
  );
}

export const dialog = ProjectLifecycle;
