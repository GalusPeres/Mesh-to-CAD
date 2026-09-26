import { useTranslation } from 'react-i18next';

import type { FeatureStatus } from '@shared/protocol/generated/document-results';

import { featureNames, featureView } from '../features/registry';
import { useFormatter } from '../i18n/useFormatter';
import { useDocument } from '../state/documentStore';
import { useObjectSelection } from '../state/objectSelectionStore';
import { PanelSection } from '../ui/PanelSection/PanelSection';
import { PropertyValue } from '../ui/PropertyRow/PropertyRow';
import styles from './ObjectProperties.module.css';
import { regionName } from './treeModel';

function issueText(status: FeatureStatus, t: ReturnType<typeof useTranslation>['t']): string[] {
  const texts = status.issues.map((issue) => t(`issues:${issue.code}`, issue.params));
  if (status.error) texts.unshift(t(`errors:${status.error.code}`, status.error.params));
  return texts;
}

/** Properties of the selected object, or the empty state when nothing is selected. */
export function ObjectProperties() {
  const { t } = useTranslation(['panels', 'common', 'features']);
  const format = useFormatter();
  const selected = useObjectSelection((state) => state.selected[0] ?? null);
  const snapshot = useDocument((state) => state.snapshot);
  const document = snapshot?.document ?? null;

  if (selected?.kind === 'scan' && document?.scan) {
    const scan = document.scan;
    return (
      <PanelSection title={t('tree.scan')}>
        <PropertyValue label={t('properties.file')} value={scan.source.fileName} />
        <PropertyValue label={t('properties.triangles')} value={format.count(scan.faceCount)} />
        <PropertyValue label={t('properties.vertices')} value={format.count(scan.vertexCount)} />
        <PropertyValue label={t('properties.unit')} value={scan.source.importUnit} />
        {scan.noise !== null && (
          <PropertyValue label={t('properties.noise')} value={format.length(scan.noise)} />
        )}
      </PanelSection>
    );
  }

  if (selected?.kind === 'feature' && document && snapshot) {
    const feature = document.features.find((item) => item.id === selected.id);
    if (feature) {
      const view = featureView(feature.type);
      const status = snapshot.status.features[feature.id];
      const state = feature.suppressed ? 'suppressed' : (status?.state ?? 'ok');
      const summary = view?.summary?.(feature.params as never, format, t);
      const Properties = view?.Properties;
      const notes = status ? issueText(status, t) : [];
      return (
        <PanelSection title={featureNames(document.features, t).get(feature.id) ?? feature.id}>
          <PropertyValue label={t('properties.type')} value={t(`features:${feature.type}.name`)} />
          {summary && <PropertyValue label={t('properties.summary')} value={summary} />}
          <PropertyValue
            label={t('properties.status')}
            value={<span data-testid="properties-feature-state">{t(`state.${state}`)}</span>}
          />
          {notes.length > 0 && (
            <ul className={styles.issues} aria-label={t('properties.issues')}>
              {notes.map((text) => (
                <li key={text}>{text}</li>
              ))}
            </ul>
          )}
          {Properties && <Properties featureId={feature.id} />}
        </PanelSection>
      );
    }
  }

  if (selected?.kind === 'body' && snapshot) {
    const index = snapshot.status.bodies.findIndex((body) => body.id === selected.id);
    const body = snapshot.status.bodies[index];
    if (body) {
      return (
        <PanelSection title={t('tree.body', { number: index + 1 })}>
          <PropertyValue label={t('properties.volume')} value={format.volume(body.volume)} />
          <PropertyValue label={t('properties.area')} value={format.area(body.area)} />
          <PropertyValue label={t('properties.solids')} value={format.count(body.solids)} />
          <PropertyValue
            label={t('properties.validity')}
            value={t(body.valid ? 'properties.valid' : 'properties.invalid')}
          />
        </PanelSection>
      );
    }
  }

  if (selected?.kind === 'region' && document) {
    const region = document.regions.items.find((item) => item.id === selected.id);
    if (region) {
      return (
        <PanelSection title={regionName(region, t)}>
          <PropertyValue label={t('properties.type')} value={t(`regionKind.${region.kind}`)} />
          {region.rms !== null && (
            <PropertyValue label={t('properties.rms')} value={format.length(region.rms)} />
          )}
          <PropertyValue label={t('properties.faces')} value={format.count(region.faceCount)} />
          <PropertyValue label={t('properties.area')} value={format.area(region.area)} />
        </PanelSection>
      );
    }
  }

  return (
    <div className={styles.empty}>
      <h2 className={styles.title}>{t('common:panels.noSelection')}</h2>
      <p className={styles.hint}>{t('common:panels.noSelectionHint')}</p>
    </div>
  );
}
