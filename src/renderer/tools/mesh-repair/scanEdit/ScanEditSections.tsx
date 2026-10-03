import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { useFormatter } from '../../../i18n/useFormatter';
import { describeError } from '../../../kernel/describeError';
import { useDocument } from '../../../state/documentStore';
import { InlineMessage } from '../../../ui/InlineMessage/InlineMessage';
import { PanelSection } from '../../../ui/PanelSection/PanelSection';
import { PropertyValue } from '../../../ui/PropertyRow/PropertyRow';
import styles from './ScanEdit.module.css';
import type { ScanEdit } from './useScanEdit';

/** *Eingabe* of the preparation tools: the scan they work on. */
export function ScanInput() {
  const { t } = useTranslation();
  const format = useFormatter();
  const faceCount = useDocument((state) => state.snapshot?.document.scan?.faceCount ?? null);
  return (
    <PanelSection title={t('common:sections.input')}>
      <PropertyValue
        label={t('tools:meshRepair.shared.scan')}
        value={
          faceCount === null
            ? t('errors:mesh.noScan')
            : t('common:status.faces', { count: faceCount, formatted: format.count(faceCount) })
        }
      />
    </PanelSection>
  );
}

export interface ResultRow {
  label: string;
  value: string;
}

/**
 * *Ergebnis* of a preparation tool: what the dry run found, "Wird berechnet …"
 * while it runs, and the message when there is nothing to do.
 */
export function EditResult({
  edit,
  rows,
  nothingToDo,
  children,
}: {
  edit: ScanEdit;
  rows: readonly ResultRow[];
  nothingToDo: string;
  children?: ReactNode;
}) {
  const { t } = useTranslation();
  const { preview, result, commit } = edit;
  return (
    <PanelSection title={t('common:sections.result')}>
      {preview.status === 'computing' && (
        <p className={styles.hint}>{t('common:tool.computing')}</p>
      )}
      {result &&
        rows.map((row) => <PropertyValue key={row.label} label={row.label} value={row.value} />)}
      {preview.status === 'ok' && !preview.result.changed && (
        <InlineMessage severity="info">{nothingToDo}</InlineMessage>
      )}
      {preview.status === 'error' && (
        <InlineMessage severity="error" details={preview.error.details}>
          {describeError(preview.error, t)}
        </InlineMessage>
      )}
      {commit.error && (
        <InlineMessage severity="error" details={commit.error.details}>
          {describeError(commit.error, t)}
        </InlineMessage>
      )}
      {children}
    </PanelSection>
  );
}
