import { useTranslation } from 'react-i18next';

import type { BodyPreflight } from '@shared/protocol/generated/export';

import { useFormatter } from '../../i18n/useFormatter';
import { describeError } from '../../kernel/describeError';
import { useDocument } from '../../state/documentStore';
import { Checkbox } from '../../ui/Checkbox/Checkbox';
import { InlineMessage } from '../../ui/InlineMessage/InlineMessage';
import { bodyNames, documentFeatureNames } from '../names';
import styles from './ExportBodyList.module.css';
import type { PreflightState } from './usePreflight';

const WARNING = 'export.highTolerance';

export interface ExportBodyListProps {
  preflight: PreflightState;
  selected: readonly string[];
  onChange: (selected: string[]) => void;
}

/**
 * One checkbox per body with its pre-flight result. A body with a blocking problem
 * cannot be chosen; the message names the problem and the feature that caused it.
 */
export function ExportBodyList({ preflight, selected, onChange }: ExportBodyListProps) {
  const { t } = useTranslation(['inspection', 'issues']);
  const format = useFormatter();
  const snapshot = useDocument((state) => state.snapshot);
  const bodies = bodyNames(snapshot, t);
  const features = documentFeatureNames(snapshot, t);

  if (preflight.status === 'checking') {
    return <p className={styles.secondary}>{t('export.checking')}</p>;
  }
  if (preflight.status === 'error') {
    return (
      <InlineMessage severity="error" details={preflight.error.details}>
        {describeError(preflight.error, t)}
      </InlineMessage>
    );
  }

  const problem = (report: BodyPreflight, code: string) =>
    t(`issues:${code}`, {
      body: bodies.get(report.body) ?? report.body,
      tolerance: format.length(report.maxTolerance, { decimals: 4 }),
    });

  return (
    <div role="group" aria-label={t('export.bodies')} className={styles.list}>
      {preflight.result.bodies.map((report) => {
        const name = bodies.get(report.body) ?? report.body;
        const blocking = report.problems.filter((code) => code !== WARNING);
        const warnings = report.problems.filter((code) => code === WARNING);
        return (
          <div key={report.body} className={styles.body}>
            <Checkbox
              label={`${name} · ${format.volume(report.volume)}`}
              checked={!report.blocking && selected.includes(report.body)}
              disabled={report.blocking}
              testId={`export-body-${report.body}`}
              onChange={(checked) =>
                onChange(
                  checked
                    ? [...selected, report.body]
                    : selected.filter((id) => id !== report.body),
                )
              }
            />
            {blocking.map((code) => (
              <InlineMessage key={code} severity="warning">
                {t('export.blocked', {
                  problem: problem(report, code),
                  feature: features.get(report.owner) ?? report.owner,
                })}
              </InlineMessage>
            ))}
            {warnings.map((code) => (
              <InlineMessage key={code} severity="info">
                {t('export.exportable', { problem: problem(report, code) })}
              </InlineMessage>
            ))}
          </div>
        );
      })}
    </div>
  );
}

/** Bodies to export: the chosen ones that passed the pre-flight check. */
export function exportableSelection(
  preflight: PreflightState,
  selected: readonly string[],
): string[] {
  if (preflight.status !== 'ok') return [];
  return preflight.result.bodies
    .filter((report) => !report.blocking && selected.includes(report.body))
    .map((report) => report.body);
}
