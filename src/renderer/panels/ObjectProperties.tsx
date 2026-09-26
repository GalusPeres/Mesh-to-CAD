import { useTranslation } from 'react-i18next';

import { useFormatter } from '../i18n/useFormatter';
import { useDocument } from '../state/documentStore';
import { useObjectSelection } from '../state/objectSelectionStore';
import { PanelSection } from '../ui/PanelSection/PanelSection';
import { PropertyValue } from '../ui/PropertyRow/PropertyRow';
import styles from './ObjectProperties.module.css';

/** Properties of the selected object, or the empty state when nothing is selected. */
export function ObjectProperties() {
  const { t } = useTranslation(['panels', 'common']);
  const format = useFormatter();
  const selected = useObjectSelection((state) => state.selected[0] ?? null);
  const scan = useDocument((state) => state.snapshot?.document.scan ?? null);

  if (selected?.kind === 'scan' && scan) {
    return (
      <PanelSection title={t('tree.scan')}>
        <PropertyValue label={t('properties.file')} value={scan.source.fileName} />
        <PropertyValue label={t('properties.triangles')} value={format.count(scan.faceCount)} />
        <PropertyValue label={t('properties.vertices')} value={format.count(scan.vertexCount)} />
        {scan.noise !== null && (
          <PropertyValue label={t('properties.noise')} value={format.length(scan.noise)} />
        )}
      </PanelSection>
    );
  }
  return (
    <div className={styles.empty}>
      <h2 className={styles.title}>{t('common:panels.noSelection')}</h2>
      <p className={styles.hint}>{t('common:panels.noSelectionHint')}</p>
    </div>
  );
}
