// What the freeform-net tool tells automation clients (docs/AUTOMATION.md, `toolInfo`):
// the net's counts and border edges on screen, the chosen and pinned points with their
// surface positions, and the panel state, so an assistant can grab and check them.

import type { ScreenPoint, Vec3 } from '../../viewport/api';
import type { Net } from './netModel';
import type { NetEditorState } from './netState';

interface PointInfo {
  control: number;
  at: Vec3;
  screen: ScreenPoint | null;
}

export interface NetAutomationSource {
  tool: string;
  net: Net | null;
  state: NetEditorState;
  border: () => unknown;
  chosen: ReadonlySet<number>;
  pinned: ReadonlySet<number>;
  limitPoint: (control: number) => Vec3;
  screenOf: (control: number) => ScreenPoint | null;
}

/** At most this many chosen points are listed (Ctrl+A chooses all of them). */
const LISTED_POINTS = 5000;

export function netAutomationInfo(source: NetAutomationSource): unknown {
  const { net, state, tool } = source;
  if (!net || !state.hasNet) return { tool, net: null, state };
  const describe = (controls: ReadonlySet<number>): PointInfo[] =>
    [...controls].slice(0, LISTED_POINTS).map((control) => ({
      control,
      at: source.limitPoint(control),
      screen: source.screenOf(control),
    }));
  return {
    tool,
    quads: net.quads.length / 4,
    points: net.vertices.length / 3,
    border: source.border(),
    chosen: describe(source.chosen),
    pinned: describe(source.pinned),
    state,
  };
}
