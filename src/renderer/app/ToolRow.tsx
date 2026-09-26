import { Redo2, Undo2 } from 'lucide-react';
import { Fragment } from 'react';
import { useTranslation } from 'react-i18next';

import { useDocument } from '../state/documentStore';
import { entryToRedo, entryToUndo, useHistory } from '../state/historyStore';
import { exclusiveJobRunning, useJobs } from '../state/jobStore';
import { useTools } from '../state/toolStore';
import { toolKey, toolsForStage } from '../tools/framework/registry';
import { openTool, toolAvailability } from '../tools/framework/toolActions';
import type { ToolDefinition, ToolGroup } from '../tools/framework/types';
import { IconButton } from '../ui/IconButton/IconButton';
import { ToolButton } from '../ui/ToolButton/ToolButton';
import { ViewToolGroup } from '../viewport/ViewToolGroup';
import { formatShortcut } from './commands/keymap';
import { redo, undo } from './edit.commands';
import styles from './ToolRow.module.css';

const GROUP_ORDER: readonly ToolGroup[] = [
  'selection',
  'mesh',
  'analysis',
  'regions',
  'align',
  'fit',
  'reference',
  'sketch',
  'solid',
  'freeform',
  'inspect',
  'export',
];

function groupTools(tools: ToolDefinition[]): ToolDefinition[][] {
  return GROUP_ORDER.map((group) => tools.filter((tool) => tool.group === group)).filter(
    (group) => group.length,
  );
}

/** Undo and redo, the tool groups of the active stage, and the view group at the right. */
export function ToolRow() {
  const { t, i18n } = useTranslation();
  const stage = useTools((state) => state.stage);
  const activeToolId = useTools((state) => state.activeToolId);
  const selectionMode = useTools((state) => state.selectionMode);
  const canUndo = useHistory((state) => !!entryToUndo(state));
  const canRedo = useHistory((state) => !!entryToRedo(state));
  const busy = useJobs((state) => exclusiveJobRunning(state));
  useDocument((state) => state.snapshot?.revision);

  return (
    <div className={styles.row} role="toolbar" aria-label={t('toolGroups.history')}>
      <div className={styles.group}>
        <IconButton
          icon={Undo2}
          label={t('commands.undo')}
          shortcut={formatShortcut({ key: 'Z', ctrl: true }, i18n.language)}
          disabled={!canUndo || busy}
          data-testid="tool-undo"
          onClick={() => void undo()}
        />
        <IconButton
          icon={Redo2}
          label={t('commands.redo')}
          shortcut={formatShortcut({ key: 'Y', ctrl: true }, i18n.language)}
          disabled={!canRedo || busy}
          data-testid="tool-redo"
          onClick={() => void redo()}
        />
      </div>
      {groupTools(toolsForStage(stage)).map((group) => (
        <Fragment key={group[0]?.group}>
          <span className={styles.divider} aria-hidden />
          <div
            className={styles.group}
            role="group"
            aria-label={t(`toolGroups.${group[0]?.group ?? ''}`)}
          >
            {group.map((tool) => {
              const availability = toolAvailability(tool);
              const tooltipKey = toolKey(tool.id, 'tooltip');
              return (
                <ToolButton
                  key={tool.id}
                  icon={tool.icon}
                  label={t(toolKey(tool.id, 'label'))}
                  shortcut={tool.shortcut && formatShortcut(tool.shortcut, i18n.language)}
                  showLabel={tool.primary}
                  active={tool.id === activeToolId || tool.id === selectionMode}
                  disabled={!availability.enabled}
                  disabledReason={
                    availability.enabled
                      ? i18n.exists(tooltipKey)
                        ? t(tooltipKey)
                        : undefined
                      : t(availability.reasonKey)
                  }
                  testId={`tool-${tool.id}`}
                  onClick={() => void openTool(tool.id)}
                />
              );
            })}
          </div>
        </Fragment>
      ))}
      <span className={styles.spacer} />
      <div className={styles.group}>
        <ViewToolGroup />
      </div>
    </div>
  );
}
