// Display items of the document and of tool previews, their highlight, and the
// picking of their surfaces, edges, lines and points.

import * as THREE from 'three';

import type { SceneItem, ScenePayload } from '@shared/protocol/generated/document-display';

import type { HiddenObjects, PickHit } from './api';
import {
  type DisplayContext,
  type DisplayObject,
  createDisplayObject,
  createLines,
} from './displayItems';
import { distanceToSegment } from './handleMath';
import { type ItemVisibility, itemShown } from './itemVisibility';
import { SCENE_COLORS } from './palette';

export type PayloadFetcher = (keys: string[]) => Promise<ScenePayload[]>;
export type HighlightTarget = { bodyId: string; edge?: number } | { owner: string } | null;

/** A line or point of an item close to the pointer. */
export interface LineCandidate {
  hit: PickHit;
  /** Distance to the pointer in CSS pixels. */
  pixels: number;
}

/** A highlighted edge is drawn over the body edges in the selection colour. */
const EDGE_HIGHLIGHT_PX = 3;

const project = new THREE.Vector3();
const a3 = new THREE.Vector3();
const b3 = new THREE.Vector3();

export class ItemLayer {
  readonly group = new THREE.Group();
  readonly previewGroup = new THREE.Group();
  private readonly items = new Map<string, DisplayObject>();
  private readonly previews = new Map<string, { objects: DisplayObject[]; token: number }>();
  private previewToken = 0;
  private highlighted: HighlightTarget = null;
  private edgeOverlay: { object: THREE.Object3D; dispose(): void } | null = null;
  private visibility: ItemVisibility = {
    bodyEdges: true,
    editedOwner: null,
    hiddenBodies: new Set(),
    hiddenOwners: new Set(),
  };

  constructor(
    private readonly context: () => DisplayContext,
    private readonly fetch: PayloadFetcher,
    private readonly invalidate: () => void,
  ) {}

  get count(): number {
    return this.items.size;
  }

  /** Keys of wanted items that are not drawn yet. */
  missing(wanted: readonly SceneItem[]): string[] {
    return wanted.filter((item) => !this.items.has(item.key)).map((item) => item.key);
  }

  sync(wanted: readonly SceneItem[], payloads: Map<string, ScenePayload>): void {
    const keys = new Set(wanted.map((item) => item.key));
    for (const [key, object] of this.items) {
      if (keys.has(key)) continue;
      this.group.remove(object.object);
      object.dispose();
      this.items.delete(key);
    }
    for (const item of wanted) {
      const payload = payloads.get(item.key);
      if (this.items.has(item.key) || !payload) continue;
      const object = createDisplayObject(item, payload, this.context());
      if (!object) continue;
      this.items.set(item.key, object);
      this.group.add(object.object);
    }
    this.applyVisibility();
    this.applyHighlight();
    this.invalidate();
  }

  /** Body edges (the seams between B-Rep faces) follow the display mode, as in CAD programs. */
  setBodyEdgesVisible(visible: boolean): void {
    this.visibility = { ...this.visibility, bodyEdges: visible };
    this.applyVisibility();
    this.invalidate();
  }

  /** Hide the document items of one owner while a tool edits it in place. */
  setHiddenOwner(owner: string | null): void {
    this.visibility = { ...this.visibility, editedOwner: owner };
    this.applyVisibility();
    this.invalidate();
  }

  /** Hide bodies and the other items of features, as the project tree does. */
  setHiddenObjects(hidden: HiddenObjects): void {
    this.visibility = {
      ...this.visibility,
      hiddenBodies: new Set(hidden.bodies),
      hiddenOwners: new Set(hidden.owners),
    };
    this.applyVisibility();
    this.invalidate();
  }

  private applyVisibility(): void {
    for (const object of this.items.values()) {
      object.object.visible = itemShown(object.item, this.visibility);
    }
    for (const object of [...this.previews.values()].flatMap((preview) => preview.objects)) {
      if (object.item.style === 'bodyEdges') object.object.visible = this.visibility.bodyEdges;
    }
  }

  /**
   * Replace the preview of `owner`. The previous preview stays drawn at half
   * opacity until the new payloads arrive, so the view never flickers empty.
   */
  async setPreview(owner: string, items: readonly SceneItem[]): Promise<void> {
    const token = ++this.previewToken;
    const current = this.previews.get(owner);
    if (items.length === 0) {
      this.removePreview(owner);
      return;
    }
    current?.objects.forEach((object) => object.setStale(true));
    this.previews.set(owner, { objects: current?.objects ?? [], token });
    this.invalidate();
    const payloads = await this.fetch(items.map((item) => item.key));
    if (this.previews.get(owner)?.token !== token) return;
    const byKey = new Map(payloads.map((payload) => [payload.key, payload]));
    const objects = items.flatMap((item) => {
      const payload = byKey.get(item.key);
      const object = payload ? createDisplayObject(item, payload, this.context()) : null;
      return object ? [object] : [];
    });
    this.removePreview(owner);
    objects.forEach((object) => this.previewGroup.add(object.object));
    this.previews.set(owner, { objects, token });
    this.applyVisibility();
    this.applyHighlight();
    this.invalidate();
  }

  highlight(target: HighlightTarget): void {
    this.highlighted = target;
    this.applyHighlight();
    this.invalidate();
  }

  setTheme(): void {
    const theme = this.context().theme;
    for (const object of this.all()) object.setTheme(theme);
    this.invalidate();
  }

  /** Every drawn object: document items first, then previews. */
  all(): DisplayObject[] {
    return [...this.items.values(), ...[...this.previews.values()].flatMap((p) => p.objects)];
  }

  bounds(): THREE.Box3 {
    const box = new THREE.Box3();
    for (const object of this.all()) box.expandByObject(object.object);
    return box;
  }

  /** Mesh objects for raycasting (visible groups only). */
  surfaces(): THREE.Object3D[] {
    return this.visible()
      .filter((object) => object.object instanceof THREE.Mesh && object.object.visible)
      .map((o) => o.object);
  }

  /** The line or point nearest to the pointer within `maxPixels`. */
  nearestLine(
    at: { x: number; y: number },
    maxPixels: number,
    camera: THREE.Camera,
    size: { width: number; height: number },
    kinds: readonly PickHit['kind'][],
  ): LineCandidate | null {
    let best: LineCandidate | null = null;
    const toScreen = (point: THREE.Vector3) => {
      project.copy(point).project(camera);
      return {
        x: ((project.x + 1) / 2) * size.width,
        y: ((1 - project.y) / 2) * size.height,
        z: project.z,
      };
    };
    for (const display of this.visible()) {
      const { item, object } = display;
      const isEdge = item.style === 'bodyEdges' && !!item.bodyId;
      if (!kinds.includes(isEdge ? 'edge' : 'item')) continue;
      const matrix = object.matrixWorld;
      const consider = (pixels: number, hit: PickHit) => {
        if (pixels > maxPixels || (best && pixels >= best.pixels)) return;
        best = { hit, pixels };
      };
      if (display.lines) {
        const { segments, ids } = display.lines;
        for (let s = 0; s < segments.length / 6; s += 1) {
          a3.fromArray(segments, s * 6).applyMatrix4(matrix);
          b3.fromArray(segments, s * 6 + 3).applyMatrix4(matrix);
          const a = toScreen(a3);
          const b = toScreen(b3);
          if (Math.abs(a.z) > 1 || Math.abs(b.z) > 1) continue;
          const pixels = distanceToSegment(at, a, b);
          if (pixels > maxPixels) continue;
          const length = Math.hypot(b.x - a.x, b.y - a.y);
          const t =
            length > 0
              ? ((at.x - a.x) * (b.x - a.x) + (at.y - a.y) * (b.y - a.y)) / length ** 2
              : 0;
          const point = a3.clone().lerp(b3, Math.min(1, Math.max(0, t)));
          const tuple = [point.x, point.y, point.z] as const;
          consider(
            pixels,
            isEdge
              ? { kind: 'edge', bodyId: item.bodyId ?? '', edge: ids[s] ?? 0, point: tuple }
              : { kind: 'item', key: item.key, owner: item.owner, point: tuple },
          );
        }
      } else if (object instanceof THREE.Points) {
        const points = object as THREE.Points<THREE.BufferGeometry>;
        const positions = points.geometry.getAttribute('position') as THREE.BufferAttribute;
        for (let i = 0; i < positions.count; i += 1) {
          a3.fromBufferAttribute(positions, i).applyMatrix4(matrix);
          const p = toScreen(a3);
          const pixels = Math.hypot(p.x - at.x, p.y - at.y);
          consider(pixels, {
            kind: 'item',
            key: item.key,
            owner: item.owner,
            point: [a3.x, a3.y, a3.z],
          });
        }
      }
    }
    return best;
  }

  dispose(): void {
    this.edgeOverlay?.dispose();
    for (const object of this.all()) object.dispose();
    this.items.clear();
    this.previews.clear();
  }

  private visible(): DisplayObject[] {
    const shown: DisplayObject[] = [];
    if (this.group.visible)
      shown.push(...[...this.items.values()].filter((object) => object.object.visible));
    if (this.previewGroup.visible)
      shown.push(...[...this.previews.values()].flatMap((p) => p.objects));
    return shown;
  }

  private removePreview(owner: string): void {
    for (const object of this.previews.get(owner)?.objects ?? []) {
      this.previewGroup.remove(object.object);
      object.dispose();
    }
    this.previews.delete(owner);
    this.invalidate();
  }

  private applyHighlight(): void {
    const target = this.highlighted;
    for (const object of this.all()) {
      const { item } = object;
      let on = false;
      if (target && 'owner' in target) on = item.owner === target.owner;
      else if (target && item.bodyId === target.bodyId) on = target.edge === undefined;
      object.setHighlight(on);
    }
    this.edgeOverlay?.dispose();
    this.edgeOverlay = null;
    if (target && !('owner' in target) && target.edge !== undefined)
      this.drawEdge(target.bodyId, target.edge);
  }

  private drawEdge(bodyId: string, edge: number): void {
    const source = this.all().find(
      (object) =>
        object.item.style === 'bodyEdges' && object.item.bodyId === bodyId && object.lines,
    );
    if (!source?.lines) return;
    const { segments, ids } = source.lines;
    const picked: number[] = [];
    ids.forEach((id, s) => {
      if (id === edge) picked.push(...segments.subarray(s * 6, s * 6 + 6));
    });
    if (picked.length === 0) return;
    const { object, material } = createLines(
      Float32Array.from(picked),
      EDGE_HIGHLIGHT_PX,
      SCENE_COLORS.selection,
      this.context().bias,
      2,
    );
    material.clippingPlanes = this.context().clipping;
    const parent = source.object.parent ?? this.group;
    parent.add(object);
    this.edgeOverlay = {
      object,
      dispose: () => {
        parent.remove(object);
        (object as THREE.Mesh).geometry.dispose();
        material.dispose();
      },
    };
  }
}
