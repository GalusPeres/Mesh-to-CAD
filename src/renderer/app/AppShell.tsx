import { type DragEvent, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ObjectProperties } from '../panels/ObjectProperties';
import { ProjectTree } from '../panels/ProjectTree';
import { useDocument } from '../state/documentStore';
import { useTools } from '../state/toolStore';
import { ToolHost } from '../tools/framework/ToolHost';
import { openDroppedFile } from '../tools/import-mesh/importFlow';
import { ViewportCanvas } from '../viewport/ViewportCanvas';
import styles from './AppShell.module.css';
import { EmptyState } from './empty-state/EmptyState';
import { DIALOGS, OVERLAYS } from './extensions';
import { Splitter } from './Splitter';
import { StatusBar } from './StatusBar';
import { TitleBar } from './TitleBar';
import { ToolRow } from './ToolRow';
import { useShortcuts } from './useShortcuts';

const LEFT = { initial: 260, min: 200, max: 420 };
const RIGHT = { initial: 300, min: 260, max: 440 };

/** Title bar, tool row, project panel, viewport, properties panel and status bar. */
export function AppShell() {
  const { t } = useTranslation();
  const [leftWidth, setLeftWidth] = useState(LEFT.initial);
  const [rightWidth, setRightWidth] = useState(RIGHT.initial);
  const [dropping, setDropping] = useState(false);
  const hasScan = useDocument((state) => !!state.snapshot?.document.scan);
  const toolOpen = useTools((state) => state.activeToolId !== null);
  useShortcuts();

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDropping(false);
    const file = event.dataTransfer.files[0];
    if (file) void openDroppedFile(file);
  };

  return (
    <div className={styles.shell}>
      <TitleBar />
      <ToolRow />
      <div
        className={styles.workspace}
        style={{ gridTemplateColumns: `${leftWidth}px 1px 1fr 1px ${rightWidth}px` }}
        onDragOver={(event) => {
          event.preventDefault();
          setDropping(true);
        }}
        onDragLeave={() => setDropping(false)}
        onDrop={onDrop}
      >
        <aside className={styles.panel} aria-label={t('panels.project')}>
          <h2 className={styles.panelTitle}>{t('panels.project')}</h2>
          <div className={styles.panelBody}>
            <ProjectTree />
          </div>
        </aside>
        <Splitter
          side="left"
          label={t('panels.project')}
          width={leftWidth}
          min={LEFT.min}
          max={LEFT.max}
          onResize={setLeftWidth}
        />
        <main className={styles.viewport}>
          <ViewportCanvas />
          {!hasScan && <EmptyState />}
          {OVERLAYS.map(({ Component, anchor }, index) => (
            <div key={index} className={styles[`overlay-${anchor}`]}>
              <Component />
            </div>
          ))}
          {dropping && <div className={styles.dropHint}>{t('dropFile')}</div>}
        </main>
        <Splitter
          side="right"
          label={t('panels.properties')}
          width={rightWidth}
          min={RIGHT.min}
          max={RIGHT.max}
          onResize={setRightWidth}
        />
        <aside className={styles.panel} aria-label={t('panels.properties')}>
          {toolOpen ? <ToolHost /> : <ObjectProperties />}
        </aside>
      </div>
      <StatusBar />
      {DIALOGS.map((Dialog, index) => (
        <Dialog key={index} />
      ))}
    </div>
  );
}
