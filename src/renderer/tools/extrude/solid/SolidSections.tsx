import { useTranslation } from 'react-i18next';

import type { ErrorInfo } from '@shared/protocol/generated/document-results';
import type { BodyOperation } from '@shared/protocol/generated/features-common';

import { useFormatter } from '../../../i18n/useFormatter';
import { describeError } from '../../../kernel/describeError';
import type { KernelFailure } from '../../../kernel/KernelFailure';
import { InlineMessage } from '../../../ui/InlineMessage/InlineMessage';
import { PanelSection } from '../../../ui/PanelSection/PanelSection';
import { PropertyRow, PropertyValue } from '../../../ui/PropertyRow/PropertyRow';
import { SegmentedControl } from '../../../ui/SegmentedControl/SegmentedControl';
import { Select } from '../../../ui/Select/Select';
import { type BodyOption, type InputProblem, OPERATIONS, needsTarget } from './model';
import type { SolidPreview } from './useSolidFeature';

const KEY = 'tools:extrude.solid';

export function useBodyLabel(): (body: BodyOption) => string {
  const { t } = useTranslation();
  return (body) => t(`${KEY}.body`, { number: body.number });
}

interface OperationProps {
  operation: BodyOperation;
  targetBody: string | null;
  bodies: readonly BodyOption[];
  onOperation: (operation: BodyOperation) => void;
  onTargetBody: (body: string) => void;
}

/** Operation (Neuer Körper / Vereinigen / Abziehen / Schnittmenge) and its target body. */
export function OperationFields({
  operation,
  targetBody,
  bodies,
  onOperation,
  onTargetBody,
}: OperationProps) {
  const { t } = useTranslation();
  const bodyLabel = useBodyLabel();
  if (bodies.length === 0) {
    return <PropertyValue label={t(`${KEY}.operation`)} value={t(`${KEY}.operations.newBody`)} />;
  }
  return (
    <>
      <PropertyRow label={t(`${KEY}.operation`)}>
        <SegmentedControl<BodyOperation>
          value={operation}
          ariaLabel={t(`${KEY}.operation`)}
          segments={OPERATIONS.map((value) => ({
            value,
            label: t(`${KEY}.operations.${value}`),
          }))}
          onChange={onOperation}
        />
      </PropertyRow>
      {needsTarget(operation) && (
        <BodySelect
          label={t(`${KEY}.targetBody`)}
          value={targetBody}
          bodies={bodies}
          onChange={onTargetBody}
          bodyLabel={bodyLabel}
        />
      )}
    </>
  );
}

interface BodySelectProps {
  label: string;
  value: string | null;
  bodies: readonly BodyOption[];
  onChange: (body: string) => void;
  bodyLabel: (body: BodyOption) => string;
  testId?: string;
}

export function BodySelect({ label, value, bodies, onChange, bodyLabel, testId }: BodySelectProps) {
  const { t } = useTranslation();
  const none = value === null || !bodies.some((body) => body.id === value);
  const options = bodies.map((body) => ({ value: body.id, label: bodyLabel(body) }));
  return (
    <PropertyRow label={label}>
      <Select<string>
        value={none ? '' : value}
        ariaLabel={label}
        testId={testId}
        options={none ? [{ value: '', label: t(`${KEY}.choose`) }, ...options] : options}
        onChange={(body) => body && onChange(body)}
      />
    </PropertyRow>
  );
}

/** "Zielkörper fehlt" and similar input problems, shown under the inputs. */
export function InputProblemMessage({ problem }: { problem: InputProblem | null }) {
  const { t } = useTranslation();
  if (!problem) return null;
  return <InlineMessage severity="info">{t(`${KEY}.problems.${problem}`)}</InlineMessage>;
}

function featureError(error: ErrorInfo, t: ReturnType<typeof useTranslation>['t']): string {
  const message = t(`errors:${error.code}`, { ...error.params, defaultValue: '' });
  return message || t('common:unexpectedError');
}

interface ResultProps {
  preview: SolidPreview;
  commitError: KernelFailure | null;
}

/** The _Ergebnis_ section: state of the preview, errors and warnings, body volume. */
export function SolidResult({ preview, commitError }: ResultProps) {
  const { t } = useTranslation();
  const format = useFormatter();
  const status = preview.status === 'ok' ? preview.result.status : null;
  const bodies = preview.status === 'ok' ? preview.result.bodies : [];
  return (
    <PanelSection title={t('common:sections.result')}>
      {preview.status === 'idle' && <p>{t(`${KEY}.inputsFirst`)}</p>}
      {preview.status === 'computing' && <p>{t('common:tool.computing')}</p>}
      {preview.status === 'error' && (
        <InlineMessage severity="error" details={preview.error.details ?? undefined}>
          {describeError(preview.error, t)}
        </InlineMessage>
      )}
      {status?.error && (
        <InlineMessage severity="error" details={status.error.details ?? undefined}>
          {featureError(status.error, t)}
        </InlineMessage>
      )}
      {status?.issues.map((issue) => (
        <InlineMessage key={issue.code} severity="warning">
          {t(`issues:${issue.code}`, issue.params)}
        </InlineMessage>
      ))}
      {bodies.map((body) => (
        <PropertyValue
          key={body.id}
          label={t(`${KEY}.volume`)}
          value={format.volume(body.volume)}
        />
      ))}
      {commitError && (
        <InlineMessage severity="error" details={commitError.details}>
          {describeError(commitError, t)}
        </InlineMessage>
      )}
    </PanelSection>
  );
}
