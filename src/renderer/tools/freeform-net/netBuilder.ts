// Building the net by hand, as in QuickSurface: a face from four clicks on the scan,
// chosen edges (a double click takes a whole chain), new rows dragged out of border
// edges by drag and drop (RowDrag: dropped onto the scan, or onto border points of the
// net to join pieces), a border point dropped onto another one welds them, and chosen
// points or edges can be deleted with their quads. After a row its outer edges are
// chosen, so the next drag goes on from there.

import type { ScreenPoint, Vec3, Viewport } from '../../viewport/api';
import { GuideOverlay } from './GuideOverlay';
import { addQuad, extrudeEdges, mergePoints, removeQuads, splitRing } from './netBuild';
import type { Net } from './netModel';
import { RowDrag, joinableBorder, nearestJoin } from './netRows';
import type { NetEditorState } from './netState';
import { type Edge, borderEdges, borderRuns, edgeKey, edgeLoop } from './netTopology';

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
  update(patch: Partial<Pick<NetEditorState, 'facing' | 'facePoints' | 'chosenEdges'>>): void;
  /** Show a net as one undo step. */
  record(net: Net): Promise<void>;
  /** Show a net, then snap its new points to the scan: one undo step. */
  settle(net: Net, added: readonly number[]): Promise<void>;
}

export type ChoiceMode = 'replace' | 'add' | 'remove' | 'toggle';

export class NetBuilder {
  private facePoints: { point: Vec3; normal: Vec3 }[] = [];
  private facePreview: Vec3 | null = null;
  private facing = false;
  private hoverEdge: Edge | null = null;
  private readonly chosen = new Map<string, Edge>();
  private readonly rows: RowDrag;
  private guides: GuideOverlay | null = null;

  constructor(private readonly host: BuildHost) {
    this.rows = new RowDrag(host);
  }

  // A face by four clicks ------------------------------------------------------------------

  setFacing(facing: boolean): void {
    this.facing = facing;
    this.facePoints = [];
    this.facePreview = null;
    this.host.update({ facing, facePoints: 0 });
    this.draw();
  }

  /** A clicked scan point of the new face; the fourth one adds the face. */
  async addFacePoint(point: Vec3, normal: Vec3): Promise<void> {
    if (!this.facing || this.host.busy()) return;
    this.facePoints.push({ point, normal });
    this.host.update({ facePoints: this.facePoints.length });
    this.draw();
    if (this.facePoints.length < 4) return;
    const corners = this.facePoints.map((clicked) => clicked.point);
    const outward = this.facePoints.reduce<Vec3>(
      (sum, { normal: n }) => [sum[0] + n[0], sum[1] + n[1], sum[2] + n[2]],
      [0, 0, 0],
    );
    this.setFacing(false);
    await this.host.record(addQuad(this.host.net(), corners, outward));
  }

  /** Take back the last clicked corner; false if there was none. */
  removeFacePoint(): boolean {
    if (this.facePoints.length === 0) return false;
    this.facePoints.pop();
    this.host.update({ facePoints: this.facePoints.length });
    this.draw();
    return true;
  }

  /** The scan point under the pointer while placing a face (rubber band), or null. */
  previewFacePoint(point: Vec3 | null): void {
    this.facePreview = point;
    this.draw();
  }

  // Chosen edges ---------------------------------------------------------------------------

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
   * Start dragging rows out of the border: out of every chosen border edge if `edge` is
   * chosen, else out of `edge` alone (which becomes the choice). False if it is no border.
   */
  beginRows(edge: Edge): boolean {
    const net = this.host.net();
    if (!net || this.host.busy()) return false;
    if (!this.isChosen(edge)) this.chooseEdges([edge], 'replace');
    return this.rows.begin(borderRuns(net, this.chosenEdges()));
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
    const outer: Edge[] = [];
    for (const run of drop.runs) {
      const row = extrudeEdges(next, run, drop.target);
      next = row.net;
      added.push(...row.added);
      outer.push(...row.outer);
    }
    // The outer edges that stay open are chosen (once the new net is shown): the next
    // drag goes on from there. A row joined onto the net closes them.
    const open = new Set(borderEdges(next).map(({ a, b }) => edgeKey(a, b)));
    this.chosen.clear();
    for (const edge of outer)
      if (open.has(edgeKey(edge.a, edge.b))) this.chosen.set(edgeKey(edge.a, edge.b), edge);
    if (added.length > 0) await this.host.settle(next, added);
    else await this.host.record(next);
  }

  get draggingRows(): boolean {
    return this.rows.active;
  }

  // Changing the net -----------------------------------------------------------------------

  /** Split the ring of quads crossing an edge with a new loop, snapped to the scan. */
  async split(edge: Edge): Promise<void> {
    const net = this.host.net();
    if (!net || this.host.busy()) return;
    const result = splitRing(net, edge.a, edge.b);
    if (result.added.length === 0) return;
    await this.host.settle(result.net, result.added);
  }

  /** A dragged border point dropped onto another border point: weld them (true if so). */
  weldOnto(control: number): boolean {
    const net = this.host.net();
    const screen = this.host.screenOf(control);
    if (!net || !screen || this.host.busy()) return false;
    if (!this.isBorderPoint(net, control)) return false;
    const border = joinableBorder(net, (v) => this.host.screenOf(v), new Set([control]));
    const into = nearestJoin(border, screen);
    const welded = into === null ? null : mergePoints(net, control, into);
    if (!welded) return false;
    void this.host.record(welded);
    return true;
  }

  /**
   * Delete the quads of the chosen edges, else the quads using chosen points; false if
   * nothing is chosen or no quad would be left.
   */
  deleteChosen(): boolean {
    const net = this.host.net();
    if (!net || this.host.busy()) return false;
    const points = this.host.chosenPoints();
    const edges = new Set(this.chosen.keys());
    const touches = (corners: number[]) =>
      edges.size > 0
        ? corners.some((p, k) => edges.has(edgeKey(p, corners[(k + 1) % 4] ?? p)))
        : corners.some((p) => points.has(p));
    if (edges.size === 0 && points.size === 0) return false;
    const rest = removeQuads(net, touches);
    if (!rest) return false;
    this.chosen.clear();
    void this.host.record(rest);
    return true;
  }

  // Upkeep ---------------------------------------------------------------------------------

  /** The net's quads changed: forget edges it no longer has. */
  topologyChanged(net: Net): void {
    const present = new Set<string>();
    for (let quad = 0; quad < net.quads.length / 4; quad += 1)
      for (let k = 0; k < 4; k += 1)
        present.add(
          edgeKey(net.quads[quad * 4 + k] ?? 0, net.quads[quad * 4 + ((k + 1) % 4)] ?? 0),
        );
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
      return {
        edge,
        middle,
        screen: this.host.viewport.worldToScreen(middle),
        chosen: this.isChosen(edge),
      };
    });
  }

  dispose(): void {
    this.rows.cancel();
    this.guides?.dispose();
    this.guides = null;
  }

  private isBorderPoint(net: Net, control: number): boolean {
    return borderEdges(net).some(({ a, b }) => a === control || b === control);
  }

  private draw(): void {
    if (!this.host.shown()) return;
    if (!this.guides) this.guides = new GuideOverlay(this.host.viewport.createOverlay());
    const net = this.host.net();
    const count = net ? net.vertices.length / 3 : 0;
    const point = (vertex: number) => this.host.limitPoint(vertex);
    const { segments, points } = this.rows.preview();
    const corners = this.facePoints.map((clicked) => clicked.point);
    if (this.facePreview && this.facing) corners.push(this.facePreview);
    corners.forEach((corner, i) => {
      points.push(...corner);
      const next = corners[i + 1] ?? (corners.length === 4 ? corners[0] : undefined);
      if (next) segments.push(...corner, ...next);
    });
    const known = (edge: Edge) => edge.a < count && edge.b < count;
    if (this.hoverEdge && !this.facing && known(this.hoverEdge))
      segments.push(...point(this.hoverEdge.a), ...point(this.hoverEdge.b));
    const chosen: number[] = [];
    for (const edge of this.chosen.values())
      if (known(edge)) chosen.push(...point(edge.a), ...point(edge.b));
    this.guides.show(segments, points, chosen);
    this.host.viewport.invalidate();
  }
}
