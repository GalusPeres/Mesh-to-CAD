import * as THREE from 'three';

import type {
  SceneItem,
  SceneManifest,
  ScenePayload,
} from '@shared/protocol/generated/document-display';

import type {
  CameraView,
  HandleFactory,
  Overlay,
  PickHit,
  PickOptions,
  Ray,
  ScanTopology,
  ScanView,
  ScreenPoint,
  Vec3,
  Viewport,
  ViewportInteraction,
} from './api';
import { CameraRig } from './CameraRig';
import { type DisplayObject, type ThemeColors, createDisplayObject } from './displayItems';
import { createHandleFactory } from './handles';
import { SCENE_COLORS } from './palette';
import { PointerRouter } from './PointerRouter';
import { ScanMesh } from './scanMesh';
import { ScanProxy, computeScanTopology, facesInCircle, facesInPolygon } from './scanPicking';

export type PayloadFetcher = (keys: string[]) => Promise<ScenePayload[]>;

const EDGE_PICK_PX = 5;

const tuple = (vector: THREE.Vector3): Vec3 => [vector.x, vector.y, vector.z];

/**
 * The 3D scene: scan, display items, previews, overlays and handles, picking,
 * and rendering on demand (every change calls `invalidate()`, which schedules
 * one frame).
 */
export class SceneController implements Viewport {
  readonly scan: ScanView;
  readonly camera: CameraView;
  readonly handles: HandleFactory;

  private readonly renderer: THREE.WebGLRenderer;
  private readonly scene = new THREE.Scene();
  private readonly rig: CameraRig;
  private readonly pointer: PointerRouter;
  private readonly scanGroup = new THREE.Group();
  private readonly itemGroup = new THREE.Group();
  private readonly previewGroup = new THREE.Group();
  private readonly overlayGroup = new THREE.Group();
  private readonly handleGroup = new THREE.Group();
  private scanMesh: ScanMesh | null = null;
  private readonly items = new Map<string, DisplayObject>();
  private readonly previews = new Map<string, DisplayObject[]>();
  private topology: Promise<ScanTopology> | null = null;
  private syncToken = 0;
  private frameRequest = 0;
  private theme: ThemeColors;
  private readonly resizeObserver: ResizeObserver;
  private readonly raycaster = new THREE.Raycaster();

  constructor(
    private readonly container: HTMLElement,
    private readonly fetchPayloads: PayloadFetcher,
    theme: ThemeColors,
  ) {
    this.theme = theme;
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(window.devicePixelRatio);
    this.renderer.setClearColor(theme.viewportBackground);
    const canvas = this.renderer.domElement;
    canvas.dataset.testid = 'viewport-canvas';
    canvas.tabIndex = 0;
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    container.appendChild(canvas);

    this.scene.add(
      new THREE.HemisphereLight(SCENE_COLORS.hemisphereSky, SCENE_COLORS.hemisphereGround, 0.9),
    );
    this.scanGroup.matrixAutoUpdate = false;
    this.scene.add(
      this.scanGroup,
      this.itemGroup,
      this.previewGroup,
      this.overlayGroup,
      this.handleGroup,
    );

    this.rig = new CameraRig(this.scene, canvas, () => this.invalidate());
    this.pointer = new PointerRouter(canvas, (enabled) => this.rig.setNavigationEnabled(enabled));
    canvas.addEventListener('auxclick', (event) => {
      if (event.button === 1 && event.detail === 2) this.fitAll();
    });

    this.scan = new ScanProxy(() => this.scanMesh);
    this.camera = {
      fitAll: () => this.fitAll(),
      fitBox: (min, max) => this.rig.fitBox(min, max),
      setStandardView: (view) => this.rig.setStandardView(view),
      lookAlong: (origin, normal, xDirection) => this.rig.lookAlong(origin, normal, xDirection),
      setProjection: (projection) => this.rig.setProjection(projection),
      setOrbitLocked: (locked) => this.rig.setOrbitLocked(locked),
    };
    this.handles = createHandleFactory({
      group: this.handleGroup,
      addInteraction: (interaction) => this.addInteraction(interaction),
      screenToRay: (at) => this.screenToRay(at),
      worldToScreen: (point) => this.worldToScreen(point),
      worldPerPixel: (point) => this.rig.worldPerPixel(point),
      neutralColor: () => this.theme.text,
      invalidate: () => this.invalidate(),
    });

    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(container);
    this.resize();
  }

  dispose(): void {
    cancelAnimationFrame(this.frameRequest);
    this.resizeObserver.disconnect();
    this.pointer.dispose();
    this.rig.dispose();
    this.scanMesh?.dispose();
    for (const item of this.items.values()) item.dispose();
    for (const list of this.previews.values()) list.forEach((item) => item.dispose());
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }

  stats(): { scanFaces: number; items: number } {
    return { scanFaces: this.scanMesh?.faceCount ?? 0, items: this.items.size };
  }

  setTheme(theme: ThemeColors): void {
    this.theme = theme;
    this.renderer.setClearColor(theme.viewportBackground);
    this.invalidate();
  }

  setVisibility(scan: boolean, bodies: boolean): void {
    this.scanGroup.visible = scan;
    this.itemGroup.visible = bodies;
    this.invalidate();
  }

  /** Bring the drawn scene in line with a manifest, fetching payloads it does not have. */
  async syncScene(manifest: SceneManifest | null): Promise<void> {
    const token = ++this.syncToken;
    const scanEntry = manifest?.scan ?? null;
    const wantedItems = new Map((manifest?.items ?? []).map((item) => [item.key, item]));
    const missing = [...wantedItems.keys()].filter((key) => !this.items.has(key));
    const needsScan = scanEntry !== null && this.scanMesh?.scanKey !== scanEntry.key;
    if (needsScan) missing.unshift(scanEntry.key);

    const payloads = missing.length ? await this.fetchPayloads(missing) : [];
    if (token !== this.syncToken) return;
    const byKey = new Map(payloads.map((payload) => [payload.key, payload]));

    const firstScan = needsScan && !this.scanMesh;
    if (!scanEntry) {
      this.replaceScan(null);
    } else {
      const payload = byKey.get(scanEntry.key);
      if (needsScan && payload?.type === 'scan') {
        this.replaceScan(new ScanMesh(payload, scanEntry.key, () => this.invalidate()));
      }
      // Positions are relative to the scan origin in scan coordinates; the
      // alignment transform places them in part coordinates.
      const matrix = new THREE.Matrix4().set(
        ...(scanEntry.transform as Parameters<THREE.Matrix4['set']>),
      );
      matrix.multiply(new THREE.Matrix4().makeTranslation(...scanEntry.origin));
      this.scanGroup.matrix.copy(matrix);
      this.scanGroup.matrixWorldNeedsUpdate = true;
    }
    this.syncItems(wantedItems, byKey);
    if (firstScan) this.fitAll();
    this.invalidate();
  }

  setPreviewItems(owner: string, items: readonly SceneItem[]): void {
    for (const object of this.previews.get(owner) ?? []) {
      this.previewGroup.remove(object.object);
      object.dispose();
    }
    this.previews.delete(owner);
    this.invalidate();
    if (items.length === 0) return;
    void this.fetchPayloads(items.map((item) => item.key)).then((payloads) => {
      const byKey = new Map(payloads.map((payload) => [payload.key, payload]));
      const objects = items.flatMap((item) => {
        const payload = byKey.get(item.key);
        const object = payload ? createDisplayObject(item, payload, this.theme) : null;
        return object ? [object] : [];
      });
      objects.forEach((object) => this.previewGroup.add(object.object));
      this.previews.set(owner, objects);
      this.invalidate();
    });
  }

  highlight(target: { bodyId: string; edge?: number } | { owner: string } | null): void {
    for (const { item, object } of this.items.values()) {
      if (!(object instanceof THREE.Mesh)) continue;
      const material = object.material as THREE.MeshStandardMaterial;
      const hit =
        !!target &&
        ('owner' in target ? item.owner === target.owner : item.bodyId === target.bodyId);
      if (hit) material.emissive.set(SCENE_COLORS.selection);
      else material.emissive.setRGB(0, 0, 0);
      material.emissiveIntensity = hit ? 0.25 : 0;
    }
    this.invalidate();
  }

  pick(at: ScreenPoint, options: PickOptions = {}): PickHit | null {
    const kinds = options.kinds ?? ['scan', 'body', 'edge', 'item'];
    this.raycaster.setFromCamera(this.rig.toNdc(at), this.rig.camera);
    this.raycaster.params.Line = {
      threshold: this.rig.worldPerPixel(this.rig.target) * EDGE_PICK_PX,
    };
    const targets: THREE.Object3D[] = [];
    if (kinds.includes('scan') && this.scanMesh && this.scanGroup.visible)
      targets.push(this.scanMesh.mesh);
    if (this.itemGroup.visible)
      targets.push(...[...this.items.values()].map((item) => item.object));
    for (const hit of this.raycaster.intersectObjects(targets, false)) {
      const point = tuple(hit.point);
      if (hit.object === this.scanMesh?.mesh) {
        if (hit.faceIndex == null || this.scanMesh.isHidden(hit.faceIndex)) continue;
        return { kind: 'scan', face: hit.faceIndex, point };
      }
      const item = hit.object.userData.item as SceneItem | undefined;
      if (!item) continue;
      if (item.bodyId && hit.object instanceof THREE.Mesh && kinds.includes('body')) {
        const faceIds = hit.object.userData.faceIds as Uint32Array;
        return { kind: 'body', bodyId: item.bodyId, face: faceIds[hit.faceIndex ?? 0] ?? 0, point };
      }
      if (item.bodyId && hit.object instanceof THREE.LineSegments && kinds.includes('edge')) {
        const ids = hit.object.userData.ids as Uint32Array;
        return {
          kind: 'edge',
          bodyId: item.bodyId,
          edge: ids[Math.floor((hit.index ?? 0) / 2)] ?? 0,
          point,
        };
      }
      if (kinds.includes('item')) return { kind: 'item', key: item.key, owner: item.owner, point };
    }
    return null;
  }

  pickScanFacesInCircle(
    at: ScreenPoint,
    radiusPx: number,
    options: { visibleOnly: boolean },
  ): Uint32Array {
    if (!this.scanMesh) return new Uint32Array();
    const { toClip, toView } = this.scanProjection();
    return facesInCircle(
      this.scanMesh,
      at,
      radiusPx,
      this.size(),
      toClip,
      options.visibleOnly ? toView : null,
    );
  }

  pickScanFacesInPolygon(
    polygon: Float32Array,
    options: { visibleOnly: boolean },
  ): Promise<Uint32Array> {
    if (!this.scanMesh) return Promise.resolve(new Uint32Array());
    const { toClip, toView } = this.scanProjection();
    return Promise.resolve(
      facesInPolygon(
        this.scanMesh,
        polygon,
        this.size(),
        toClip,
        options.visibleOnly ? toView : null,
      ),
    );
  }

  scanTopology(): Promise<ScanTopology> {
    const mesh = this.scanMesh;
    if (!mesh) return Promise.reject(new Error('no scan loaded'));
    this.topology ??= Promise.resolve(computeScanTopology(mesh, this.scanGroup.matrix));
    return this.topology;
  }

  screenToRay(at: ScreenPoint): Ray {
    this.raycaster.setFromCamera(this.rig.toNdc(at), this.rig.camera);
    return {
      origin: tuple(this.raycaster.ray.origin),
      direction: tuple(this.raycaster.ray.direction),
    };
  }

  worldToScreen(point: Vec3): ScreenPoint | null {
    return this.rig.toScreen(point);
  }

  addInteraction(interaction: ViewportInteraction): () => void {
    return this.pointer.add(interaction);
  }

  createOverlay(): Overlay {
    const group = new THREE.Group();
    this.overlayGroup.add(group);
    return {
      add: (object) => {
        group.add(object as THREE.Object3D);
        this.invalidate();
      },
      clear: () => {
        group.clear();
        this.invalidate();
      },
      dispose: () => {
        this.overlayGroup.remove(group);
        this.invalidate();
      },
    };
  }

  invalidate(): void {
    if (this.frameRequest) return;
    this.frameRequest = requestAnimationFrame(() => {
      this.frameRequest = 0;
      this.renderer.render(this.scene, this.rig.camera);
    });
  }

  capture(options: { width?: number; height?: number } = {}): Promise<Blob> {
    const previous = this.size();
    const resized = !!(options.width && options.height);
    if (resized) this.renderer.setSize(options.width ?? 0, options.height ?? 0, false);
    this.renderer.render(this.scene, this.rig.camera);
    return new Promise((resolve, reject) => {
      this.renderer.domElement.toBlob((blob) => {
        if (resized) this.renderer.setSize(previous.width, previous.height, false);
        if (blob) resolve(blob);
        else reject(new Error('capture failed'));
      }, 'image/png');
    });
  }

  private syncItems(wanted: Map<string, SceneItem>, payloads: Map<string, ScenePayload>): void {
    for (const [key, object] of this.items) {
      if (wanted.has(key)) continue;
      this.itemGroup.remove(object.object);
      object.dispose();
      this.items.delete(key);
    }
    for (const [key, item] of wanted) {
      const payload = payloads.get(key);
      if (this.items.has(key) || !payload) continue;
      const object = createDisplayObject(item, payload, this.theme);
      if (!object) continue;
      this.items.set(key, object);
      this.itemGroup.add(object.object);
    }
  }

  private replaceScan(mesh: ScanMesh | null): void {
    if (this.scanMesh) {
      this.scanGroup.remove(this.scanMesh.mesh);
      this.scanMesh.dispose();
    }
    this.scanMesh = mesh;
    this.topology = null;
    if (mesh) this.scanGroup.add(mesh.mesh);
  }

  private fitAll(): void {
    const box = new THREE.Box3();
    const bounds = this.scanMesh?.mesh.geometry.boundingBox;
    if (bounds) box.union(bounds.clone().applyMatrix4(this.scanGroup.matrix));
    for (const item of this.items.values()) box.expandByObject(item.object);
    if (!box.isEmpty()) this.rig.fitBox(tuple(box.min), tuple(box.max));
  }

  /** Matrices from scan-local coordinates to clip space and (rotation only) to view space. */
  private scanProjection(): { toClip: THREE.Matrix4; toView: THREE.Matrix3 } {
    const camera = this.rig.camera;
    const toCamera = new THREE.Matrix4().multiplyMatrices(
      camera.matrixWorldInverse,
      this.scanGroup.matrix,
    );
    return {
      toClip: new THREE.Matrix4().multiplyMatrices(camera.projectionMatrix, toCamera),
      toView: new THREE.Matrix3().setFromMatrix4(toCamera),
    };
  }

  private size(): { width: number; height: number } {
    return {
      width: Math.max(1, this.container.clientWidth),
      height: Math.max(1, this.container.clientHeight),
    };
  }

  private resize(): void {
    const { width, height } = this.size();
    this.renderer.setSize(width, height, false);
    this.rig.resize(width, height);
    this.invalidate();
  }
}
