// The freeform-net tool's working state outside React: the draft net, its dense
// limit surface and viewport overlay, the heatmap against the scan, the chosen
// control points, the draft history, and the kernel requests that generate, fit
// and map the net. The panel subscribes for its numbers; a drag only touches the
// viewport, never React.

import type { MethodName } from '@shared/protocol/generated/index';

import { isSilentFailure } from '../../kernel/KernelFailure';
import type { KernelJob, ParamsOf, ResultOf } from '../../kernel/KernelClient';
import { kernel } from '../../kernel/kernel';
import type { Vec3, Viewport } from '../../viewport/api';
import { toFailure } from '../framework/hooks';
import {
  type DeviationSummary,
  type HeatmapScale,
  SEARCH_FACTOR,
  colorize,
  deviationSummary,
  heatmapScale,
} from './heatmap';
import { GuideOverlay } from './GuideOverlay';
import { LimitSurface } from './limitSurface';
import { type Edge, addQuad, borderChain, borderEdges, extrudeEdges, splitRing } from './netBuild';
import { type NetEditorState, type NetJobKind, initialNetState } from './netState';
import { NetOverlay } from './NetOverlay';
import {
  type Net,
  NetHistory,
  cloneNet,
  controlOffsets,
  fitPlane,
  irregularCount,
  projectOntoPlane,
  sameTopology,
} from './netModel';

export type { NetEditorState, NetJobKind } from './netState';

export const FREEFORM_NET_TOOL_ID = 'freeform-net';
/** Fairness of "Anschmiegen" and the stronger one of "Glätten" (kernel `net.fit`). */
export const SNAP_SMOOTHING = 0.002;
export const SMOOTH_SMOOTHING = 0.05;
const FIT_ITERATIONS = 4;
/** Dense vertices measured per animation frame after a change of the whole net. */
const MEASURE_CHUNK = 6000;

interface Drag {
  controls: Uint32Array;
  rows: Uint32Array;
  startVertices: Float64Array;
  startLimits: Float64Array;
}

const nextFrame = () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));

export class NetEditor {
  private state: NetEditorState;
  private readonly listeners = new Set<() => void>();
  private net: Net | null = null;
  private surface: LimitSurface | null = null;
  private overlay: NetOverlay | null = null;
  private distances = new Float32Array(0);
  private colors = new Float32Array(0);
  private readonly selection = new Set<number>();
  private hover: number | null = null;
  /** Control points near the pointer; only these (and chosen ones) are drawn. */
  private nearby = new Set<number>();
  private readonly history = new NetHistory();
  private running: KernelJob<unknown> | null = null;
  private measureToken = 0;
  private drag: Drag | null = null;
  private guides: GuideOverlay | null = null;
  private facePoints: { point: Vec3; normal: Vec3 }[] = [];
  private facePreview: Vec3 | null = null;
  private hoverEdge: Edge | null = null;
  private extrusionPreview: number[] = [];
  private scale: HeatmapScale;
  private detached = false;
  /** Scan triangles the net belongs to (fitting uses them); null = the whole scan. */
  faces: Uint32Array | null = null;

  constructor(
    private readonly viewport: Viewport,
    tolerance: number,
  ) {
    this.scale = heatmapScale(tolerance);
    this.state = initialNetState(this.scale.tolerance);
  }

  // React access ------------------------------------------------------------------------

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getState = (): NetEditorState => this.state;

  private update(patch: Partial<NetEditorState>): void {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((listener) => listener());
  }

  // The net ---------------------------------------------------------------------------------

  current(): Net | null {
    return this.net ? cloneNet(this.net) : null;
  }

  async generate(faces: Uint32Array | null, targetQuads: number): Promise<void> {
    const result = await this.run('generate', 'net.generate', { faces, targetQuads });
    if (!result) return;
    this.faces = faces;
    await this.setNet({ vertices: result.vertices, quads: result.quads }, true);
  }

  async load(featureId: string): Promise<void> {
    const result = await this.run('load', 'net.featureNet', { featureId });
    if (!result) return;
    this.faces = result.faces;
    await this.setNet({ vertices: result.vertices, quads: result.quads }, false);
    this.history.reset(this.net);
    this.syncHistory();
  }

  /**
   * Snap the net to the scan; with chosen points only those move ("Glätten": fairer).
   * Returns whether the fitted net was shown (and recorded).
   */
  async fit(smooth: boolean): Promise<boolean> {
    const net = this.net;
    if (!net) return false;
    const fixed =
      this.selection.size > 0
        ? Uint8Array.from({ length: net.vertices.length / 3 }, (_, i) =>
            this.selection.has(i) ? 0 : 1,
          )
        : null;
    const result = await this.run(smooth ? 'smooth' : 'fit', 'net.fit', {
      vertices: net.vertices,
      quads: net.quads,
      faces: this.faces,
      fixed,
      smoothing: smooth ? SMOOTH_SMOOTHING : SNAP_SMOOTHING,
      iterations: FIT_ITERATIONS,
    });
    if (!result) return false;
    await this.setNet({ vertices: result.vertices, quads: net.quads }, true);
    return true;
  }

  /**
   * Lay the chosen control points on their best-fitting plane. Where a region of the
   * net and the ring of points around it are coplanar, its limit surface is exactly
   * that plane (affine invariance of subdivision), so flat faces become truly flat.
   */
  async flatten(): Promise<void> {
    const net = this.net;
    const surface = this.surface;
    if (!net || !surface || this.selection.size < 3 || this.state.job) return;
    const chosen = [...this.selection];
    const limits = new Float64Array(chosen.length * 3);
    chosen.forEach((control, index) => limits.set(surface.limitPoint(control), index * 3));
    const plane = fitPlane(limits);
    if (!plane) return;
    const next = cloneNet(net);
    projectOntoPlane(next.vertices, chosen, plane);
    await this.setNet(next, true);
  }

  cancelJob(): void {
    this.running?.cancel();
  }

  undo(): boolean {
    const net = this.history.undo();
    if (!net) return false;
    void this.setNet(net, false);
    return true;
  }

  redo(): boolean {
    const net = this.history.redo();
    if (!net) return false;
    void this.setNet(net, false);
    return true;
  }

  // Display options -------------------------------------------------------------------------

  setSnap(snap: boolean): void {
    this.update({ snap });
  }

  setHeatmap(heatmap: boolean): void {
    this.overlay?.setSurfaceColors(heatmap ? this.colors : null);
    this.viewport.invalidate();
    this.update({ heatmap });
  }

  setTolerance(tolerance: number): void {
    if (tolerance === this.scale.tolerance) return;
    this.scale = heatmapScale(tolerance);
    this.update({ tolerance });
    void this.measureAll();
  }

  get tolerance(): number {
    return this.scale.tolerance;
  }

  // Control points --------------------------------------------------------------------------

  get controlCount(): number {
    return this.surface?.controlCount ?? 0;
  }

  limitPoint(control: number): Vec3 {
    return this.surface?.limitPoint(control) ?? [0, 0, 0];
  }

  normalAt(control: number): Vec3 {
    return this.overlay?.normalAt(control) ?? [0, 0, 1];
  }

  isSelected(control: number): boolean {
    return this.selection.has(control);
  }

  /** Replace, extend or reduce the chosen control points. */
  choose(controls: Iterable<number>, mode: 'replace' | 'add' | 'remove' | 'toggle'): void {
    if (mode === 'replace') this.selection.clear();
    for (const control of controls) {
      if (mode === 'remove') this.selection.delete(control);
      else if (mode === 'toggle' && this.selection.has(control)) this.selection.delete(control);
      else this.selection.add(control);
    }
    this.repaintPoints();
    this.update({ selected: this.selection.size });
  }

  chooseAll(): void {
    this.choose(
      Array.from({ length: this.controlCount }, (_, i) => i),
      'replace',
    );
  }

  setHover(control: number | null, nearby?: Iterable<number>): void {
    if (control === this.hover && !nearby) return;
    this.hover = control;
    if (nearby) this.nearby = new Set(nearby);
    this.repaintPoints();
  }

  // Building by hand -------------------------------------------------------------------------

  /** Start or stop placing a face by four clicks on the scan. */
  setFacing(facing: boolean): void {
    this.facePoints = [];
    this.facePreview = null;
    this.update({ facing, facePoints: 0 });
    this.drawGuides();
  }

  /** A clicked scan point of the new face; the fourth one adds the face. */
  async addFacePoint(point: Vec3, normal: Vec3): Promise<void> {
    if (!this.state.facing || this.state.job) return;
    this.facePoints.push({ point, normal });
    this.update({ facePoints: this.facePoints.length });
    this.drawGuides();
    if (this.facePoints.length < 4) return;
    const corners = this.facePoints.map((clicked) => clicked.point);
    const outward = this.facePoints.reduce<Vec3>(
      (sum, clicked) => [
        sum[0] + clicked.normal[0],
        sum[1] + clicked.normal[1],
        sum[2] + clicked.normal[2],
      ],
      [0, 0, 0],
    );
    this.setFacing(false);
    await this.setNet(addQuad(this.net, corners, outward), true);
  }

  /** Take back the last clicked corner; false if there was none. */
  removeFacePoint(): boolean {
    if (this.facePoints.length === 0) return false;
    this.facePoints.pop();
    this.update({ facePoints: this.facePoints.length });
    this.drawGuides();
    return true;
  }

  /** The scan point under the pointer while placing a face (rubber band), or null. */
  previewFacePoint(point: Vec3 | null): void {
    this.facePreview = point;
    this.drawGuides();
  }

  /** Edges of the net (control-point pairs) and which of them are open border. */
  get edges(): { pairs: Uint32Array; border: Uint8Array } | null {
    const map = this.surface?.map;
    return map ? { pairs: map.edges, border: map.boundaryEdges } : null;
  }

  /** The border edge a-b directed as in its quad, or null if it is no border edge. */
  borderEdge(a: number, b: number): Edge | null {
    if (!this.net) return null;
    return (
      borderEdges(this.net).find(
        (edge) => (edge.a === a && edge.b === b) || (edge.a === b && edge.b === a),
      ) ?? null
    );
  }

  /** Highlight the edge under the pointer (null: none). */
  setHoverEdge(edge: Edge | null): void {
    const current = this.hoverEdge;
    const same = edge && current ? edge.a === current.a && edge.b === current.b : edge === current;
    if (same) return;
    this.hoverEdge = edge;
    this.drawGuides();
  }

  /** The border edges a drag of `edge` extends: it alone, or its whole border chain. */
  extrusionChain(edge: Edge, whole: boolean): Edge[] {
    return whole && this.net ? borderChain(this.net, edge) : [edge];
  }

  /** Show the row an extrusion by `offset` would add (null clears the preview). */
  previewExtrusion(chain: readonly Edge[] | null, offset: Vec3): void {
    const segments: number[] = [];
    for (const { a, b } of chain ?? []) {
      const [pa, pb] = [this.limitPoint(a), this.limitPoint(b)];
      const [qa, qb] = [this.extrudedPoint(a, offset), this.extrudedPoint(b, offset)];
      segments.push(...pa, ...qa, ...qa, ...qb, ...qb, ...pb);
    }
    this.extrusionPreview = segments;
    this.drawGuides();
  }

  /** Add a row of quads along border edges, moved by `offset`, and snap it to the scan. */
  async extrude(chain: readonly Edge[], offset: Vec3): Promise<void> {
    const net = this.net;
    this.extrusionPreview = [];
    this.drawGuides();
    if (!net || this.state.job || chain.length === 0) return;
    const result = extrudeEdges(net, chain, (vertex) => this.extrudedPoint(vertex, offset));
    await this.settle(result.net, result.added);
  }

  /** Split the ring of quads crossing an edge with a new loop, snapped to the scan. */
  async split(edge: Edge): Promise<void> {
    const net = this.net;
    if (!net || this.state.job) return;
    const result = splitRing(net, edge.a, edge.b);
    if (result.added.length === 0) return;
    await this.settle(result.net, result.added);
  }

  /** Show a changed net, then snap its new points to the scan: one undo step. */
  private async settle(net: Net, added: readonly number[]): Promise<void> {
    await this.setNet(net, false);
    this.choose(added, 'replace');
    const fitted = await this.fit(false);
    if (!fitted && this.net) {
      this.history.push(this.net);
      this.syncHistory();
    }
  }

  /** A border point moved by `offset`, onto the scan when snapping. */
  private extrudedPoint(vertex: number, offset: Vec3): Vec3 {
    const [x, y, z] = this.limitPoint(vertex);
    const moved: Vec3 = [x + offset[0], y + offset[1], z + offset[2]];
    if (!this.state.snap) return moved;
    return this.viewport.scanSurface.closest(moved, Infinity)?.point ?? moved;
  }

  private drawGuides(): void {
    if (this.detached) return;
    if (!this.guides) this.guides = new GuideOverlay(this.viewport.createOverlay());
    const segments: number[] = [...this.extrusionPreview];
    const points: number[] = [];
    const corners = this.facePoints.map((clicked) => clicked.point);
    if (this.facePreview && this.state.facing) corners.push(this.facePreview);
    corners.forEach((corner, i) => {
      points.push(...corner);
      const next = corners[i + 1] ?? (corners.length === 4 ? corners[0] : undefined);
      if (next) segments.push(...corner, ...next);
    });
    if (this.hoverEdge && this.surface && !this.state.facing) {
      segments.push(...this.limitPoint(this.hoverEdge.a), ...this.limitPoint(this.hoverEdge.b));
    }
    this.guides.show(segments, points);
    this.viewport.invalidate();
  }

  // Dragging ----------------------------------------------------------------------------------

  /** Start moving the chosen control points (the grabbed one is chosen first if needed). */
  beginDrag(grabbed: number): boolean {
    const surface = this.surface;
    const net = this.net;
    if (!surface || !net || this.state.job) return false;
    if (!this.selection.has(grabbed)) this.choose([grabbed], 'replace');
    const controls = Uint32Array.from(this.selection);
    const startLimits = new Float64Array(controls.length * 3);
    controls.forEach((control, index) => startLimits.set(surface.limitPoint(control), index * 3));
    this.drag = {
      controls,
      rows: surface.rowsOf(controls),
      startVertices: net.vertices.slice(),
      startLimits,
    };
    return true;
  }

  /**
   * Move the surface points of the dragged control points by `offset`. With snapping
   * (and not `alongNormal`), each moved surface point lands on the nearest scan point.
   */
  dragBy(offset: Vec3, alongNormal: boolean): void {
    const drag = this.drag;
    const surface = this.surface;
    const net = this.net;
    if (!drag || !surface || !net) return;
    const wanted = new Float64Array(drag.controls.length * 3);
    drag.controls.forEach((_, index) => {
      const o = index * 3;
      let x = (drag.startLimits[o] ?? 0) + offset[0];
      let y = (drag.startLimits[o + 1] ?? 0) + offset[1];
      let z = (drag.startLimits[o + 2] ?? 0) + offset[2];
      if (this.state.snap && !alongNormal) {
        const hit = this.viewport.scanSurface.closest([x, y, z], Infinity);
        if (hit) [x, y, z] = hit.point;
      }
      wanted[o] = x - (drag.startLimits[o] ?? 0);
      wanted[o + 1] = y - (drag.startLimits[o + 1] ?? 0);
      wanted[o + 2] = z - (drag.startLimits[o + 2] ?? 0);
    });
    const offsets = controlOffsets(surface, drag.controls, wanted);
    net.vertices.set(drag.startVertices);
    drag.controls.forEach((control, index) => {
      for (let axis = 0; axis < 3; axis += 1) {
        const c = control * 3 + axis;
        net.vertices[c] = (drag.startVertices[c] ?? 0) + (offsets[index * 3 + axis] ?? 0);
      }
    });
    this.refreshRows(drag.rows);
  }

  /** Finish the drag: keep it (a draft history step) or put the points back. */
  endDrag(keep: boolean): void {
    const drag = this.drag;
    const net = this.net;
    this.drag = null;
    if (!drag || !net) return;
    if (!keep) {
      net.vertices.set(drag.startVertices);
      this.refreshRows(drag.rows);
      return;
    }
    this.history.push(net);
    this.syncHistory();
    this.update({ summary: this.summary() });
  }

  get dragging(): boolean {
    return this.drag !== null;
  }

  /** Show the net again after `detach` (the panel's effect ran again). */
  attach(): void {
    if (!this.detached) return;
    this.detached = false;
    if (this.surface && this.net) {
      this.overlay = new NetOverlay(this.viewport.createOverlay(), this.surface);
      this.overlay.positionsChanged();
      this.repaintPoints();
      void this.measureAll();
    }
  }

  /** Remove the net from the viewport and stop running work; the draft is kept. */
  detach(): void {
    this.detached = true;
    this.measureToken += 1;
    this.drag = null;
    this.running?.cancel();
    this.overlay?.dispose();
    this.overlay = null;
    this.guides?.dispose();
    this.guides = null;
  }

  // Internals ---------------------------------------------------------------------------------

  private async run<M extends MethodName>(
    kind: NetJobKind,
    method: M,
    params: ParamsOf<M>,
  ): Promise<ResultOf<M> | null> {
    this.running?.cancel();
    const job = kernel().call(method, params, { lane: `${method}:${FREEFORM_NET_TOOL_ID}` });
    this.running = job;
    this.update({ job: { kind, fraction: null, stage: null }, error: null });
    job.onProgress((fraction, stage) => {
      if (this.running === job) this.update({ job: { kind, fraction, stage } });
    });
    try {
      return await job.result;
    } catch (error) {
      if (this.running === job && !isSilentFailure(error)) this.update({ error: toFailure(error) });
      return null;
    } finally {
      if (this.running === job) {
        this.running = null;
        if (!this.detached) this.update({ job: null });
      }
    }
  }

  /** Show a net: a new limit map when the quads changed, then positions and heatmap. */
  private async setNet(net: Net, record: boolean): Promise<void> {
    if (this.detached) return;
    const topologyChanged = !this.net || !this.surface || !sameTopology(this.net, net);
    if (topologyChanged) {
      const map = await this.run('map', 'net.limitMap', {
        quads: net.quads,
        vertexCount: net.vertices.length / 3,
      });
      if (!map || this.detached) return;
      this.overlay?.dispose();
      this.surface = new LimitSurface(map, net.vertices.length / 3);
      this.overlay = new NetOverlay(this.viewport.createOverlay(), this.surface);
      this.distances = new Float32Array(this.surface.fineCount).fill(Number.NaN);
      this.colors = new Float32Array(this.surface.fineCount * 3);
      for (const control of [...this.selection]) {
        if (control >= this.surface.controlCount) this.selection.delete(control);
      }
      this.hover = null;
      this.hoverEdge = null;
    }
    this.net = cloneNet(net);
    const surface = this.surface as LimitSurface;
    surface.evaluate(this.net.vertices);
    this.overlay?.positionsChanged();
    this.repaintPoints();
    if (record) {
      this.history.push(this.net);
      this.syncHistory();
    }
    const { map } = surface;
    this.update({
      hasNet: true,
      quads: this.net.quads.length / 4,
      faces: map.faceCount,
      controlPoints: surface.controlCount,
      irregular: irregularCount(map.edges, map.boundaryEdges, surface.controlCount),
      closed: !map.boundaryEdges.some((flag) => flag !== 0),
      selected: this.selection.size,
    });
    this.viewport.invalidate();
    await this.measureAll();
  }

  /** Recompute positions, distances and colours of some dense vertices (during a drag). */
  private refreshRows(rows: Uint32Array): void {
    const surface = this.surface;
    const net = this.net;
    if (!surface || !net) return;
    surface.evaluateRows(net.vertices, rows);
    const measured = this.viewport.scanSurface.distances(
      surface.positions,
      this.distances,
      this.scale.range * SEARCH_FACTOR,
      rows,
    );
    if (measured) colorize(this.distances, this.scale, this.colors, rows);
    this.overlay?.positionsChanged();
    if (this.state.heatmap) this.overlay?.setSurfaceColors(this.colors);
    this.viewport.invalidate();
  }

  /** Measure every dense vertex against the scan, a chunk per frame. */
  private async measureAll(): Promise<void> {
    const token = ++this.measureToken;
    const surface = this.surface;
    if (!surface) return;
    await this.viewport.scanTopology().catch(() => undefined);
    for (let start = 0; start < surface.fineCount; start += MEASURE_CHUNK) {
      if (token !== this.measureToken || this.surface !== surface) return;
      const end = Math.min(surface.fineCount, start + MEASURE_CHUNK);
      const rows = Uint32Array.from({ length: end - start }, (_, i) => start + i);
      if (
        !this.viewport.scanSurface.distances(
          surface.positions,
          this.distances,
          this.scale.range * SEARCH_FACTOR,
          rows,
        )
      )
        return;
      colorize(this.distances, this.scale, this.colors, rows);
      if (this.state.heatmap) this.overlay?.setSurfaceColors(this.colors);
      this.viewport.invalidate();
      await nextFrame();
    }
    if (token === this.measureToken) this.update({ summary: this.summary() });
  }

  private summary(): DeviationSummary {
    return deviationSummary(this.distances, this.scale.tolerance);
  }

  private repaintPoints(): void {
    this.overlay?.paintPoints(this.selection, this.hover, (control) => this.nearby.has(control));
    this.viewport.invalidate();
  }

  private syncHistory(): void {
    this.update({ canUndo: this.history.canUndo, canRedo: this.history.canRedo });
  }
}
