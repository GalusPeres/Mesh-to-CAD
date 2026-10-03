import { Circle, CornerDownRight, Link2, Slash } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Button } from '../../ui/Button/Button';
import { IconButton } from '../../ui/IconButton/IconButton';
import { NumberField } from '../../ui/NumberField/NumberField';
import { PropertyRow } from '../../ui/PropertyRow/PropertyRow';
import type { SketchMode } from './sketchSession';
import type { Vec2 } from './sketchMath';
import styles from './SketchPanel.module.css';

const K = 'sectionSketch';

interface SketchToolbarProps {
  mode: SketchMode;
  onMode: (mode: SketchMode) => void;
  canCloseGap: boolean;
  onCloseGap: () => void;
  circle: { center: Vec2; radius: number };
  onCircle: (circle: { center: Vec2; radius: number }) => void;
  onAddCircle: () => void;
}

/** Drawing tools as icon buttons; the circle tool adds its centre and radius fields. */
export function SketchToolbar(props: SketchToolbarProps) {
  const { mode, onMode, canCloseGap, onCloseGap, circle, onCircle, onAddCircle } = props;
  const { t } = useTranslation('tools');
  const toggle = (next: SketchMode) => () => onMode(mode === next ? 'select' : next);
  const setCenter = (index: 0 | 1, value: number) =>
    onCircle({
      ...circle,
      center: index === 0 ? [value, circle.center[1]] : [circle.center[0], value],
    });
  return (
    <>
      <div className={styles.toolbar} role="toolbar" aria-label={t(`${K}.draw`)}>
        <IconButton
          icon={CornerDownRight}
          label={t(`${K}.actions.corner`)}
          shortcut="K"
          pressed={mode === 'corner'}
          onClick={toggle('corner')}
        />
        <IconButton
          icon={Slash}
          label={t(`${K}.actions.line`)}
          shortcut="L"
          pressed={mode === 'line'}
          onClick={toggle('line')}
        />
        <IconButton
          icon={Circle}
          label={t(`${K}.actions.circle`)}
          shortcut="C"
          pressed={mode === 'circle'}
          onClick={toggle('circle')}
        />
        <IconButton
          icon={Link2}
          label={t(`${K}.actions.closeGap`)}
          disabled={!canCloseGap}
          onClick={onCloseGap}
        />
      </div>
      {mode === 'circle' && (
        <>
          {([0, 1] as const).map((index) => (
            <PropertyRow
              key={index}
              label={t(`${K}.field.${index ? 'centerY' : 'centerX'}`)}
              htmlFor={`sketch-circle-${index}`}
            >
              <NumberField
                id={`sketch-circle-${index}`}
                value={circle.center[index]}
                onCommit={(value) => setCenter(index, value)}
              />
            </PropertyRow>
          ))}
          <PropertyRow label={t(`${K}.field.radius`)} htmlFor="sketch-circle-radius">
            <NumberField
              id="sketch-circle-radius"
              value={circle.radius}
              min={0.01}
              onCommit={(radius) => onCircle({ ...circle, radius })}
            />
          </PropertyRow>
          <Button onClick={onAddCircle}>{t(`${K}.actions.addCircle`)}</Button>
        </>
      )}
    </>
  );
}
