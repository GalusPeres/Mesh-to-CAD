import { type KeyboardEvent, useRef } from 'react';
import { useTranslation } from 'react-i18next';

import { STAGES, type StageId, setStage, useTools } from '../state/toolStore';
import styles from './StageTabs.module.css';

/**
 * The stages filter the tool row; they are not a wizard. Switching keeps the
 * tree, the viewport, the selection and any open tool as they are.
 */
export function StageTabs() {
  const { t } = useTranslation();
  const stage = useTools((state) => state.stage);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);

  const onKeyDown = (event: KeyboardEvent, index: number) => {
    const offset = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
    if (!offset) return;
    const next = (index + offset + STAGES.length) % STAGES.length;
    setStage(STAGES[next] as StageId);
    tabs.current[next]?.focus();
  };

  return (
    <div className={styles.tabs} role="tablist" aria-label={t('stages.label')}>
      {STAGES.map((id, index) => (
        <button
          key={id}
          ref={(element) => {
            tabs.current[index] = element;
          }}
          type="button"
          role="tab"
          aria-selected={stage === id}
          tabIndex={stage === id ? 0 : -1}
          className={styles.tab}
          data-testid={`stage-${id}`}
          onClick={() => setStage(id)}
          onKeyDown={(event) => onKeyDown(event, index)}
        >
          {t(`stages.${id}`)}
        </button>
      ))}
    </div>
  );
}
