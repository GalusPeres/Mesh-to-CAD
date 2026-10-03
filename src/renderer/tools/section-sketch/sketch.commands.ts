// Drawing commands of sketch mode (DESIGN.md 7.2). They exist only while a sketch
// is open; the viewport keys K, L and C resolve to them before the viewport scope.

import { Circle, CornerDownRight, Link2, Slash, Trash2 } from 'lucide-react';

import type { AppCommand } from '../../app/commands/types';
import { type SketchMode, sketchActions, sketchSession } from './sketchSession';

const active = () => sketchSession.getState().active;

function modeCommand(
  id: string,
  mode: SketchMode,
  key: string,
  icon: AppCommand['icon'],
): AppCommand {
  return {
    id: `sketch.${id}`,
    label: `tools:sectionSketch.actions.${id}`,
    icon,
    shortcuts: [{ key }],
    scope: 'sketch',
    isEnabled: active,
    run: () => sketchActions()?.setMode(mode),
  };
}

export const commands: readonly AppCommand[] = [
  modeCommand('corner', 'corner', 'K', CornerDownRight),
  modeCommand('line', 'line', 'L', Slash),
  modeCommand('circle', 'circle', 'C', Circle),
  {
    id: 'sketch.closeGap',
    label: 'tools:sectionSketch.actions.closeGap',
    icon: Link2,
    scope: 'sketch',
    isEnabled: () => active() && !(sketchSession.getState().profile?.closed ?? true),
    run: () => sketchActions()?.closeGap(),
  },
  {
    id: 'sketch.delete',
    label: 'tools:sectionSketch.actions.delete',
    icon: Trash2,
    shortcuts: [{ key: 'Delete' }],
    scope: 'sketch',
    isEnabled: active,
    run: () => sketchActions()?.deleteSelected(),
  },
];
