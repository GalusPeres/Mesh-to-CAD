import { useTranslation } from 'react-i18next';

import { useFormatter } from '../../i18n/useFormatter';
import { Button } from '../../ui/Button/Button';
import { RECOGNITION_COLORS } from '../../viewport/palette';
import { type FeatureGroup, featureName } from './model';
import styles from './RecognizePanel.module.css';

const KEY = 'tools:recognize';
const DEGREES = 180 / Math.PI;

interface GroupListProps {
  groups: readonly FeatureGroup[];
  checked: ReadonlySet<number>;
  /** Groups whose top edges stay sharp although the scan shows a rounding. */
  sharp: ReadonlySet<number>;
  hovered: number | null;
  onToggle: (group: number) => void;
  onToggleRounding: (group: number) => void;
  onHover: (group: number | null) => void;
  onAll: (all: boolean) => void;
}

/** The recognised groups: one row each, checked to be built. */
export function GroupList({ groups, checked, sharp, hovered, onAll, ...row }: GroupListProps) {
  const { t } = useTranslation();
  const format = useFormatter();
  if (groups.length === 0) return null;
  const count = groups.reduce((sum, group) => sum + group.indices.length, 0);
  return (
    <>
      <div className={styles.listHeader}>
        <span>{t(`${KEY}.featureCount`, { count, formatted: format.count(count) })}</span>
        <span className={styles.listActions}>
          <Button variant="ghost" data-testid="recognize-all" onClick={() => onAll(true)}>
            {t(`${KEY}.all`)}
          </Button>
          <Button variant="ghost" data-testid="recognize-none" onClick={() => onAll(false)}>
            {t(`${KEY}.none`)}
          </Button>
        </span>
      </div>
      <ul
        className={styles.list}
        data-testid="recognize-groups"
        onMouseLeave={() => row.onHover(null)}
      >
        {groups.map((group) => (
          <GroupRow
            key={group.id}
            group={group}
            checked={checked.has(group.id)}
            rounded={!sharp.has(group.id)}
            hovered={hovered === group.id}
            {...row}
          />
        ))}
      </ul>
    </>
  );
}

interface GroupRowProps {
  group: FeatureGroup;
  checked: boolean;
  rounded: boolean;
  hovered: boolean;
  onToggle: (group: number) => void;
  onToggleRounding: (group: number) => void;
  onHover: (group: number | null) => void;
}

function GroupRow({
  group,
  checked,
  rounded,
  hovered,
  onToggle,
  onToggleRounding,
  onHover,
}: GroupRowProps) {
  const { t } = useTranslation();
  const format = useFormatter();
  const { feature } = group;
  const color = RECOGNITION_COLORS[group.role];
  const amount = format.length(feature.height, { decimals: 2 });
  const details = [
    t(`${KEY}.roles.${group.role}`),
    group.role === 'hole'
      ? t(`${KEY}.through`)
      : t(`${KEY}.${group.role === 'boss' ? 'height' : 'depth'}`, { value: amount }),
    feature.top === 'domed' ? t(`${KEY}.domed`) : null,
    feature.top === 'inclined'
      ? t(`${KEY}.inclined`, { angle: format.number(feature.tilt * DEGREES, 0) })
      : null,
    group.nested ? t(`${KEY}.nested`) : null,
  ].filter(Boolean);
  const name = featureName(feature, t(`${KEY}.shapeNames.${feature.shape}`), format);
  const radius = feature.rounding ?? 0;
  return (
    <li
      className={`${styles.row} ${hovered ? styles.hovered : ''}`}
      data-testid={`recognize-group-${group.id}`}
      onMouseEnter={() => onHover(group.id)}
    >
      <input
        type="checkbox"
        className={styles.box}
        checked={checked}
        aria-label={name}
        onChange={() => onToggle(group.id)}
      />
      <span className={styles.swatch} style={{ background: color }} aria-hidden />
      <span className={styles.text}>
        <span className={styles.name}>
          {group.indices.length > 1 && (
            <span className={styles.count}>{group.indices.length} × </span>
          )}
          {name}
          {radius > 0 && (
            <>
              {' · '}
              <button
                type="button"
                className={`${styles.radius} ${rounded ? '' : styles.radiusOff}`}
                aria-pressed={rounded}
                title={t(`${KEY}.roundTooltip`)}
                data-testid={`recognize-round-${group.id}`}
                onClick={() => onToggleRounding(group.id)}
              >
                R {format.number(radius, 2)}
              </button>
            </>
          )}
        </span>
        <span className={styles.details}>{details.join(' · ')}</span>
      </span>
    </li>
  );
}
