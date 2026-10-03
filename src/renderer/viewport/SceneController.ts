import * as THREE from 'three';

import type { SceneItem, SceneManifest } from '@shared/protocol/generated/document-display';

import { settingsStore } from '../state/settingsStore';
import { type DisplayMode, type SectionPlane, setSectionPlane } from '../state/viewStore';
import type {
  CameraView,
  Overlay,
  PickHit,
  PickOptions,
  Ray,
  ScanSurfaceQueries,
  ScanTopology,
  ScreenPoint,
  Vec3,
  Viewport,
  ViewportInteraction,
} from './api';
import { CameraRig } from './CameraRig';
import { createDepthBias } from './depthBias';
import { CornerWidgets } from './cornerWidgets';
import type { ThemeColors } from './displayItems';
import { type InternalHandleFactory, createHandleFactory } from './handles';
import { type HighlightTarget, ItemLayer, type PayloadFetcher } from './itemLayer';
import { createOverlayGroup } from './overlays';
import { SCENE_COLORS } from './palette';
import { PointerRouter } from './PointerRouter';
import { createScanSurfaceQueries } from './scanDistance';
import { ScanLayer } from './scanLayer';
import { ScanQueries } from './scanQueries';
import { type PickScene, pickScene } from './scenePicking';
import { type SceneChange, SceneSync } from './sceneSync';
import { SectionPlaneController } from './sectionPlane';
import { warmUpShaders } from './shaderWarmUp';
import { captureCanvas, createViewportRenderer } from './rendererSetup';
import type { CubeLabels } from './viewCube';

export type { PayloadFetcher } from './itemLayer';

const ALL_KINDS: readonly PickHit['kind'][] = ['scan', 'body', 'edge', 'item'];
const tuple = (vector: THREE.Vector3): Vec3 => [vector.x, vector.y, vector.z];

/**
 * The 3D scene: scan, display items, previews, overlays, handles and the corner
 * widgets; picking; rendering on demand (every change calls `invalidate()`, which
 * schedules one frame). Tools see it only through viewport/api.ts.
 */
export class SceneController implements Viewport {
  readonly scan: ScanLayer;
  readonly camera: CameraView;
  readonly handles: InternalHandleFactory;
  readonly scanSurface: ScanSurfaceQueries;
  readonly rig: CameraRig;

  private readonly renderer: THREE.WebGLRenderer;
  private readonly scene = new THREE.Scene();
  private readonly handleScene = new THREE.Scene();
  private readonly scanGroup = new THREE.Group();
  private readonly overlayGroup = new THREE.Group();
  private readonly bias = createDepthBias();
  private readonly pointer: PointerRouter;
  private readonly section: SectionPlaneController;
  private readonly items: ItemLayer;
  private readonly sync: SceneSync;
  private readonly queries: ScanQueries;
  private readonly widgets: CornerWidgets;
  private readonly frameHooks = new Set<() => void>();
  private readonly resizeObserver: ResizeObserver;
  private theme: ThemeColors;
  private tolerance = 0.1;
  private display: { mode: DisplayMode; deviationVisible: boolean } = {
    mode: 'shaded',
    deviationVisible: false,
  };
  private frameRequest = 0;
  private contextLost = false;

  constructor(
    private readonly container: HTMLElement,
    fetchPayloads: PayloadFetcher,
    theme: ThemeColors,
  ) {
    this.theme = theme;
    this.renderer = createViewportRenderer(container, theme.viewportBackground);
    const canvas = this.renderer.domElement;

    this.handles = createHandleFactory({
      group: this.handleScene,
      bias: this.bias,
      addInteraction: (interaction) => this.addInteraction(interaction),
      screenToRay: (at) => this.screenToRay(at),
      worldToScreen: (point) => this.worldToScreen(point),
      worldPerPixel: (point) => this.rig.worldPerPixel(point),
      colors: () => ({
        neutral: this.theme.text,
        outline: this.theme.bgApp,
        accent: this.theme.accent,
      }),
      beforeFrame: (update) => {
        this.frameHooks.add(update);
        return () => this.frameHooks.delete(update);
      },
      invalidate: () => this.invalidate(),
    });
    this.section = new SectionPlaneController({
      handles: this.handles,
      bias: this.bias,
      scanGroup: this.scanGroup,
      scan: () => this.scan.current,
      sceneRadius: () => this.sceneBounds().getBoundingSphere(new THREE.Sphere()).radius,
      commit: (plane) => setSectionPlane(plane),
      invalidate: () => this.invalidate(),
    });
    const clipping = [this.section.clippingPlane];
    this.queries = new ScanQueries(this.renderer, clipping, {
      visibleScan: () => (this.scanGroup.visible ? this.scan.current : null),
      scanMatrix: this.scanGroup.matrix,
      camera: () => this.rig.camera,
      size: () => this.size(),
      pickScene: () => this.pickScene(),
    });
    this.scanSurface = createScanSurfaceQueries(() => this.scan.current, this.scanGroup.matrix);
    this.scan = new ScanLayer(clipping, (change) => {
      if (change === 'visibility') this.visibleFacesChanged();
      this.invalidate();
    });
    this.items = new ItemLayer(
      () => ({ bias: this.bias, clipping, theme: this.theme }),
      fetchPayloads,
      () => this.invalidate(),
    );
    this.sync = new SceneSync({
      fetch: fetchPayloads,
      scan: this.scan,
      items: this.items,
      scanGroup: this.scanGroup,
      changed: (change) => this.sceneChanged(change),
      firstScan: () => this.fitAll(false),
    });
    // The rig reports its first pose right away; everything it notifies exists by now.
    this.rig = new CameraRig(this.scene, canvas, {
      pickPivot: (at) => this.pick(at, { kinds: ['scan', 'body'] })?.point ?? null,
      invertWheel: () => settingsStore.getState().navigation.invertWheel,
      onChange: () => this.viewChanged(),
    });
    this.pointer = new PointerRouter(canvas, (enabled) => this.rig.setNavigationEnabled(enabled));

    this.scene.add(
      new THREE.HemisphereLight(SCENE_COLORS.hemisphereSky, SCENE_COLORS.hemisphereGround, 0.9),
    );
    this.scanGroup.matrixAutoUpdate = false;
    this.scene.add(this.scanGroup, this.items.group, this.items.previewGroup, this.overlayGroup);

    this.widgets = new CornerWidgets(theme, this.bias, this.pointer, {
      rig: this.rig,
      width: () => this.size().width,
      invalidate: () => this.invalidate(),
    });
    canvas.addEventListener('auxclick', (event) => {
      if (event.button === 1 && event.detail === 2) this.fitAll();
    });
    canvas.addEventListener('webglcontextlost', () => {
      this.contextLost = true;
      cancelAnimationFrame(this.frameRequest);
      this.frameRequest = 0;
    });
    canvas.addEventListener('webglcontextrestored', () => {
      // three.js re-creates its GL state; every buffer and texture is uploaded again.
      this.contextLost = false;
      this.invalidateFaceIds();
      this.invalidate();
    });

    this.camera = {
      fitAll: () => this.fitAll(),
      fitBox: (min, max) => this.rig.fitBox(min, max),
      setStandardView: (view) => this.rig.setStandardView(view),
      lookAlong: (origin, normal, xDirection) => this.rig.lookAlong(origin, normal, xDirection),
      setProjection: (projection) => this.rig.setProjection(projection),
      setOrbitLocked: (locked) => this.rig.setOrbitLocked(locked),
    };

    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(container);
    this.resize();
    warmUpShaders(this.renderer, this.rig.camera, this.scene, {
      materials: [
        this.scan.materials.opaque,
        this.scan.materials.transparent,
        this.queries.faceIds.material(0),
      ],
      display: { bias: this.bias, clipping, theme },
    }).catch((error: unknown) => {
      window.m2c.app.log({ level: 'warn', message: `shader warm-up failed: ${String(error)}` });
    });
  }

  dispose(): void {
    cancelAnimationFrame(this.frameRequest);
    this.resizeObserver.disconnect();
    this.pointer.dispose();
    this.rig.dispose();
    this.section.dispose();
    this.sync.dispose();
    this.items.dispose();
    this.queries.dispose();
    this.widgets.dispose();
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }

  // Settings from the stores (ViewportCanvas) -----------------------------------------

  syncScene(manifest: SceneManifest | null): Promise<void> {
    return this.sync.sync(manifest);
  }

  setTheme(theme: ThemeColors): void {
    this.theme = theme;
    this.renderer.setClearColor(theme.viewportBackground);
    this.scan.setDisplay(this.display.mode, this.display.deviationVisible, theme.text);
    this.items.setTheme();
    this.widgets.setTheme(theme);
    this.handles.refreshAll();
    this.invalidate();
  }

  setCubeLabels(labels: CubeLabels): void {
    this.widgets.setLabels(labels);
    this.invalidate();
  }

  setVisibility(scan: boolean, bodies: boolean): void {
    this.scanGroup.visible = scan;
    this.items.group.visible = bodies;
    this.items.previewGroup.visible = bodies;
    this.invalidate();
  }

  setDisplay(mode: DisplayMode, deviationVisible: boolean): void {
    this.display = { mode, deviationVisible };
    this.scan.setDisplay(mode, deviationVisible, this.theme.text);
    this.items.setBodyEdgesVisible(mode !== 'shaded');
  }

  setTolerance(tolerance: number): void {
    this.tolerance = tolerance > 0 ? tolerance : 0.1;
    this.scan.setTolerance(this.tolerance);
    this.invalidate();
  }

  setSectionPlane(plane: SectionPlane | null): void {
    if (plane === this.section.plane) return;
    this.section.set(plane);
    this.invalidateFaceIds();
  }

  /** A section through the middle of the scene that cuts away the half facing the viewer. */
  defaultSectionPlane(): SectionPlane {
    const center = this.sceneBounds().getCenter(new THREE.Vector3());
    const towardsCamera = new THREE.Vector3(0, 0, 1).applyQuaternion(this.rig.camera.quaternion);
    return SectionPlaneController.facingViewer(tuple(center), towardsCamera);
  }

  fitSelection(): void {
    const bounds = this.scan.current?.selectionBounds();
    if (!bounds) {
      this.fitAll();
      return;
    }
    bounds.applyMatrix4(this.scanGroup.matrix);
    this.rig.fitBox(tuple(bounds.min), tuple(bounds.max));
  }

  // Viewport ------------------------------------------------------------------------------

  stats(): { scanFaces: number; items: number } {
    return { scanFaces: this.scan.current?.shownFaces ?? 0, items: this.items.count };
  }

  setOwnerHidden(owner: string | null): void {
    this.items.setHiddenOwner(owner);
  }

  /** The tree's hidden lists (panels/objectVisibility.ts finds this member at run time). */
  setHiddenObjects(hidden: { bodies: readonly string[]; owners: readonly string[] }): void {
    this.items.setHiddenObjects(hidden.bodies, hidden.owners);
  }

  setPreviewItems(owner: string, items: readonly SceneItem[]): void {
    this.items.setPreview(owner, items).catch((error: unknown) => {
      window.m2c.app.log({ level: 'error', message: `preview items failed: ${String(error)}` });
    });
  }

  highlight(target: HighlightTarget): void {
    this.items.highlight(target);
  }

  pick(at: ScreenPoint, options: PickOptions = {}): PickHit | null {
    return pickScene(this.pickScene(), at, options.kinds ?? ALL_KINDS);
  }

  pickScanFacesInCircle(
    at: ScreenPoint,
    radiusPx: number,
    options: { visibleOnly: boolean },
  ): Uint32Array {
    return this.queries.circle(at, radiusPx, options.visibleOnly);
  }

  pickScanFacesInPolygon(
    polygon: Float32Array,
    options: { visibleOnly: boolean },
  ): Promise<Uint32Array> {
    return this.queries.polygon(polygon, options.visibleOnly);
  }

  scanTopology(): Promise<ScanTopology> {
    return this.queries.scanTopology(this.scan.current);
  }

  screenToRay(at: ScreenPoint): Ray {
    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(this.rig.toNdc(at), this.rig.camera);
    return { origin: tuple(raycaster.ray.origin), direction: tuple(raycaster.ray.direction) };
  }

  worldToScreen(point: Vec3): ScreenPoint | null {
    return this.rig.toScreen(point);
  }

  addInteraction(interaction: ViewportInteraction): () => void {
    return this.pointer.add(interaction);
  }

  createOverlay(): Overlay {
    return createOverlayGroup(this.overlayGroup, this.bias, () => this.invalidate());
  }

  invalidate(): void {
    if (this.frameRequest || this.contextLost) return;
    this.frameRequest = requestAnimationFrame(() => this.frame());
  }

  capture(options: { width?: number; height?: number } = {}): Promise<Blob> {
    const size = this.size();
    const draw = (width: number, height: number) => {
      this.rig.resize(width, height);
      this.prepareFrame();
      this.renderer.render(this.scene, this.rig.camera);
    };
    const restore = () => {
      this.resize();
      this.frame();
    };
    const width = Math.round(options.width ?? size.width);
    const height = Math.round(options.height ?? size.height);
    return captureCanvas(this.renderer, width, height, draw, restore);
  }

  // Internals -------------------------------------------------------------------------------

  private pickScene(): PickScene {
    return {
      rig: this.rig,
      size: this.size(),
      scan: this.scanGroup.visible ? this.scan.current : null,
      scanMatrix: this.scanGroup.matrix,
      items: this.items,
      clippingPlane: this.section.clippingPlane,
      sectionOn: this.section.plane !== null,
      bias: this.bias.uniform.value,
    };
  }

  private invalidateFaceIds(): void {
    this.queries.invalidateIds();
  }

  private viewChanged(): void {
    this.invalidateFaceIds();
    this.invalidate();
  }

  /** Faces were hidden or shown, or the scan changed: ids and the section outline change. */
  private visibleFacesChanged(): void {
    this.invalidateFaceIds();
    this.section.scanChanged();
  }

  private sceneChanged(change: SceneChange): void {
    if (change !== 'items') this.visibleFacesChanged();
    if (change === 'scan' || change === 'placement') this.queries.resetTopology();
    const box = this.sceneBounds();
    if (!box.isEmpty()) {
      const sphere = box.getBoundingSphere(new THREE.Sphere());
      this.rig.setSceneBounds(tuple(sphere.center), sphere.radius);
    }
    this.invalidate();
  }

  private sceneBounds(): THREE.Box3 {
    const box = this.items.bounds();
    const mesh = this.scan.current;
    if (mesh) box.union(mesh.bounds.clone().applyMatrix4(this.scanGroup.matrix));
    return box;
  }

  private fitAll(animate = true): void {
    const box = this.sceneBounds();
    if (!box.isEmpty()) this.rig.fitBox(tuple(box.min), tuple(box.max), animate);
  }

  /** Per-frame work before drawing: chunk uploads, screen-size handles, the outline. */
  private prepareFrame(): void {
    const mesh = this.scan.current;
    if (mesh && !mesh.complete && mesh.showNextChunk()) {
      this.invalidateFaceIds();
      if (!mesh.complete) this.invalidate();
    }
    for (const hook of this.frameHooks) hook();
    this.section.update();
    // Items within this distance of the scan are drawn in front of it.
    this.bias.uniform.value = 2 * this.tolerance + 2 * this.rig.worldPerPixel(this.rig.target);
    this.widgets.follow(this.rig.camera.quaternion);
  }

  private frame(): void {
    this.frameRequest = 0;
    if (this.contextLost) return;
    this.prepareFrame();
    const renderer = this.renderer;
    renderer.render(this.scene, this.rig.camera);
    renderer.autoClear = false;
    renderer.render(this.handleScene, this.rig.camera);
    renderer.autoClear = true;
    const { width, height } = this.size();
    this.widgets.render(renderer, width, height);
    this.scan.current?.afterRender();
  }

  private size(): { width: number; height: number } {
    return {
      width: Math.max(1, this.container.clientWidth),
      height: Math.max(1, this.container.clientHeight),
    };
  }

  private resize(): void {
    const { width, height } = this.size();
    if (this.renderer.getPixelRatio() !== window.devicePixelRatio)
      this.renderer.setPixelRatio(window.devicePixelRatio);
    this.renderer.setSize(width, height, false);
    this.rig.resize(width, height);
    this.invalidateFaceIds();
    this.invalidate();
  }
}
