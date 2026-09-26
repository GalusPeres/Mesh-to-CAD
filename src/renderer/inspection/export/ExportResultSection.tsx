import { FolderOpen } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { KernelFailure } from '../../kernel/KernelFailure';
import { describeError } from '../../kernel/describeError';
import { Button } from '../../ui/Button/Button';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import styles from './ExportResultSection.module.css';

export interface ExportResultSectionProps {
  busy: boolean;
  /** "STEP gespeichert: halterung.step (2 Körper, 184 KB)" after a successful export. */
  message: string | null;
  revealToken: string | null;
  error: KernelFailure | null;
}

/** Shown once an export ran: progress, the saved file with *Ordner öffnen*, or the error. */
export function ExportResultSection({
  busy,
  message,
  revealToken,
  error,
}: ExportResultSectionProps) {
  const { t } = useTranslation(['inspection', 'common']);
  if (!busy && !message && !error) return null;
  return (
    <PanelSection title={t('common:sections.result')}>
      {busy && <p className={styles.secondary}>{t('export.exporting')}</p>}
      {!busy && message && (
        <div className={styles.done} role="status" data-testid="export-done">
          <span>{message}</span>
          {revealToken && (
            <Button variant="ghost" onClick={() => window.m2c.files.reveal(revealToken)}>
              <FolderOpen size={16} aria-hidden />
              {t('export.revealFolder')}
            </Button>
          )}
        </div>
      )}
      {!busy && error && (
        <InlineMessage severity="error" details={error.details}>
          {describeError(error, t)}
        </InlineMessage>
      )}
    </PanelSection>
  );
}
