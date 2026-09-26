// The WebGL canvas of the viewport and the screenshots taken from it.

import * as THREE from 'three';

/** A renderer whose canvas fills `container`; picked by tests as `viewport-canvas`. */
export function createViewportRenderer(
  container: HTMLElement,
  background: string,
): THREE.WebGLRenderer {
  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    powerPreference: 'high-performance',
  });
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setClearColor(background);
  // The section plane clips per material.
  renderer.localClippingEnabled = true;
  const canvas = renderer.domElement;
  canvas.dataset.testid = 'viewport-canvas';
  canvas.tabIndex = 0;
  canvas.style.width = '100%';
  canvas.style.height = '100%';
  container.appendChild(canvas);
  return renderer;
}

/**
 * A PNG of the scene at `width` x `height` pixels. The canvas is resized, drawn,
 * copied and restored within one task, so the resized frame is never shown.
 */
export function captureCanvas(
  renderer: THREE.WebGLRenderer,
  width: number,
  height: number,
  draw: (width: number, height: number) => void,
  restore: () => void,
): Promise<Blob> {
  const ratio = renderer.getPixelRatio();
  renderer.setPixelRatio(1);
  renderer.setSize(width, height, false);
  draw(width, height);
  const blob = new Promise<Blob>((resolve, reject) => {
    renderer.domElement.toBlob((result) => {
      if (result) resolve(result);
      else reject(new Error('capture failed'));
    }, 'image/png');
  });
  renderer.setPixelRatio(ratio);
  restore();
  return blob;
}
