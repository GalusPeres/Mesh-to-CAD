import type { ViewportInteraction } from '../../viewport/api';

/** A running selection mode: its viewport interaction and its gesture state. */
export interface SelectionMode {
  interaction: ViewportInteraction;
  /** A gesture (stroke, lasso, rectangle) is in progress. */
  busy(): boolean;
  /** Abort the running gesture (Esc); what a stroke already painted stays. */
  cancel(): void;
  dispose(): void;
}
