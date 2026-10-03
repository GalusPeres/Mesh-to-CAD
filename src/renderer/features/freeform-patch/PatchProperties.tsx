import { useTranslation } from 'react-i18next';

import { useFormatter } from '../../i18n/useFormatter';
import { useDocument } from '../../state/documentStore';
import { PropertyValue } from '../../ui/PropertyRow/PropertyRow';
import { statValue } from './statusOf';

const KEY = 'features:freeformPatch';
const LENGTHS = ['noise', 'rms', 'max'] as const;

/** Quality of the committed patch: the result block of the tool, from the rebuild. */
export function PatchProperties({ featureId }: { featureId: string }) {
  const { t } = useTranslation();
  const format = useFormatter();
  const status = useDocument((state) => state.snapshot?.status.features[featureId]);
  const value = (key: string) => statValue(status, `freeform.stats.${key}`);
  const within = value('withinTolerance');
  const faces = value('faces');
  const spansU = value('spansU');
  const spansV = value('spansV');
  const spread = value('normalSpreadDeg');
  return (
    <div data-testid="freeform-patch-properties">
      {LENGTHS.map((key) => {
        const number = value(key);
        return number === null ? null : (
          <PropertyValue key={key} label={t(`${KEY}.stats.${key}`)} value={format.length(number)} />
        );
      })}
      {within !== null && (
        <PropertyValue label={t(`${KEY}.stats.withinTolerance`)} value={format.percent(within)} />
      )}
      {faces !== null && (
        <PropertyValue label={t(`${KEY}.stats.faces`)} value={format.count(faces)} />
      )}
      {spansU !== null && spansV !== null && (
        <PropertyValue
          label={t(`${KEY}.stats.spans`)}
          value={t(`${KEY}.spansValue`, { u: spansU, v: spansV })}
        />
      )}
      {spread !== null && (
        <PropertyValue label={t(`${KEY}.stats.normalSpread`)} value={format.angle(spread)} />
      )}
    </div>
  );
}
