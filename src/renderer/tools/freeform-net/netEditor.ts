// The freeform-net tool's working state outside React: the draft net, its dense
// limit surface and viewport overlay, the draft history, and the kernel requests that
// generate, fit and map the net. The chosen and pinned points are NetPoints', measuring
// against the scan NetMeasure's, building by hand NetBuilder's, dragging points
// NetPointDrag's, running kernel requests NetJobs'. The panel subscribes for its
// numbers; a drag only touches the viewport, never React.

import type { ScreenPoint, Vec3, Viewport } from '../../viewport/api';
import { LimitSurface } from './limitSurface';
import { type Edge, borderEdges } from './netTopology';
import { netAutomationInfo } from './netAutomation';
import { NetBuilder } from './netBuilder';
import { NetJobs } from './netJobs';
import { NetMeasure } from './netMeasure';
import {
  type Net,
  NetHistory,
  cloneNet,
  fitPlane,
  irregularPoints,
  projectOntoPlane,
  sameTopology,
} from './netModel';
import { NetOverlay } from './NetOverlay';
import { carriedPins, fixedMask, holdPinned, pinnedLimits } from './netPins';
import { NetPointDrag } from './netPointDrag';
import { type ChooseMode, NetPoints } from './netPoints';
import { type NetEditorState, initialNetState } from './netState';

export type { NetEditorState, NetJobKind } from './netState';

export const FREEFORM_NET_TOOL_ID = 'freeform-net';
/** Fairness of "Snap to scan" and the stronger one of "Smooth" (kernel `net.fit`). */
export const SNAP_SMOOTHING = 0.002;
export const SMOOTH_SMOOTHING = 0.05;
const FIT_ITERATIONS = 4;
/** Points whose surface faces away from the viewer more than this cannot be picked. */
const FACING_LIMIT = 0.15;

export class NetEditor {
  private state: NetEditorState;
  private readonly listeners = new Set<() => void>();
  private net: Net | null = null;
  private surface: LimitSurface | null = null;
  private overlay: NetOverlay | null = null;
  private readonly measure: NetMeasure;
  private readonly points = new NetPoints();
  private readonly history = new NetHistory();
  private readonly jobs: NetJobs;
  private detached = false;
  /** Building by hand: faces by clicks, chosen edges, rows dragged out of the border. */
  readonly build: NetBuilder;
  /** Moving chosen control points with the pointer. */
  readonly pointDrag: NetPointDrag;
  /** Scan triangles the net belongs to (fitting uses them); null = the whole scan. */
  faces: Uint32Array | null = null;

  constructor(
    private readonly viewport: Viewport,
    tolerance: number,
  ) {
    this.measure = new NetMeasure(viewport, tolerance);
    this.state = initialNetState(this.measure.tolerance);
    this.jobs = new NetJobs(
      FREEFORM_NET_TOOL_ID,
      (patch) => this.update(patch),
      () => !this.detached,
    );
    this.build = new NetBuilder({
      viewport,
      net: () => this.net,
      limitPoint: (control) => this.limitPoint(control),
      screenOf: (control) => this.visibleScreen(control),
      chosenPoints: () => this.points.chosen,
      busy: () => this.state.job !== null,
      snap: () => this.state.snap,
      shown: () => !this.detached,
      update: (patch) => this.update(patch),
      record: (net) => this.setNet(net, true),
      settle: (net, added) => this.settle(net, added),
    });
    this.pointDrag = new NetPointDrag({
      viewport,
      net: () => this.net,
      surface: () => (this.state.job ? null : this.surface),
      selection: () => this.points.chosen,
      pinned: () => this.points.pinned,
      snap: () => this.state.snap,
      keepNeighbours: () => this.state.keepNeighbours,
      strength: () => this.state.strength,
      refreshRows: (rows) => this.refreshRows(rows),
      record: () => this.recordCurrent(),
      dropped: (controls) => controls.length === 1 && this.build.edits.weldOnto(controls[0] ?? 0),
    });
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
    const result = await this.jobs.run('generate', 'net.generate', { faces, targetQuads });
    if (!result) return;
    this.faces = faces;
    this.points.setPinned([]);
    await this.setNet({ vertices: result.vertices, quads: result.quads }, true);
  }

  async load(featureId: string): Promise<void> {
    const result = await this.jobs.run('load', 'net.featureNet', { featureId });
    if (!result) return;
    this.faces = result.faces;
    await this.setNet({ vertices: result.vertices, quads: result.quads }, false, []);
    this.history.reset(this.net);
    this.syncHistory();
  }

  /**
   * Snap the net to the scan; with chosen points only those move ("Smooth": fairer).
   * Pinned points stay. Returns whether the fitted net was shown (and recorded).
   */
  async fit(smooth: boolean): Promise<boolean> {
    const net = this.net;
    if (!net) return false;
    const result = await this.jobs.run(smooth ? 'smooth' : 'fit', 'net.fit', {
      vertices: net.vertices,
      quads: net.quads,
      faces: this.faces,
      fixed: fixedMask(net.vertices.length / 3, this.points.pinned, this.points.chosen),
      smoothing: smooth ? SMOOTH_SMOOTHING : SNAP_SMOOTHING,
      iterations: FIT_ITERATIONS,
    });
    if (!result) return false;
    await this.setNet({ vertices: result.vertices, quads: net.quads }, true);
    return true;
  }

  /**
   * Lay the chosen control points (not the pinned ones) on their best-fitting plane.
   * Where a region of the net and the ring of points around it are coplanar, its limit
   * surface is exactly that plane (affine invariance of subdivision), so flat faces
   * become truly flat.
   */
  async flatten(): Promise<void> {
    const net = this.net;
    const surface = this.surface;
    const chosen = [...this.points.chosen].filter((control) => !this.points.pinned.has(control));
    if (!net || !surface || chosen.length < 3 || this.state.job) return;
    const plane = fitPlane(pinnedLimits(surface, chosen));
    if (!plane) return;
    const next = cloneNet(net);
    projectOntoPlane(next.vertices, chosen, plane);
    await this.setNet(next, true);
  }

  cancelJob(): void {
    this.jobs.cancel();
  }

  undo(): boolean {
    const step = this.history.undo();
    if (!step) return false;
    void this.setNet(step.net, false, step.pinned);
    return true;
  }

  redo(): boolean {
    const step = this.history.redo();
    if (!step) return false;
    void this.setNet(step.net, false, step.pinned);
    return true;
  }

  /** Q: smooth the chosen chain (or the chosen points) while it stays on the scan. */
  async smoothChosen(): Promise<void> {
    const edges = this.build.chosenEdges();
    if (edges.length > 0)
      this.choose(
        edges.flatMap(({ a, b }) => [a, b]),
        'replace',
      );
    if (this.points.chosen.size > 0) await this.fit(true);
  }

  // Options -------------------------------------------------------------------------------

  /** Snapping, "Don't move neighbours" and the drag strength. */
  setDragOptions(options: Partial<Pick<NetEditorState, 'snap' | 'keepNeighbours' | 'strength'>>) {
    this.update(options);
  }

  /** Space: show only the surface, or the net on it again. */
  setNetVisible(netVisible: boolean): void {
    this.overlay?.setNetVisible(netVisible);
    this.viewport.invalidate();
    this.update({ netVisible });
  }

  setHeatmap(heatmap: boolean): void {
    this.overlay?.setSurfaceColors(heatmap ? this.measure.colors : null);
    this.viewport.invalidate();
    this.update({ heatmap });
  }

  setTolerance(tolerance: number): void {
    if (!this.measure.setTolerance(tolerance)) return;
    this.update({ tolerance });
    void this.measureAll();
  }

  get tolerance(): number {
    return this.measure.tolerance;
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

  /** Screen position of a control point, or null if it faces away from the viewer. */
  visibleScreen(control: number): ScreenPoint | null {
    const screen = this.viewport.worldToScreen(this.limitPoint(control));
    if (!screen) return null;
    const ray = this.viewport.screenToRay(screen).direction;
    const normal = this.normalAt(control);
    const away = normal[0] * ray[0] + normal[1] * ray[1] + normal[2] * ray[2];
    return away > FACING_LIMIT ? null : screen;
  }

  isSelected(control: number): boolean {
    return this.points.chosen.has(control);
  }

  isPinned(control: number): boolean {
    return this.points.pinned.has(control);
  }

  /** Replace, extend or reduce the chosen control points. */
  choose(controls: Iterable<number>, mode: ChooseMode): void {
    this.points.choose(controls, mode);
    this.repaintPoints();
    this.update(this.points.counts());
  }

  chooseAll(): void {
    this.choose(
      Array.from({ length: this.controlCount }, (_, i) => i),
      'replace',
    );
  }

  /** Pin the chosen points (then no longer chosen), or release them: one draft step. */
  pinChosen(pin: boolean): void {
    if (!this.net || this.state.job || !this.points.pinChosen(pin)) return;
    if (pin) this.points.choose([], 'replace');
    this.repaintPoints();
    this.recordCurrent();
  }

  setHover(control: number | null, nearby?: Iterable<number>): void {
    if (this.points.setHover(control, nearby)) this.repaintPoints();
  }

  // The net's edges -------------------------------------------------------------------------

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

  /** The net for automation clients: counts, border edges, chosen and pinned points. */
  automationInfo(): unknown {
    return netAutomationInfo({
      tool: FREEFORM_NET_TOOL_ID,
      net: this.surface ? this.net : null,
      state: this.state,
      border: () => this.build.automationBorder(),
      chosen: this.points.chosen,
      pinned: this.points.pinned,
      limitPoint: (control) => this.limitPoint(control),
      screenOf: (control) => this.visibleScreen(control),
    });
  }

  /** Points or rows are being dragged (no OK meanwhile). */
  get dragging(): boolean {
    return this.pointDrag.active || this.build.draggingRows;
  }

  // Lifecycle -------------------------------------------------------------------------------

  /** Show the net again after `detach` (the panel's effect ran again). */
  attach(): void {
    if (!this.detached) return;
    this.detached = false;
    if (this.surface && this.net) {
      this.overlay = new NetOverlay(this.viewport.createOverlay(), this.surface);
      this.overlay.positionsChanged();
      this.overlay.setNetVisible(this.state.netVisible);
      this.repaintPoints();
      void this.measureAll();
    }
  }

  /** Remove the net from the viewport and stop running work; the draft is kept. */
  detach(): void {
    this.detached = true;
    this.measure.cancel();
    this.pointDrag.end(false);
    this.jobs.cancel();
    this.overlay?.dispose();
    this.overlay = null;
    this.build.dispose();
  }

  // Internals ---------------------------------------------------------------------------------

  /** Show a changed net, then snap its new points to the scan: one undo step. */
  private async settle(net: Net, added: readonly number[]): Promise<void> {
    await this.setNet(net, false);
    this.choose(added, 'replace');
    const fitted = await this.fit(false);
    if (!fitted) this.recordCurrent();
  }

  /** The current net becomes a draft history step (after a drag or a build step). */
  private recordCurrent(): void {
    if (!this.net) return;
    this.history.push(this.net, [...this.points.pinned]);
    this.syncHistory();
    this.update({ summary: this.measure.summary(), ...this.points.counts() });
  }

  /**
   * Show a net: a new limit map when the quads changed, then positions and heatmap.
   * `pinned` comes with a history step; else the pins follow from the current net and
   * their points are held where they were.
   */
  private async setNet(net: Net, record: boolean, pinned?: readonly number[]): Promise<void> {
    if (this.detached) return;
    const previous = this.net;
    const { pins, anchors } = pinned
      ? { pins: [...pinned], anchors: null }
      : carriedPins(this.surface, previous, net, [...this.points.pinned]);
    if (net.quads.length === 0) {
      this.showEmpty(net, record);
      return;
    }
    const topologyChanged = !previous || !this.surface || !sameTopology(previous, net);
    if (topologyChanged) {
      const map = await this.jobs.run('map', 'net.limitMap', {
        quads: net.quads,
        vertexCount: net.vertices.length / 3,
      });
      if (!map || this.detached) return;
      this.overlay?.dispose();
      this.surface = new LimitSurface(map, net.vertices.length / 3);
      this.overlay = new NetOverlay(this.viewport.createOverlay(), this.surface);
      this.overlay.setNetVisible(this.state.netVisible);
      this.measure.reset(this.surface);
      const count = this.surface.controlCount;
      this.points.renumbered(count, irregularPoints(map.edges, map.boundaryEdges, count));
    }
    this.net = cloneNet(net);
    const surface = this.surface as LimitSurface;
    surface.evaluate(this.net.vertices);
    this.points.setPinned(pins);
    if (anchors) holdPinned(surface, this.net.vertices, pins, anchors);
    this.overlay?.positionsChanged();
    if (topologyChanged) this.build.topologyChanged(this.net);
    this.repaintPoints();
    if (record) {
      this.history.push(this.net, [...this.points.pinned]);
      this.syncHistory();
    }
    const { map } = surface;
    this.update({
      hasNet: true,
      quads: this.net.quads.length / 4,
      faces: map.faceCount,
      controlPoints: surface.controlCount,
      irregular: this.points.irregularCount,
      closed: !map.boundaryEdges.some((flag) => flag !== 0),
      ...this.points.counts(),
    });
    this.viewport.invalidate();
    await this.measureAll();
  }

  /** Everything deleted: no surface; placing a first face starts again (undoable). */
  private showEmpty(net: Net, record: boolean): void {
    this.measure.cancel();
    this.overlay?.dispose();
    this.overlay = null;
    this.surface = null;
    this.net = cloneNet(net);
    this.points.renumbered(0, []);
    this.build.topologyChanged(this.net);
    if (record) {
      this.history.push(this.net);
      this.syncHistory();
    }
    const counts = { quads: 0, faces: 0, controlPoints: 0, irregular: 0 };
    this.update({ hasNet: false, summary: null, ...counts, ...this.points.counts() });
    this.build.setFacing(true);
    this.viewport.invalidate();
  }

  /** Recompute positions, distances and colours of some dense vertices (during a drag). */
  private refreshRows(rows: Uint32Array): void {
    const surface = this.surface;
    const net = this.net;
    if (!surface || !net) return;
    surface.evaluateRows(net.vertices, rows);
    this.measure.rows(surface, rows);
    this.overlay?.positionsChanged();
    if (this.state.heatmap) this.overlay?.setSurfaceColors(this.measure.colors);
    this.viewport.invalidate();
  }

  /** Measure every dense vertex against the scan, a chunk per frame. */
  private async measureAll(): Promise<void> {
    const surface = this.surface;
    if (!surface) return;
    const summary = await this.measure.all(surface, () => {
      if (this.state.heatmap) this.overlay?.setSurfaceColors(this.measure.colors);
      this.viewport.invalidate();
    });
    if (summary) this.update({ summary });
  }

  private repaintPoints(): void {
    this.points.paint(this.overlay);
    this.viewport.invalidate();
  }

  private syncHistory(): void {
    this.update({ canUndo: this.history.canUndo, canRedo: this.history.canRedo });
  }
}
