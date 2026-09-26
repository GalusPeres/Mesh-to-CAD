import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { featureNames, featureView } from '../features/registry';
import { useDocument } from '../state/documentStore';
import { useObjectSelection } from '../state/objectSelectionStore';
import styles from './ObjectProperties.module.css';
import {
  BodyProperties,
  FeatureProperties,
  RegionProperties,
  ScanProperties,
} from './propertySections';
import { treeIcon } from './treeIcons';
import { bodyNames, regionName } from './treeModel';

function Header({ icon: Icon, title }: { icon?: LucideIcon; title: string }) {
  return (
    <header className={styles.header}>
      {Icon && <Icon size={16} aria-hidden />}
      <h2 className={styles.headerTitle} data-testid="properties-title">
        {title}
      </h2>
    </header>
  );
}

function Frame({
  icon,
  title,
  children,
}: {
  icon?: LucideIcon;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className={styles.panel} data-testid="properties-object">
      <Header icon={icon} title={title} />
      <div className={styles.body}>{children}</div>
    </div>
  );
}

/**
 * The properties panel when no tool is open (docs/DESIGN.md 3.4): the selected
 * object's values and state, or the empty state.
 */
export function ObjectProperties() {
  const { t } = useTranslation(['panels', 'common']);
  const selected = useObjectSelection((state) => state.selected[0] ?? null);
  const snapshot = useDocument((state) => state.snapshot);
  const document = snapshot?.document;

  if (snapshot && document?.scan && selected) {
    if (selected.kind === 'scan') {
      return (
        <Frame icon={treeIcon('scan')} title={t('tree.scan')}>
          <ScanProperties scan={document.scan} tolerance={document.settings.tolerance} />
        </Frame>
      );
    }
    if (selected.kind === 'feature') {
      const feature = document.features.find((item) => item.id === selected.id);
      if (feature) {
        return (
          <Frame
            icon={featureView(feature.type)?.icon}
            title={featureNames(document.features, t).get(feature.id) ?? feature.id}
          >
            <FeatureProperties feature={feature} snapshot={snapshot} />
          </Frame>
        );
      }
    }
    if (selected.kind === 'body') {
      const body = snapshot.status.bodies.find((item) => item.id === selected.id);
      if (body) {
        return (
          <Frame
            icon={treeIcon('body')}
            title={bodyNames(snapshot.status, t).get(body.id) ?? body.id}
          >
            <BodyProperties body={body} snapshot={snapshot} />
          </Frame>
        );
      }
    }
    if (selected.kind === 'region') {
      const region = document.regions.items.find((item) => item.id === selected.id);
      if (region) {
        return (
          <Frame icon={treeIcon(`region:${region.kind}`)} title={regionName(region, t)}>
            <RegionProperties region={region} snapshot={snapshot} />
          </Frame>
        );
      }
    }
  }

  return (
    <div className={styles.empty} data-testid="properties-empty">
      <h2 className={styles.title}>{t('common:panels.noSelection')}</h2>
      <p className={styles.hint}>{t('common:panels.noSelectionHint')}</p>
    </div>
  );
}
