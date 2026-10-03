// The view state stored in a project's ui.json: the stage and how the scene is shown.

import { STAGES, type StageId, setStage, toolStore } from '../state/toolStore';
import {
  type DisplayMode,
  type Projection,
  type Visibility,
  setDisplayMode,
  setProjection,
  setVisibility,
  viewStore,
} from '../state/viewStore';

export interface ProjectUiState {
  stage: StageId;
  projection: Projection;
  displayMode: DisplayMode;
  visibility: Visibility;
}

const PROJECTIONS: readonly Projection[] = ['orthographic', 'perspective'];
const DISPLAY_MODES: readonly DisplayMode[] = [
  'shaded',
  'shadedEdges',
  'flat',
  'xray',
  'regions',
  'deviation',
  'covered',
];
const VISIBILITIES: readonly Visibility[] = ['scan', 'bodies', 'both'];

export function collectUiState(): ProjectUiState {
  const view = viewStore.getState();
  return {
    stage: toolStore.getState().stage,
    projection: view.projection,
    displayMode: view.displayMode,
    visibility: view.visibility,
  };
}

/**
 * Restore what a project file stored. The file comes from outside, so every
 * value is checked; unknown or missing values keep the current state.
 */
export function applyUiState(stored: unknown): void {
  if (typeof stored !== 'object' || stored === null) return;
  const state = stored as Record<string, unknown>;
  const pick = <T extends string>(value: unknown, allowed: readonly T[]): T | undefined =>
    allowed.find((candidate) => candidate === value);
  const stage = pick(state.stage, STAGES);
  const projection = pick(state.projection, PROJECTIONS);
  const displayMode = pick(state.displayMode, DISPLAY_MODES);
  const visibility = pick(state.visibility, VISIBILITIES);
  if (stage) setStage(stage);
  if (projection) setProjection(projection);
  if (displayMode) setDisplayMode(displayMode);
  if (visibility) setVisibility(visibility);
}
