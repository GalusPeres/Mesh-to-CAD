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
  | { type: 'key'; key: string; ctrl?: boolean; shift?: boolean; alt?: boolean };

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
