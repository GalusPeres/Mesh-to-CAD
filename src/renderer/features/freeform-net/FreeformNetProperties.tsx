import { useTranslation } from 'react-i18next';

import { useFormatter } from '../../i18n/useFormatter';
import { useDocument } from '../../state/documentStore';
import { PropertyValue } from '../../ui/PropertyRow/PropertyRow';
import { statValue } from '../freeform-patch/statusOf';

const KEY = 'features:freeformNet';

/** Face count, deviation and result of the committed freeform net, from the rebuild. */
export function FreeformNetProperties({ featureId }: { featureId: string }) {
  const { t } = useTranslation();
  const format = useFormatter();
  const status = useDocument((state) => state.snapshot?.status.features[featureId]);
  const patches = statValue(status, 'patches');
  if (patches === null) return null;
  const rms = statValue(status, 'deviationRms');
  const p95 = statValue(status, 'deviationP95');
  const max = statValue(status, 'deviationMax');
  const closed = statValue(status, 'closed') === 1;
  return (
    <div data-testid="freeform-net-properties">
      <PropertyValue label={t(`${KEY}.stats.patches`)} value={format.count(patches)} />
      {rms !== null && <PropertyValue label={t(`${KEY}.stats.rms`)} value={format.length(rms)} />}
      {p95 !== null && <PropertyValue label={t(`${KEY}.stats.p95`)} value={format.length(p95)} />}
      {max !== null && <PropertyValue label={t(`${KEY}.stats.max`)} value={format.length(max)} />}
      <PropertyValue
        label={t(`${KEY}.stats.shape`)}
        value={t(`${KEY}.stats.${closed ? 'solid' : 'openSurface'}`)}
      />
    </div>
  );
}
