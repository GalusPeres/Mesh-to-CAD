import { CircleHelp } from 'lucide-react';
import { type ReactNode, useEffect } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '../../ui/Button/Button';
import { IconButton } from '../../ui/IconButton/IconButton';
import { PanelSection } from '../../ui/PanelSection/PanelSection';
import { toolById, toolKey } from './registry';
import styles from './ToolPanel.module.css';

export interface ToolPanelFrameProps {
  toolId: string;
  children: ReactNode;
  /** Shown instead of the tool name while editing a feature ("Bearbeiten: Extrusion 2"). */
  editingName?: string;
  canCommit: boolean;
  busy?: boolean;
  onCommit: () => void;
  onCancel: () => void;
  /** Commit and keep the tool open (Shift+Enter), for tools where repeating makes sense. */
  onApply?: () => void;
}

function isTextField(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))
  );
}

/**
 * Frame of every panel tool: header with name and help, the tool's sections,
 * an optional "So geht's" section, and the footer with OK / Abbrechen.
 * Enter commits and Esc cancels, except while a text field has focus.
 */
export function ToolPanel({
  toolId,
  children,
  editingName,
  canCommit,
  busy,
  onCommit,
  onCancel,
  onApply,
}: ToolPanelFrameProps) {
  const { t, i18n } = useTranslation();
  const tool = toolById(toolId);
  const Icon = tool?.icon;
  const title = editingName
    ? t('common:tool.editing', { name: editingName })
    : t(toolKey(toolId, 'label'));
  const helpKey = toolKey(toolId, 'help');
  const hasHelp = i18n.exists(helpKey);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || isTextField(event.target)) return;
      if (event.key === 'Enter' && canCommit && !busy) {
        event.preventDefault();
        if (event.shiftKey && onApply) onApply();
        else onCommit();
      } else if (event.key === 'Escape') {
        event.preventDefault();
        onCancel();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [canCommit, busy, onCommit, onCancel, onApply]);

  return (
    <div className={styles.panel} data-testid={`panel-${toolId}`}>
      <header className={styles.header}>
        {Icon && <Icon size={16} aria-hidden />}
        <h2 className={styles.title}>{title}</h2>
        {hasHelp && <IconButton icon={CircleHelp} label={t('common:actions.help')} shortcut="F1" />}
      </header>
      <div className={styles.body}>
        {children}
        {hasHelp && (
          <PanelSection title={t('common:sections.howTo')} defaultOpen={false}>
            <p className={styles.help}>{t(helpKey)}</p>
          </PanelSection>
        )}
      </div>
      <footer className={styles.footer}>
        {onApply && (
          <Button
            variant="ghost"
            disabled={!canCommit || busy}
            data-testid="panel-apply"
            onClick={onApply}
          >
            {t('common:actions.apply')}
          </Button>
        )}
        <span className={styles.spacer} />
        <Button
          variant="primary"
          disabled={!canCommit || busy}
          data-testid="panel-ok"
          onClick={onCommit}
        >
          {t('common:actions.ok')}
        </Button>
        <Button data-testid="panel-cancel" onClick={onCancel}>
          {t('common:actions.cancel')}
        </Button>
      </footer>
    </div>
  );
}
