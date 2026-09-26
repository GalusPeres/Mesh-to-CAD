import { useEffect, useRef } from 'react';

import type { ScenePayload } from '@shared/protocol/generated/document-display';

import { kernel } from '../kernel/kernel';
import { documentStore } from '../state/documentStore';
import { viewStore } from '../state/viewStore';
import { registerViewport } from './api';
import type { ThemeColors } from './displayItems';
import { SceneController } from './SceneController';
import styles from './ViewportCanvas.module.css';

function readTheme(): ThemeColors {
  const root = document.documentElement;
  const style = getComputedStyle(root);
  const token = (name: string) => style.getPropertyValue(name).trim();
  return {
    dark: root.dataset.theme !== 'light',
    text: token('--text'),
    textSecondary: token('--text-secondary'),
    viewportBackground: token('--viewport-bg'),
  };
}

async function fetchPayloads(keys: string[]): Promise<ScenePayload[]> {
  const result = await kernel().call('scene.fetch', { keys }).result;
  return result.payloads;
}

/** Mounts the scene controller and keeps it in sync with the document and the view settings. */
export function ViewportCanvas() {
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = container.current;
    if (!element) return;
    const controller = new SceneController(element, fetchPayloads, readTheme());
    registerViewport(controller);

    const sync = () => {
      controller
        .syncScene(documentStore.getState().snapshot?.scene ?? null)
        .catch((error: unknown) => {
          window.m2c.app.log({ level: 'error', message: `scene sync failed: ${String(error)}` });
        });
    };
    sync();
    const unsubscribeDocument = documentStore.subscribe((state, previous) => {
      if (state.snapshot?.scene !== previous.snapshot?.scene) sync();
    });
    const applyView = () => {
      const { projection, visibility } = viewStore.getState();
      controller.camera.setProjection(projection);
      controller.setVisibility(visibility !== 'bodies', visibility !== 'scan');
    };
    applyView();
    const unsubscribeView = viewStore.subscribe(applyView);
    const themeObserver = new MutationObserver(() => controller.setTheme(readTheme()));
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    });

    return () => {
      themeObserver.disconnect();
      unsubscribeView();
      unsubscribeDocument();
      registerViewport(null);
      controller.dispose();
    };
  }, []);

  return <div ref={container} className={styles.viewport} />;
}
