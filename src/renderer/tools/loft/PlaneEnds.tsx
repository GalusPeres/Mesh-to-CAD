import { useTranslation } from 'react-i18next';

import { PropertyRow } from '../../ui/PropertyRow/PropertyRow';
import { Select } from '../../ui/Select/Select';
import { ORIGIN_PLANES } from '../extrude/solid/model';

const KEY = 'tools:loft';
/** Select value for an end without a plane. */
const NONE = '';

export interface PlaneEndsProps {
  /** Plane features the ends may reach, in history order. */
  planes: readonly string[];
  startPlane: string | null;
  endPlane: string | null;
  label: (id: string) => string;
  onStartPlane: (plane: string | null) => void;
  onEndPlane: (plane: string | null) => void;
}

/** "Bis Ebene" for both ends of a loft: the walls continue straight up to the plane. */
export function PlaneEnds({
  planes,
  startPlane,
  endPlane,
  label,
  onStartPlane,
  onEndPlane,
}: PlaneEndsProps) {
  const { t } = useTranslation();
  const options = [
    { value: NONE, label: t(`${KEY}.noPlane`) },
    ...[...ORIGIN_PLANES, ...planes].map((id) => ({ value: id, label: label(id) })),
  ];
  const rows = [
    { role: 'startPlane', value: startPlane, onChange: onStartPlane },
    { role: 'endPlane', value: endPlane, onChange: onEndPlane },
  ] as const;
  return (
    <>
      {rows.map(({ role, value, onChange }) => (
        <PropertyRow key={role} label={t(`${KEY}.${role}`)}>
          <Select<string>
            value={value ?? NONE}
            ariaLabel={t(`${KEY}.${role}`)}
            testId={`loft-${role}`}
            options={options}
            onChange={(id) => onChange(id === NONE ? null : id)}
          />
        </PropertyRow>
      ))}
    </>
  );
}
