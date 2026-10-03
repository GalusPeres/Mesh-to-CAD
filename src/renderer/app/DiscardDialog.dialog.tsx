import { useTranslation } from 'react-i18next';

import { toolKey } from '../tools/framework/registry';
import { useDiscardQuestion } from '../tools/framework/toolActions';
import { Button } from '../ui/Button/Button';
import { Dialog } from '../ui/Dialog/Dialog';

/** Asks before a tool with changed inputs is closed (sketches, fillet edge picks). */
function DiscardDialog() {
  const { t } = useTranslation(['ui', 'common']);
  const question = useDiscardQuestion();
  return (
    <Dialog
      open={!!question}
      title={t('discardDraft.title')}
      onOpenChange={(open) => {
        if (!open) question?.answer(false);
      }}
      footer={
        <>
          <Button
            variant="primary"
            data-testid="discard-confirm"
            onClick={() => question?.answer(true)}
          >
            {t('discardDraft.discard')}
          </Button>
          <Button onClick={() => question?.answer(false)}>{t('common:actions.cancel')}</Button>
        </>
      }
    >
      {question && t('discardDraft.text', { tool: t(toolKey(question.toolId, 'label')) })}
    </Dialog>
  );
}

export const dialog = DiscardDialog;
