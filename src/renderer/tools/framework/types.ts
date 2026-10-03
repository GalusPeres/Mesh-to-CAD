import type { LucideIcon } from 'lucide-react';
import type { ComponentType } from 'react';

import type { FeatureTypeId } from '@shared/protocol/generated/index';
import type { DocumentSnapshot } from '@shared/protocol/generated/document-snapshot';

import type { Shortcut } from '../../app/commands/types';
import type { StageId } from '../../state/toolStore';

/**
 * - `panel`: opens in the properties panel with OK / Abbrechen (fit, extrude, ...).
 * - `selection`: a selection mode (brush, smart select, lasso, rectangle). It stays
 *   active alongside an open panel tool, so inputs can be selected while a panel is open.
 * - `action`: runs once (reset alignment, delete selected triangles).
 */
export type ToolKind = 'panel' | 'selection' | 'action';

export type ToolGroup =
  | 'selection'
  | 'mesh'
  | 'analysis'
  | 'regions'
  | 'align'
  | 'fit'
  | 'reference'
  | 'sketch'
  | 'solid'
  | 'freeform'
  | 'inspect'
  | 'export';

export type Availability = { enabled: true } | { enabled: false; reasonKey: string };

export interface ToolContext {
  snapshot: DocumentSnapshot | null;
}

export interface ToolPanelProps {
  /** Data the tool was opened with (for example an import report). */
  activation: unknown;
  /** The feature being edited, when opened from the project tree. */
  editTarget: string | null;
  close: () => void;
}

export interface ToolDefinition {
  /** kebab-case, equals the folder name; strings live under `tools:<camelCaseId>`. */
  id: string;
  kind: ToolKind;
  /**
   * `planned` tools exist as placeholders. Development builds show them disabled;
   * release builds hide them.
   */
  status: 'ready' | 'planned';
  /** Stages whose tool row shows the tool; empty for tools opened another way (import). */
  stages: readonly StageId[];
  group: ToolGroup;
  icon: LucideIcon;
  /** Primary tools show their label in the tool row. */
  primary?: boolean;
  shortcut?: Shortcut;
  availability?(context: ToolContext): Availability;
  Panel?: ComponentType<ToolPanelProps>;
  run?(): void | Promise<void>;
  /** Double-clicking a feature of these types in the tree opens this tool to edit it. */
  edits?: readonly FeatureTypeId[];
  /** Ask before discarding a changed draft (sketches, fillet edge picks). */
  confirmDiscard?: boolean;
  /**
   * Switching to another tool commits the draft (through the keeper the panel
   * registers with `setDraftKeeper`) instead of asking to discard it: work built by
   * hand is never lost by a change of tool. Cancel still discards.
   */
  keepDraftOnLeave?: boolean;
}
