// Requests of the local automation interface (docs/AUTOMATION.md) that the main
// process forwards to the renderer: things only the user interface owns.

export type AutomationAction =
  | { type: 'state' }
  | { type: 'listCommands' }
  | { type: 'runCommand'; id: string }
  | { type: 'selectFaces'; faces: readonly number[] }
  /** Click a control by its `data-testid`, or else a button by its label or aria-label. */
  | { type: 'click'; target: string }
  /** Press a key (`Escape`, `Enter`, `k`, ...) like the user, with optional modifiers. */
  | { type: 'key'; key: string; ctrl?: boolean; shift?: boolean; alt?: boolean }
  /**
   * A pointer event on the 3D view at (x, y), CSS pixels from its top left corner:
   * press, move or release, with the button (0 left) and modifiers.
   */
  | {
      type: 'pointer';
      kind: 'down' | 'move' | 'up';
      x: number;
      y: number;
      button?: number;
      ctrl?: boolean;
      shift?: boolean;
      alt?: boolean;
    }
  /** Where part-coordinate points appear in the 3D view (null when behind the camera). */
  | { type: 'project'; points: readonly (readonly [number, number, number])[] }
  /** What is under a point of the 3D view: scan, body, edge or item, with its 3D point. */
  | { type: 'pick'; x: number; y: number };

export interface AutomationRequest {
  requestId: number;
  action: AutomationAction;
}

export interface AutomationResponse {
  requestId: number;
  ok: boolean;
  result?: unknown;
  error?: string;
}
