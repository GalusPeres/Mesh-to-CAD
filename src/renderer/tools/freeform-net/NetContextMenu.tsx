import {
  ArrowUpToLine,
  Combine,
  Crosshair,
  Eye,
  Focus,
  Grid2x2Plus,
  Magnet,
  Pin,
  PinOff,
  RectangleHorizontal,
  Spline,
  SplitSquareVertical,
  SquarePlus,
  Trash2,
  Waves,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useFormatter } from '../../i18n/useFormatter';
import { MenuAt, MenuItem, MenuSeparator, MenuSub } from '../../ui/Menu/Menu';
import type { NetEditor, NetEditorState } from './netEditor';
import type { NetMenuRequest } from './netInteraction';
import { referenceCount, usePushReferences } from './netReferences';
import { DRAG_STRENGTHS } from './NetPointOptions';

const KEY = 'tools:freeformNet.menu';

interface NetContextMenuProps {
  editor: NetEditor;
  state: NetEditorState;
  request: NetMenuRequest | null;
  onClose: () => void;
}

/** Window position of a point given relative to the viewport area. */
function inWindow(at: { x: number; y: number }): { x: number; y: number } {
  const area = document.querySelector('main')?.getBoundingClientRect();
  return { x: (area?.left ?? 0) + at.x, y: (area?.top ?? 0) + at.y };
}

/**
 * The right-click menu of the freeform net, as QuickSurface's: what can be done with the
 * edge under the pointer and the chosen edges or points, and on the whole net.
 */
export function NetContextMenu({ editor, state, request, onClose }: NetContextMenuProps) {
  const { t } = useTranslation();
  const format = useFormatter();
  const references = usePushReferences();
  const edge = request?.edge ?? null;
  const chosen = state.selected + state.chosenEdges > 0;
  const busy = state.job !== null;
  const item = (name: string) => t(`${KEY}.${name}`);
  return (
    <MenuAt at={request ? inWindow(request.at) : null} onClose={onClose}>
      {edge && (
        <>
          <MenuItem
            label={item('split')}
            icon={SplitSquareVertical}
            shortcut="S"
            disabled={busy}
            onSelect={() => void editor.build.edits.split(edge)}
          />
          <MenuItem
            label={item('chain')}
            icon={Spline}
            onSelect={() => editor.build.chooseEdges(editor.build.chainOf(edge), 'replace')}
          />
          <MenuSeparator />
        </>
      )}
      <MenuItem
        label={item('bridge')}
        icon={Combine}
        disabled={busy || !editor.build.edits.bridgeable()}
        testId="freeform-net-bridge"
        onSelect={() => void editor.build.edits.bridge()}
      />
      <MenuItem
        label={item('smooth')}
        icon={Waves}
        shortcut="Q"
        disabled={busy || !chosen}
        onSelect={() => void editor.shape.smoothChosen()}
      />
      {state.selected > state.chosenPinned && (
        <MenuItem
          label={item('pin')}
          icon={Pin}
          disabled={busy}
          testId="freeform-net-menu-pin"
          onSelect={() => editor.pinChosen(true)}
        />
      )}
      {state.chosenPinned > 0 && (
        <MenuItem
          label={item('unpin')}
          icon={PinOff}
          disabled={busy}
          testId="freeform-net-menu-unpin"
          onSelect={() => editor.pinChosen(false)}
        />
      )}
      <MenuItem
        label={item('delete')}
        icon={Trash2}
        shortcut={t(`${KEY}.deleteKey`)}
        disabled={busy || !chosen}
        onSelect={() => void editor.build.edits.deleteChosen()}
      />
      <MenuSeparator />
      <MenuItem
        label={item(state.selected > 0 ? 'snapChosen' : 'snapAll')}
        icon={Magnet}
        disabled={busy || !state.hasNet}
        onSelect={() => void editor.shape.fit(false)}
      />
      <MenuItem
        label={item('push')}
        icon={ArrowUpToLine}
        disabled={busy || !state.hasNet || referenceCount(references) === 0}
        testId="freeform-net-menu-push"
        onSelect={() => void editor.shape.pushPast(references)}
      />
      <MenuItem
        label={item('refine')}
        icon={Grid2x2Plus}
        disabled={busy || !state.hasNet}
        testId="freeform-net-refine"
        onSelect={() => void editor.build.edits.refine()}
      />
      <MenuItem
        label={item('snap')}
        icon={Crosshair}
        checked={state.snap}
        onSelect={() => editor.setDragOptions({ snap: !state.snap })}
      />
      <MenuItem
        label={item('neighbours')}
        icon={Focus}
        checked={state.keepNeighbours}
        onSelect={() => editor.setDragOptions({ keepNeighbours: !state.keepNeighbours })}
      />
      <MenuSub label={item('strength')}>
        {DRAG_STRENGTHS.map((strength) => (
          <MenuItem
            key={strength}
            label={`${format.number(strength * 100, 0)} %`}
            checked={state.strength === strength}
            onSelect={() => editor.setDragOptions({ strength })}
          />
        ))}
      </MenuSub>
      <MenuItem
        label={item('net')}
        icon={Eye}
        shortcut={t(`${KEY}.space`)}
        checked={state.netVisible}
        onSelect={() => editor.setNetVisible(!state.netVisible)}
      />
      <MenuSeparator />
      <MenuItem
        label={item('face')}
        icon={SquarePlus}
        disabled={busy}
        onSelect={() => editor.build.setFacing(true, 'quad')}
      />
      <MenuItem
        label={item('rectangle')}
        icon={RectangleHorizontal}
        disabled={busy}
        onSelect={() => editor.build.setFacing(true, 'rectangle')}
      />
    </MenuAt>
  );
}
