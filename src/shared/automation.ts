// Requests of the local automation interface (docs/AUTOMATION.md) that the main
// process forwards to the renderer: things only the user interface owns.

export type AutomationAction =
  | { type: 'state' }
  | { type: 'listCommands' }
  | { type: 'runCommand'; id: string }
  | { type: 'selectFaces'; faces: readonly number[] };

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
