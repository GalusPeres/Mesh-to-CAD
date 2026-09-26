import { useTranslation } from 'react-i18next';

import { useTools } from '../state/toolStore';
import { Button } from '../ui/Button/Button';
import { Checkbox } from '../ui/Checkbox/Checkbox';
import { NumberField } from '../ui/NumberField/NumberField';
import { SegmentedControl } from '../ui/SegmentedControl/SegmentedControl';
import { useGesture } from './gestureStore';
import { isSelectionModeId } from './selectionRuntime';
import {
  BRUSH_RADIUS,
  SMART_TOLERANCE,
  type SmartMode,
  setSelectionOptions,
  useSelectionOptions,
} from './selectionOptions';
import styles from './SelectionLayer.module.css';

function BrushOptions() {
  const { t } = useTranslation('selection');
  const radius = useSelectionOptions((options) => options.brushRadius);
  const visibleOnly = useSelectionOptions((options) => options.visibleOnly);
  return (
    <>
      <label className={styles.option}>
        <span className={styles.optionLabel}>{t('options.brushSize')}</span>
        <span className={styles.field}>
          <NumberField
            kind="count"
            unit={t('options.pixels')}
            min={BRUSH_RADIUS.min}
            max={BRUSH_RADIUS.max}
            value={radius}
            ariaLabel={t('options.brushSize')}
            onCommit={(value) => setSelectionOptions({ brushRadius: Math.round(value) })}
          />
        </span>
      </label>
      <Checkbox
        checked={visibleOnly}
        label={t('options.visibleOnly')}
        testId="selection-visible-only"
        onChange={(checked) => setSelectionOptions({ visibleOnly: checked })}
      />
    </>
  );
}

function SmartOptions() {
  const { t } = useTranslation('selection');
  const mode = useSelectionOptions((options) => options.smartMode);
  const tolerance = useSelectionOptions((options) => options.smartTolerance);
  const used = useGesture((state) => state.smartPreview?.tolerance ?? null);
  return (
    <>
      <SegmentedControl<SmartMode>
        value={mode}
        ariaLabel={t('options.smartMode')}
        segments={[
          { value: 'primitive', label: t('options.modePrimitive') },
          { value: 'smooth', label: t('options.modeSmooth') },
        ]}
        onChange={(value) => setSelectionOptions({ smartMode: value })}
      />
      <label className={styles.option}>
        <span className={styles.optionLabel}>{t('options.tolerance')}</span>
        <span className={styles.field}>
          <NumberField
            kind="length"
            min={SMART_TOLERANCE.min}
            max={SMART_TOLERANCE.max}
            step={0.01}
            value={tolerance ?? used}
            computed={tolerance === null}
            ariaLabel={t('options.tolerance')}
            onCommit={(value) => setSelectionOptions({ smartTolerance: value })}
          />
        </span>
      </label>
      {tolerance !== null && (
        <Button variant="ghost" onClick={() => setSelectionOptions({ smartTolerance: null })}>
          {t('options.automatic')}
        </Button>
      )}
    </>
  );
}

function ShapeOptions() {
  const { t } = useTranslation('selection');
  const throughPart = useSelectionOptions((options) => options.throughPart);
  return (
    <Checkbox
      checked={throughPart}
      label={t('options.throughPart')}
      testId="selection-through-part"
      onChange={(checked) => setSelectionOptions({ throughPart: checked })}
    />
  );
}

/**
 * Options of the active selection mode (docs/DESIGN.md 3.2, 5.4): brush size and
 * Nur sichtbare, smart-select mode and tolerance, Durch das Teil.
 */
export function SelectionOptionsBar() {
  const { t } = useTranslation('selection');
  const mode = useTools((state) => state.selectionMode);
  if (!isSelectionModeId(mode)) return null;
  return (
    <div
      className={styles.options}
      role="toolbar"
      aria-label={t('options.title')}
      data-testid="selection-options"
    >
      {mode === 'select-brush' && <BrushOptions />}
      {mode === 'select-smart' && <SmartOptions />}
      {(mode === 'select-lasso' || mode === 'select-rectangle') && <ShapeOptions />}
    </div>
  );
}
