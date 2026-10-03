import type { TFunction } from 'i18next';
import { Ban, Check, CircleAlert, TriangleAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import type { Feature, Region, Scan } from '@shared/protocol/generated/document-model';
import type { BodyInfo, FeatureStatus, Issue } from '@shared/protocol/generated/document-results';
import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';

import { featureNames, featureView } from '../features/registry';
import { useFormatter } from '../i18n/useFormatter';
import { InlineMessage } from '../ui/InlineMessage/InlineMessage';
import { PanelSection } from '../ui/PanelSection/PanelSection';
import { PropertyValue } from '../ui/PropertyRow/PropertyRow';
import { shownStatus } from './featureState';
import styles from './ObjectProperties.module.css';
import { operationLabel } from './treeModel';
import { usedFeatures } from './usedConstruction';

export function ScanProperties({ scan, tolerance }: { scan: Scan; tolerance: number }) {
  const { t } = useTranslation('panels');
  const format = useFormatter();
  const operations = scan.operations.filter((operation) => operation.op !== 'import');
  return (
    <>
      <PanelSection title={t('properties.scanSection')}>
        <PropertyValue label={t('properties.file')} value={scan.source.fileName} />
        <PropertyValue
          label={t('properties.unit')}
          value={t(`common:units.${scan.source.importUnit}`)}
        />
        <PropertyValue label={t('properties.triangles')} value={format.count(scan.faceCount)} />
        <PropertyValue label={t('properties.vertices')} value={format.count(scan.vertexCount)} />
        <PropertyValue
          label={t('properties.noise')}
          value={scan.noise === null ? t('properties.unknown') : format.length(scan.noise)}
        />
        <PropertyValue
          label={t('properties.tolerance')}
          value={format.length(tolerance, { signed: true })}
        />
      </PanelSection>
      {operations.length > 0 && (
        <PanelSection title={t('properties.operations')}>
          <ul className={styles.list} data-testid="properties-operations">
            {operations.map((operation, index) => (
              <li key={index}>{operationLabel(operation, t, format)}</li>
            ))}
          </ul>
        </PanelSection>
      )}
    </>
  );
}

const STATE_ICONS = {
  ok: { icon: Check, className: styles.ok },
  warning: { icon: TriangleAlert, className: styles.warning },
  error: { icon: CircleAlert, className: styles.error },
  suppressed: { icon: Ban, className: styles.disabled },
  skipped: { icon: Ban, className: styles.disabled },
} as const;

function StateValue({ state, t }: { state: keyof typeof STATE_ICONS; t: TFunction }) {
  const { icon: Icon, className } = STATE_ICONS[state];
  return (
    <span className={styles.state} data-testid="properties-feature-state" data-state={state}>
      <Icon size={12} className={className} aria-hidden />
      {t(`panels:state.${state}`)}
    </span>
  );
}

/** Error, warnings and the reason a feature was not evaluated. */
function StatusMessages({
  error,
  issues,
  state,
}: {
  error?: FeatureStatus['error'];
  issues: Issue[];
  state: string;
}) {
  const { t } = useTranslation(['panels', 'errors', 'issues']);
  return (
    <>
      {error && (
        <InlineMessage severity="error" details={error.details ?? error.code}>
          {t(`errors:${error.code}`, {
            ...error.params,
            defaultValue: t('common:unexpectedError'),
          })}
        </InlineMessage>
      )}
      {issues.map((issue) => (
        <InlineMessage key={`${issue.code}:${JSON.stringify(issue.params)}`} severity="warning">
          {t(`issues:${issue.code}`, { ...issue.params, defaultValue: issue.code })}
        </InlineMessage>
      ))}
      {state === 'skipped' && (
        <InlineMessage severity="info">{t('properties.skipped')}</InlineMessage>
      )}
      {state === 'suppressed' && (
        <InlineMessage severity="info">{t('properties.suppressed')}</InlineMessage>
      )}
    </>
  );
}

export function FeatureProperties({
  feature,
  snapshot,
}: {
  feature: Feature;
  snapshot: DocumentSnapshot;
}) {
  const { t } = useTranslation(['panels', 'features']);
  const format = useFormatter();
  const view = featureView(feature.type);
  const { state, issues } = shownStatus(
    feature,
    snapshot.status.features[feature.id],
    usedFeatures(snapshot),
  );
  const error = snapshot.status.features[feature.id]?.error;
  const summary = view?.summary?.(feature.params as never, format, t);
  const Properties = view?.Properties;
  return (
    <>
      <PanelSection title={t('properties.featureSection')}>
        <PropertyValue label={t('properties.type')} value={t(`features:${feature.type}.name`)} />
        {summary && <PropertyValue label={t('properties.summary')} value={summary} />}
        <PropertyValue label={t('properties.status')} value={<StateValue state={state} t={t} />} />
        <StatusMessages error={error} issues={issues} state={state} />
      </PanelSection>
      {Properties && (
        <PanelSection title={t('common:sections.parameters')}>
          <Properties featureId={feature.id} />
        </PanelSection>
      )}
    </>
  );
}

export function BodyProperties({ body, snapshot }: { body: BodyInfo; snapshot: DocumentSnapshot }) {
  const { t } = useTranslation('panels');
  const format = useFormatter();
  const names = featureNames(snapshot.document.features, t);
  return (
    <PanelSection title={t('properties.bodySection')}>
      <PropertyValue label={t('properties.createdBy')} value={names.get(body.id) ?? body.id} />
      {body.owner !== body.id && (
        <PropertyValue
          label={t('properties.changedBy')}
          value={names.get(body.owner) ?? body.owner}
        />
      )}
      <PropertyValue label={t('properties.volume')} value={format.volume(body.volume)} />
      <PropertyValue label={t('properties.area')} value={format.area(body.area)} />
      <PropertyValue label={t('properties.solids')} value={format.count(body.solids)} />
      <PropertyValue
        label={t('properties.maxTolerance')}
        value={format.length(body.maxTolerance)}
      />
      <PropertyValue
        label={t('properties.validity')}
        value={
          <span className={styles.state} data-testid="properties-body-valid">
            {body.valid ? (
              <Check size={12} className={styles.ok} aria-hidden />
            ) : (
              <CircleAlert size={12} className={styles.error} aria-hidden />
            )}
            {t(body.valid ? 'properties.valid' : 'properties.invalid')}
          </span>
        }
      />
    </PanelSection>
  );
}

export function RegionProperties({
  region,
  snapshot,
}: {
  region: Region;
  snapshot: DocumentSnapshot;
}) {
  const { t } = useTranslation('panels');
  const format = useFormatter();
  const names = featureNames(snapshot.document.features, t);
  const users = snapshot.document.features.filter((feature) => {
    const params = feature.params;
    return (
      !!params &&
      typeof params === 'object' &&
      !Array.isArray(params) &&
      params.sourceRegion === region.id
    );
  });
  return (
    <PanelSection title={t('properties.regionSection')}>
      <PropertyValue label={t('properties.type')} value={t(`regionKind.${region.kind}`)} />
      <PropertyValue
        label={t('properties.rms')}
        value={region.rms === null ? t('properties.unknown') : format.length(region.rms)}
      />
      <PropertyValue label={t('properties.triangles')} value={format.count(region.faceCount)} />
      <PropertyValue label={t('properties.area')} value={format.area(region.area)} />
      <PropertyValue
        label={t('properties.usedBy')}
        value={
          users.length
            ? format.list(users.map((feature) => names.get(feature.id) ?? feature.id))
            : t('properties.unused')
        }
      />
    </PanelSection>
  );
}
