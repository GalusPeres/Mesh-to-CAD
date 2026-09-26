import { useTranslation } from 'react-i18next';

import { useFormatter } from '../../i18n/useFormatter';
import { useDocument } from '../../state/documentStore';
import { surfaceStats } from '../../tools/auto-surface/model';
import { PropertyValue } from '../../ui/PropertyRow/PropertyRow';

const KEY = 'features:autoSurface';

/** Surface count and deviation of the committed auto surface, from the rebuild. */
export function AutoSurfaceProperties({ featureId }: { featureId: string }) {
  const { t } = useTranslation();
  const format = useFormatter();
  const status = useDocument((state) => state.snapshot?.status.features[featureId]);
  const feature = useDocument((state) =>
    state.snapshot?.document.features.find((item) => item.id === featureId),
  );
  const stats = surfaceStats(status);
  const params = feature?.params as { detail?: string; smoothing?: string } | undefined;
  return (
    <div data-testid="auto-surface-properties">
      {params?.detail && (
        <PropertyValue label={t(`${KEY}.detail`)} value={t(`${KEY}.details.${params.detail}`)} />
      )}
      {params?.smoothing && (
        <PropertyValue
          label={t(`${KEY}.smoothing`)}
          value={t(`${KEY}.smoothingLevels.${params.smoothing}`)}
        />
      )}
      {stats && (
        <>
          <PropertyValue label={t(`${KEY}.stats.patches`)} value={format.count(stats.patches)} />
          {stats.rms !== null && (
            <PropertyValue label={t(`${KEY}.stats.rms`)} value={format.length(stats.rms)} />
          )}
          {stats.max !== null && (
            <PropertyValue label={t(`${KEY}.stats.max`)} value={format.length(stats.max)} />
          )}
          <PropertyValue
            label={t(`${KEY}.stats.shape`)}
            value={t(`${KEY}.stats.${stats.closed ? 'solid' : 'openSurface'}`)}
          />
        </>
      )}
    </div>
  );
}
