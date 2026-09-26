import { House, RotateCcw, RotateCw } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { ScenePayload } from '@shared/protocol/generated/document-display';

import { kernel } from '../kernel/kernel';
import { documentStore } from '../state/documentStore';
import { viewStore } from '../state/viewStore';
import { IconButton } from '../ui/IconButton/IconButton';
import { registerViewport } from './api';
import type { ThemeColors } from './displayItems';
import { SceneController } from './SceneController';
import type { CubeLabels } from './viewCube';
import styles from './ViewportCanvas.module.css';

function readTheme(): ThemeColors {
  const root = document.documentElement;
  const style = getComputedStyle(root);
  const token = (name: string) => style.getPropertyValue(name).trim();
  return {
    dark: root.dataset.theme !== 'light',
    text: token('--text'),
    textSecondary: token('--text-secondary'),
    accent: token('--accent'),
    accentText: token('--accent-text'),
    viewportBackground: token('--viewport-bg'),
    bgApp: token('--bg-app'),
    bgRaised: token('--bg-raised'),
    bgHover: token('--bg-hover'),
    borderStrong: token('--border-strong'),
    font: token('--font-ui'),
  };
}

async function fetchPayloads(keys: string[]): Promise<ScenePayload[]> {
  const result = await kernel().call('scene.fetch', { keys }).result;
  return result.payloads;
}

function logError(what: string, error: unknown): void {
  window.m2c.app.log({ level: 'error', message: `${what}: ${String(error)}` });
}

/** Mounts the scene controller and keeps it in sync with the document and the view settings. */
export function ViewportCanvas() {
  const container = useRef<HTMLDivElement>(null);
  const [controller, setController] = useState<SceneController | null>(null);
  const { t, i18n } = useTranslation('viewport');

  useEffect(() => {
    const element = container.current;
    if (!element) return;
    const scene = new SceneController(element, fetchPayloads, readTheme());
    registerViewport(scene);
    setController(scene);

    const syncDocument = () => {
      const snapshot = documentStore.getState().snapshot;
      scene.setTolerance(snapshot?.document.settings.tolerance ?? 0.1);
      scene
        .syncScene(snapshot?.scene ?? null)
        .catch((error: unknown) => logError('scene sync failed', error));
    };
    syncDocument();
    const unsubscribeDocument = documentStore.subscribe((state, previous) => {
      if (state.snapshot !== previous.snapshot) syncDocument();
    });
    const applyView = () => {
      const view = viewStore.getState();
      scene.camera.setProjection(view.projection);
      scene.setVisibility(view.visibility !== 'bodies', view.visibility !== 'scan');
      scene.setDisplay(view.displayMode, view.deviationVisible);
      scene.setSectionPlane(view.sectionPlane);
    };
    applyView();
    const unsubscribeView = viewStore.subscribe(applyView);
    const themeObserver = new MutationObserver(() => scene.setTheme(readTheme()));
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    });

    return () => {
      themeObserver.disconnect();
      unsubscribeView();
      unsubscribeDocument();
      registerViewport(null);
      setController(null);
      scene.dispose();
    };
  }, []);

  // View cube labels follow the language.
  useEffect(() => {
    const labels: CubeLabels = {
      front: t('views.front'),
      back: t('views.back'),
      left: t('views.left'),
      right: t('views.right'),
      top: t('views.top'),
      bottom: t('views.bottom'),
    };
    controller?.setCubeLabels(labels);
  }, [controller, t, i18n.language]);

  return (
    <div ref={container} className={styles.viewport}>
      {controller && (
        <div className={styles.cubeButtons}>
          <IconButton
            icon={House}
            label={t('viewCube.home')}
            className={styles.home}
            data-testid="view-cube-home"
            onClick={() => controller.camera.setStandardView('iso')}
          />
          <IconButton
            icon={RotateCcw}
            label={t('viewCube.rollLeft')}
            className={styles.rollLeft}
            data-testid="view-cube-roll-left"
            onClick={() => controller.rig.roll(-90)}
          />
          <IconButton
            icon={RotateCw}
            label={t('viewCube.rollRight')}
            className={styles.rollRight}
            data-testid="view-cube-roll-right"
            onClick={() => controller.rig.roll(90)}
          />
        </div>
      )}
    </div>
  );
}
