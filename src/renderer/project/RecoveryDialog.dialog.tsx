import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { RecoveryCandidate } from '@shared/bridge';

import { KernelFailure } from '../kernel/KernelFailure';
import { clearHistory } from '../state/historyStore';
import { showMessage } from '../state/messageStore';
import { Button } from '../ui/Button/Button';
import { Dialog } from '../ui/Dialog/Dialog';
import { reportFailure } from './fileActions';
import { markUntitled } from './projectStore';

/**
 * At start, offers the work of an instance that ended without closing
 * (`recovery.list`). *Wiederherstellen* switches the computing process to that
 * session; *Verwerfen* deletes it. Closing the dialog decides nothing, so the
 * session is offered again at the next start.
 */
function RecoveryDialog() {
  const { t } = useTranslation('project');
  const [candidates, setCandidates] = useState<RecoveryCandidate[]>([]);
  const [busy, setBusy] = useState(false);
  const candidate = candidates[0];

  useEffect(() => {
    let current = true;
    void window.m2c.recovery.list().then((found) => {
      if (current) setCandidates(found);
    });
    return () => {
      current = false;
    };
  }, []);

  const resolve = async (action: 'restore' | 'discard') => {
    if (!candidate) return;
    setBusy(true);
    try {
      const status = await window.m2c.recovery.resolve(candidate.id, action);
      if (action === 'restore') {
        // The restarted computing process reports the recovered document itself.
        clearHistory();
        markUntitled();
        setCandidates([]);
        if (status.state === 'stopped') {
          reportFailure(new KernelFailure(status.error ?? { code: 'kernel.stopped', params: {} }));
        } else {
          showMessage('success', t('recovery.restored', { name: candidate.label }));
        }
      } else {
        setCandidates((remaining) => remaining.filter((item) => item.id !== candidate.id));
      }
    } catch (error) {
      reportFailure(error);
      setCandidates([]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={!!candidate}
      title={t('recovery.title')}
      onOpenChange={(open) => {
        if (!open && !busy) setCandidates([]);
      }}
      footer={
        <>
          <Button
            variant="primary"
            disabled={busy}
            data-testid="recovery-restore"
            onClick={() => void resolve('restore')}
          >
            {t('recovery.restore')}
          </Button>
          <Button
            disabled={busy}
            data-testid="recovery-discard"
            onClick={() => void resolve('discard')}
          >
            {t('recovery.discard')}
          </Button>
        </>
      }
    >
      {candidate &&
        t('recovery.text', { name: candidate.label, startedAt: new Date(candidate.startedAt) })}
    </Dialog>
  );
}

export const dialog = RecoveryDialog;
