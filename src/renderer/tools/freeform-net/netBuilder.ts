// Building the net by hand, as in QuickSurface: a face from four clicked corners or a
// rectangle from two, chosen edges (a double click takes a whole chain), and new rows
// duplicated out of border edges by drag and drop: from the "D" grip shown beside every
// open border edge, or with Alt (RowDrag drops them onto the scan, or onto border
// points of the net to join pieces). Where a dropped point joins or welds onto
// another one, both are marked and linked. One-step edits (split, bridge, ...) are
// NetEdits'.

import type { ScreenPoint, Vec3, Viewport } from '../../viewport/api';
import { GuideOverlay } from './GuideOverlay';
import { addQuad, extrudeEdges } from './netBuild';
import { NetEdits } from './netEdits';
import { FacePlacement, type FaceMode, type ScanCorner, outwardOf } from './netFacePlacement';
import type { Net } from './netModel';
import { RowDrag, joinableBorder, nearestJoin } from './netRows';
import type { NetEditorState } from './netState';
import { type Edge, borderEdges, borderRuns, edgeKey, edgeLoop, edgeQuads } from './netTopology';

/** The "D" grip of a border edge sits this far out from its middle, in parts of its length. */
const HANDLE_OFFSET = 0.4;
/** The grip is under the pointer within this distance. */
const HANDLE_PICK_PX = 10;

/** What the builder needs of the editor that owns the net. */
export interface BuildHost {
  readonly viewport: Viewport;
  net(): Net | null;
  limitPoint(control: number): Vec3;
  /** Screen position of a control point, or null if it faces away from the viewer. */
  screenOf(control: number): ScreenPoint | null;
  chosenPoints(): ReadonlySet<number>;
  /** A kernel job runs; nothing is built meanwhile. */
  busy(): boolean;
  snap(): boolean;
  /** The tool is shown, so guides may be drawn. */
  shown(): boolean;
  update(
    patch: Partial<Pick<NetEditorState, 'facing' | 'faceMode' | 'facePoints' | 'chosenEdges'>>,
  ): void;
  /** Show a net as one undo step. */
  record(net: Net): Promise<void>;
  /** Show a net, then snap its new points to the scan: one undo step. */
  settle(net: Net, added: readonly number[]): Promise<void>;
}

export type ChoiceMode = 'replace' | 'add' | 'remove' | 'toggle';

export class NetBuilder {
  private readonly face = new FacePlacement();
  private hoverEdge: Edge | null = null;
  private readonly chosen = new Map<string, Edge>();
  private readonly rows: RowDrag;
  private guides: GuideOverlay | null = null;
  /** A dragged border point and the border point it would be welded onto. */
  private weld: { from: number; into: number } | null = null;
  /** Split, bridge, increase resolution, weld, delete. */
  readonly edits: NetEdits;

  constructor(private readonly host: BuildHost) {
    this.rows = new RowDrag(host);
    this.edits = new NetEdits(host, {
      edges: () => this.chosenEdges(),
      clear: () => this.chosen.clear(),
    });
  }

  // A new face ----------------------------------------------------------------------------

  /** Start (in a mode) or stop placing a face. */
  setFacing(facing: boolean, mode: FaceMode = this.face.mode): void {
    this.face.set(facing, mode);
    this.host.update({ facing, faceMode: mode, facePoints: 0 });
    this.draw();
  }

  get faceMode(): FaceMode {
    return this.face.mode;
  }

  /** The first corner of a rectangle, clicked on screen (or null before). */
  get rectangleAnchor(): ScreenPoint | null {
    return this.face.anchor;
  }

  setRectangleAnchor(at: ScreenPoint): void {
    this.face.anchor = at;
    this.host.update({ facePoints: 1 });
    this.draw();
  }

  /** A clicked corner on the scan; the fourth one adds the face. */
  async addFacePoint(corner: ScanCorner): Promise<void> {
    if (!this.face.active || this.host.busy()) return;
    const corners = this.face.click(corner);
    this.host.update({ facePoints: this.face.count });
    this.draw();
    if (corners) await this.addFace(corners);
  }

  /** Add a face with these four corners on the scan. */
  async addFace(corners: ScanCorner[]): Promise<void> {
    if (corners.length !== 4 || this.host.busy()) return;
    this.setFacing(false);
    const points = corners.map((corner) => corner.point);
    const shared = corners.map((corner) => corner.vertex ?? null);
    const next = addQuad(this.host.net(), points, outwardOf(corners), shared);
    if (next) await this.host.record(next);
  }

  /** Take back the last clicked corner; false if there was none. */
  removeFacePoint(): boolean {
    if (!this.face.undo()) return false;
    this.host.update({ facePoints: this.face.count });
    this.draw();
    return true;
  }

  /** The corner under the pointer while placing a face (rubber band), or null. */
  previewFacePoint(corner: ScanCorner | null): void {
    this.face.hover(corner);
    this.draw();
  }

  /** The rectangle the second click would add (corners on the scan), or null. */
  previewRectangle(corners: Vec3[] | null): void {
    this.face.hoverRectangle(corners);
    this.draw();
  }

  // Chosen edges and the grip -------------------------------------------------------------

  setHoverEdge(edge: Edge | null): void {
    const current = this.hoverEdge;
    const same =
      edge && current
        ? edgeKey(edge.a, edge.b) === edgeKey(current.a, current.b)
        : !edge && !current;
    if (same) return;
    this.hoverEdge = edge;
    this.draw();
  }

  /**
   * The border edge whose "D" grip is under the pointer (it becomes the hovered one).
   * A pointer nearer to the edge itself grabs the edge, so a short grip never takes
   * over a plain drag.
   */
  handleAt(at: ScreenPoint): Edge | null {
    let best: Edge | null = null;
    let bestDistance = HANDLE_PICK_PX;
    for (const { edge, grip } of this.grips()) {
      const { viewport } = this.host;
      const screen = viewport.worldToScreen(grip);
      const distance = screen ? Math.hypot(screen.x - at.x, screen.y - at.y) : Infinity;
      const [a, b] = [this.host.screenOf(edge.a), this.host.screenOf(edge.b)];
      if (a && b && segmentDistance(at, a, b) < distance) continue;
      if (distance <= bestDistance) {
        best = edge;
        bestDistance = distance;
      }
    }
    if (best) this.setHoverEdge(best);
    return best;
  }

  /** The grips of the visible open border edges, while the net is being edited. */
  private grips(): { edge: Edge; grip: Vec3 }[] {
    const net = this.host.net();
    if (!net || this.face.active || this.rows.active) return [];
    const count = net.vertices.length / 3;
    const grips: { edge: Edge; grip: Vec3 }[] = [];
    const quadsOf = edgeQuads(net);
    for (const edge of borderEdges(net)) {
      if (edge.a >= count || edge.b >= count) continue;
      if (!this.host.screenOf(edge.a) || !this.host.screenOf(edge.b)) continue;
      const grip = this.handleOf(edge, quadsOf);
      if (grip) grips.push({ edge, grip });
    }
    return grips;
  }

  isChosen(edge: Edge): boolean {
    return this.chosen.has(edgeKey(edge.a, edge.b));
  }

  chooseEdges(edges: readonly Edge[], mode: ChoiceMode): void {
    if (mode === 'replace') this.chosen.clear();
    for (const edge of edges) {
      const id = edgeKey(edge.a, edge.b);
      if (mode === 'remove' || (mode === 'toggle' && this.chosen.has(id))) this.chosen.delete(id);
      else this.chosen.set(id, edge);
    }
    this.host.update({ chosenEdges: this.chosen.size });
    this.draw();
  }

  chosenEdges(): Edge[] {
    return [...this.chosen.values()];
  }

  /** The chain a double click on `edge` takes (border side, or edge loop). */
  chainOf(edge: Edge): Edge[] {
    const net = this.host.net();
    return net ? edgeLoop(net, edge) : [edge];
  }

  // Rows by drag and drop ------------------------------------------------------------------

  /**
   * Start duplicating border edges into new rows: every chosen border edge if `edge` is
   * chosen, else `edge` alone (which becomes the choice). False if it is no border.
   */
  /**
   * Start dragging rows out of the grabbed edge (and the chosen ones), pressed at
   * `press`: the grabbed edge's middle goes where the pointer is, so a row dropped
   * from the grip lands under the pointer, not a grip's length behind it.
   */
  beginRows(edge: Edge, press: ScreenPoint): boolean {
    const net = this.host.net();
    if (!net || this.host.busy()) return false;
    if (!this.isChosen(edge)) this.chooseEdges([edge], 'replace');
    const [a, b] = [this.host.screenOf(edge.a), this.host.screenOf(edge.b)];
    const lead = a && b ? { x: press.x - (a.x + b.x) / 2, y: press.y - (a.y + b.y) / 2 } : null;
    return this.rows.begin(borderRuns(net, this.chosenEdges()), lead ?? { x: 0, y: 0 });
  }

  /** The pointer moved by `delta` (screen pixels) since the drag began. */
  dragRows(delta: ScreenPoint): void {
    this.rows.move(delta);
    this.draw();
  }

  /** Drop the rows (add them and snap their new points to the scan) or cancel them. */
  async endRows(keep: boolean): Promise<void> {
    const drop = keep ? this.rows.finish() : null;
    this.rows.cancel();
    this.draw();
    const net = this.host.net();
    if (!drop || !net || this.host.busy()) return;
    let next = net;
    const added: number[] = [];
    for (const run of drop.runs) {
      const row = extrudeEdges(next, run, drop.target);
      next = row.net;
      added.push(...row.added);
    }
    this.chosen.clear();
    if (added.length > 0) await this.host.settle(next, added);
    else await this.host.record(next);
  }

  get draggingRows(): boolean {
    return this.rows.active;
  }

  /** While a single point is dragged: the border point it would be welded onto. */
  previewWeld(control: number | null): void {
    const net = this.host.net();
    const screen = control === null ? null : this.host.screenOf(control);
    let next: { from: number; into: number } | null = null;
    if (net && control !== null && screen) {
      const into = nearestJoin(
        joinableBorder(net, (v) => this.host.screenOf(v), new Set([control])),
        screen,
      );
      const onBorder = borderEdges(net).some(({ a, b }) => a === control || b === control);
      if (into !== null && onBorder) next = { from: control, into };
    }
    if (next?.into === this.weld?.into && next?.from === this.weld?.from) return;
    this.weld = next;
    this.draw();
  }

  // Upkeep ---------------------------------------------------------------------------------

  /** The net's quads changed: forget edges it no longer has. */
  topologyChanged(net: Net): void {
    const present = edgeQuads(net);
    for (const id of [...this.chosen.keys()]) if (!present.has(id)) this.chosen.delete(id);
    this.hoverEdge = null;
    this.host.update({ chosenEdges: this.chosen.size });
    this.draw();
  }

  /** The border edges with their middles on screen, for automation clients. */
  automationBorder(): unknown[] {
    const net = this.host.net();
    if (!net) return [];
    return borderEdges(net).map((edge) => {
      const [a, b] = [this.host.limitPoint(edge.a), this.host.limitPoint(edge.b)];
      const middle: Vec3 = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2];
      const grip = this.handleOf(edge);
      return {
        edge,
        middle,
        screen: this.host.viewport.worldToScreen(middle),
        handle: grip ? this.host.viewport.worldToScreen(grip) : null,
        chosen: this.isChosen(edge),
      };
    });
  }

  dispose(): void {
    this.rows.cancel();
    this.guides?.dispose();
    this.guides = null;
  }

  /** Where the "D" grip of a border edge sits: a little outside it, away from its quad. */
  private handleOf(edge: Edge, quadsOf?: ReturnType<typeof edgeQuads>): Vec3 | null {
    const net = this.host.net();
    const map = quadsOf ?? (net ? edgeQuads(net) : undefined);
    const users = map?.get(edgeKey(edge.a, edge.b));
    const quad = users?.length === 1 ? users[0]?.quad : undefined;
    if (!net || quad === undefined) return null;
    const corners = [0, 1, 2, 3].map((k) => this.host.limitPoint(net.quads[quad * 4 + k] ?? 0));
    const [a, b] = [this.host.limitPoint(edge.a), this.host.limitPoint(edge.b)];
    const middle: Vec3 = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2];
    const outward = [0, 1, 2].map(
      (axis) => (middle[axis] ?? 0) - corners.reduce((sum, p) => sum + (p[axis] ?? 0), 0) / 4,
    );
    const depth = Math.hypot(...outward);
    if (depth < 1e-9) return null;
    const reach = (Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]) * HANDLE_OFFSET) / depth;
    return [
      middle[0] + (outward[0] ?? 0) * reach,
      middle[1] + (outward[1] ?? 0) * reach,
      middle[2] + (outward[2] ?? 0) * reach,
    ];
  }

  private draw(): void {
    if (!this.host.shown()) return;
    if (!this.guides) this.guides = new GuideOverlay(this.host.viewport.createOverlay());
    const net = this.host.net();
    const count = net ? net.vertices.length / 3 : 0;
    const point = (vertex: number) => this.host.limitPoint(vertex);
    const rows = this.rows.preview();
    const face = this.face.preview();
    const segments = [...rows.segments, ...face.segments];
    const points = [...face.points];
    const joins = [...rows.points, ...face.joins];
    if (this.weld) {
      const [from, into] = [point(this.weld.from), point(this.weld.into)];
      joins.push(...into);
      segments.push(...from, ...into);
    }
    const known = (edge: Edge) => edge.a < count && edge.b < count;
    const hover =
      this.hoverEdge && !this.face.active && known(this.hoverEdge) ? this.hoverEdge : null;
    if (hover) segments.push(...point(hover.a), ...point(hover.b));
    const chosen: number[] = [];
    for (const edge of this.chosen.values())
      if (known(edge)) chosen.push(...point(edge.a), ...point(edge.b));
    const handles = this.grips().flatMap(({ grip }) => grip);
    this.guides.show({ segments, points, chosen, handles, joins });
    this.host.viewport.invalidate();
  }
}

/** Distance on screen from `p` to the segment from `a` to `b`. */
function segmentDistance(p: ScreenPoint, a: ScreenPoint, b: ScreenPoint): number {
  const [dx, dy] = [b.x - a.x, b.y - a.y];
  const length = dx * dx + dy * dy;
  const t =
    length > 0 ? Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / length)) : 0;
  return Math.hypot(p.x - (a.x + dx * t), p.y - (a.y + dy * t));
}
