// How points behave when dragged: snapped to the scan, pinned (they stay), "Don't move
// neighbours" and the drag strength (QuickSurface, Free Form Basics). Icon toggles with
// tooltips and one segmented control, so the panel stays short.

import { Crosshair, Focus, Pin, PinOff, Snail } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useFormatter } from '../../i18n/useFormatter';
import { IconButton } from '../../ui/IconButton/IconButton';
import { SegmentedControl } from '../../ui/SegmentedControl/SegmentedControl';
import { Tooltip } from '../../ui/Tooltip/Tooltip';
import styles from './FreeformNetPanel.module.css';
import type { NetEditor, NetEditorState } from './netEditor';

const KEY = 'tools:freeformNet';

/** Shares of the pointer's movement a dragged point follows. */
export const DRAG_STRENGTHS = [1, 0.5, 0.25, 0.1] as const;

interface OptionsProps {
  editor: NetEditor;
  state: NetEditorState;
}

/** Snapping, pinning the chosen points and the neighbour toggle (icons in a toolbar). */
export function PointOptions({ editor, state }: OptionsProps) {
  const { t } = useTranslation();
  const tool = (name: string) => ({
    label: t(`${KEY}.tools.${name}.label`),
    description: t(`${KEY}.tools.${name}.description`),
  });
  const unpin = state.selected > 0 && state.chosenPinned === state.selected;
  return (
    <>
      <IconButton
        icon={Crosshair}
        {...tool('snap')}
        pressed={state.snap}
        data-testid="freeform-net-snap"
        onClick={() => editor.setDragOptions({ snap: !state.snap })}
      />
      <IconButton
        icon={unpin ? PinOff : Pin}
        {...tool(unpin ? 'unpin' : 'pin')}
        disabled={state.job !== null || state.selected === 0}
        data-testid="freeform-net-pin"
        onClick={() => editor.pinChosen(!unpin)}
      />
      <IconButton
        icon={Focus}
        {...tool('neighbours')}
        pressed={state.keepNeighbours}
        data-testid="freeform-net-neighbours"
        onClick={() => editor.setDragOptions({ keepNeighbours: !state.keepNeighbours })}
      />
    </>
  );
}

/** How much of the pointer's movement dragged points follow, for fine adjustments. */
export function StrengthOptions({ editor, state }: OptionsProps) {
  const { t } = useTranslation();
  const format = useFormatter();
  const label = t(`${KEY}.tools.strength.label`);
  return (
    <div className={styles.row}>
      <Tooltip label={label} description={t(`${KEY}.tools.strength.description`)}>
        <span className={styles.icon} aria-hidden>
          <Snail size={16} />
        </span>
      </Tooltip>
      <SegmentedControl<string>
        value={String(state.strength)}
        ariaLabel={label}
        segments={DRAG_STRENGTHS.map((value) => ({
          value: String(value),
          label: `${format.number(value * 100, 0)} %`,
        }))}
        onChange={(value) => editor.setDragOptions({ strength: Number(value) })}
      />
    </div>
  );
}
