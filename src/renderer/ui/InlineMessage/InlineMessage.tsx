import { CircleAlert, Info, TriangleAlert } from 'lucide-react';
import { type ReactNode, useState } from 'react';
import { useTranslation } from 'react-i18next';

import styles from './InlineMessage.module.css';

export type MessageSeverity = 'info' | 'warning' | 'error';

const ICONS = { info: Info, warning: TriangleAlert, error: CircleAlert } as const;

export interface InlineMessageProps {
  severity: MessageSeverity;
  children: ReactNode;
  /** Technical text (codes, traceback) behind a *Details* disclosure. */
  details?: string;
}

/** A severity icon in the semantic colour, then normal text. Never a coloured box. */
export function InlineMessage({ severity, children, details }: InlineMessageProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const Icon = ICONS[severity];
  return (
    <div className={styles.message} role={severity === 'error' ? 'alert' : 'status'}>
      <Icon className={styles[severity]} size={16} aria-hidden />
      <div className={styles.body}>
        <div>{children}</div>
        {details && (
          <>
            <button
              type="button"
              className={styles.toggle}
              aria-expanded={open}
              onClick={() => setOpen(!open)}
            >
              {t('actions.details')}
            </button>
            {open && <pre className={styles.details}>{details}</pre>}
          </>
        )}
      </div>
    </div>
  );
}
