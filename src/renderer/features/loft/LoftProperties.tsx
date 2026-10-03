import { useTranslation } from 'react-i18next';

import { useFormatter } from '../../i18n/useFormatter';
import { useDocument } from '../../state/documentStore';
import { PropertyValue } from '../../ui/PropertyRow/PropertyRow';
import { statValue } from '../freeform-patch/statusOf';

const KEY = 'features:loft';

/** Sections of the committed loft and how closely they follow the scan. */
export function LoftProperties({ featureId }: { featureId: string }) {
  const { t } = useTranslation();
  const format = useFormatter();
  const status = useDocument((state) => state.snapshot?.status.features[featureId]);
  const sections = statValue(status, 'freeform.stats.sections');
  const rms = statValue(status, 'freeform.stats.sectionRms');
  const max = statValue(status, 'freeform.stats.sectionMax');
  return (
    <div data-testid="loft-properties">
      {sections !== null && (
        <PropertyValue label={t(`${KEY}.stats.sections`)} value={format.count(sections)} />
      )}
      {rms !== null && (
        <PropertyValue label={t(`${KEY}.stats.sectionRms`)} value={format.length(rms)} />
      )}
      {max !== null && (
        <PropertyValue label={t(`${KEY}.stats.sectionMax`)} value={format.length(max)} />
      )}
    </div>
  );
}
