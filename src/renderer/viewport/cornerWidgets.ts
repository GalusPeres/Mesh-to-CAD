// The view cube (top right) and the axis triad (bottom left): own scenes drawn
// into scissored corners of the viewport's WebGL context after the main scene.

import type * as THREE from 'three';

import { AxisTriad } from './axisTriad';
import type { CameraRig } from './CameraRig';
import type { DepthBias } from './depthBias';
import type { ThemeColors } from './displayItems';
import type { PointerRouter } from './PointerRouter';
import { type CubeLabels, ViewCube } from './viewCube';
import { ViewCubeControl } from './viewCubeControl';

export class CornerWidgets {
  private readonly cube: ViewCube;
  private readonly triad: AxisTriad;

  constructor(
    theme: ThemeColors,
    bias: DepthBias,
    pointer: PointerRouter,
    host: { rig: CameraRig; width: () => number; invalidate: () => void },
  ) {
    this.cube = new ViewCube(theme);
    this.triad = new AxisTriad(bias, theme);
    pointer.addChrome(
      new ViewCubeControl(this.cube, {
        rig: host.rig,
        width: host.width,
        setCursor: (cursor) => pointer.setChromeCursor(cursor),
        invalidate: host.invalidate,
      }),
    );
  }

  setTheme(theme: ThemeColors): void {
    this.cube.setTheme(theme);
    this.triad.setTheme(theme);
  }

  setLabels(labels: CubeLabels): void {
    this.cube.setLabels(labels);
  }

  /** Turn both widgets like the main camera. */
  follow(quaternion: THREE.Quaternion): void {
    this.cube.follow(quaternion);
    this.triad.follow(quaternion);
  }

  /** Draw both widgets over the finished frame; `width`, `height` in CSS pixels. */
  render(renderer: THREE.WebGLRenderer, width: number, height: number): void {
    const autoClear = renderer.autoClear;
    renderer.autoClear = false;
    renderer.setScissorTest(true);
    for (const [scene, camera, rect] of [
      [this.cube.scene, this.cube.camera, ViewCube.rect(width)],
      [this.triad.scene, this.triad.camera, AxisTriad.rect(height)],
    ] as const) {
      // three.js viewports count from the bottom left corner.
      const bottom = height - rect.y - rect.size;
      renderer.setViewport(rect.x, bottom, rect.size, rect.size);
      renderer.setScissor(rect.x, bottom, rect.size, rect.size);
      renderer.clearDepth();
      renderer.render(scene, camera);
    }
    renderer.setScissorTest(false);
    renderer.setViewport(0, 0, width, height);
    renderer.autoClear = autoClear;
  }

  dispose(): void {
    this.cube.dispose();
    this.triad.dispose();
  }
}
