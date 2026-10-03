// Shaping the net as a whole or its chosen points: Snap to scan and Smooth (kernel
// `net.fit`), Q, laying points on a plane, snapping the new points of an edit, placing
// dropped points exactly where they were dropped, and pushing the border past planes
// and bodies (`net.pushPast`). Pinned points stay in all of them (`fixed` for the
// kernel; NetEditor holds their limit points afterwards).

import type { LimitSurface } from './limitSurface';
import { limitsOf, placeLimits } from './netDragSolve';
import type { NetJobs } from './netJobs';
import { type Net, cloneNet, fitPlane, projectOntoPlane } from './netModel';
import { fixedMask } from './netPins';
import type { ChooseMode } from './netPoints';
import type { PushReferences } from './netReferences';
import type { NetEditorState } from './netState';
import type { Edge } from './netTopology';

/** Fairness of "Snap to scan" and the stronger one of "Smooth" (kernel `net.fit`). */
export const SNAP_SMOOTHING = 0.002;
export const SMOOTH_SMOOTHING = 0.05;
const FIT_ITERATIONS = 4;

/** What shaping needs of the editor that owns the net. */
export interface ShapingHost {
  readonly jobs: NetJobs;
  net(): Net | null;
  surface(): LimitSurface | null;
  chosen(): ReadonlySet<number>;
  pinned(): ReadonlySet<number>;
  /** Scan triangles the net belongs to; null = the whole scan. */
  faces(): Uint32Array | null;
  busy(): boolean;
  chosenEdges(): Edge[];
  choose(controls: Iterable<number>, mode: ChooseMode): void;
  /** Show a net (and record it as a draft step). */
  show(net: Net, record: boolean): Promise<void>;
  /** The net's points moved in place: redraw and measure, then record a draft step. */
  moved(): Promise<void>;
  /** Record the current net as a draft step. */
  record(): void;
  /** Tell the panel what the last push did. */
  report(pushed: NetEditorState['pushed']): void;
}

export class NetShaping {
  constructor(private readonly host: ShapingHost) {}

  /**
   * Snap the net to the scan; with chosen points only those move ("Smooth": fairer).
   * Pinned points stay. Returns whether the fitted net was shown (and recorded).
   */
  async fit(smooth: boolean): Promise<boolean> {
    const net = this.host.net();
    if (!net) return false;
    const result = await this.host.jobs.run(smooth ? 'smooth' : 'fit', 'net.fit', {
      vertices: net.vertices,
      quads: net.quads,
      faces: this.host.faces(),
      fixed: fixedMask(net.vertices.length / 3, this.host.pinned(), this.host.chosen()),
      smoothing: smooth ? SMOOTH_SMOOTHING : SNAP_SMOOTHING,
      iterations: FIT_ITERATIONS,
    });
    if (!result) return false;
    await this.host.show({ vertices: result.vertices, quads: net.quads }, true);
    return true;
  }

  /** Q: smooth the chosen chain (or the chosen points) while it stays on the scan. */
  async smoothChosen(): Promise<void> {
    const edges = this.host.chosenEdges();
    if (edges.length > 0)
      this.host.choose(
        edges.flatMap(({ a, b }) => [a, b]),
        'replace',
      );
    if (this.host.chosen().size > 0) await this.fit(true);
  }

  /**
   * Push the net's open border 0.5 mm past the planes and bodies it ends at, so that
   * trimming against them cuts cleanly (QuickSurface: Offset by reference surfaces).
   */
  async pushPast(references: PushReferences): Promise<void> {
    const net = this.host.net();
    if (!net || this.host.busy()) return;
    const count = net.vertices.length / 3;
    const result = await this.host.jobs.run('push', 'net.pushPast', {
      vertices: net.vertices,
      quads: net.quads,
      planes: references.planes,
      bodies: references.bodies,
      fixed: fixedMask(count, this.host.pinned(), new Set()),
    });
    if (!result) return;
    if (result.moved > 0)
      await this.host.show({ vertices: result.vertices, quads: net.quads }, true);
    this.host.report({ moved: result.moved, faces: result.references.length });
  }

  /**
   * Lay the chosen control points (not the pinned ones) on their best-fitting plane.
   * Where a region of the net and the ring of points around it are coplanar, its limit
   * surface is exactly that plane (affine invariance of subdivision), so flat faces
   * become truly flat.
   */
  async flatten(): Promise<void> {
    const net = this.host.net();
    const surface = this.host.surface();
    const pinned = this.host.pinned();
    const chosen = [...this.host.chosen()].filter((control) => !pinned.has(control));
    if (!net || !surface || chosen.length < 3 || this.host.busy()) return;
    const plane = fitPlane(limitsOf(surface, chosen));
    if (!plane) return;
    const next = cloneNet(net);
    projectOntoPlane(next.vertices, chosen, plane);
    await this.host.show(next, true);
  }

  /** Show a changed net, then snap its new points to the scan: one undo step. */
  async settle(net: Net, added: readonly number[]): Promise<void> {
    await this.host.show(net, false);
    this.host.choose(added, 'replace');
    const fitted = await this.fit(false);
    if (!fitted) this.host.record();
  }

  /**
   * Show a net with dropped points whose limit points stay exactly where they were
   * dropped, as in QuickSurface (a fit would pull a row dropped over a rim back off
   * the wall); only the new control points move, pinned ones hold. One undo step.
   */
  async place(net: Net, added: readonly number[]): Promise<void> {
    await this.host.show(net, false);
    const surface = this.host.surface();
    const shown = this.host.net();
    if (!surface || !shown) return;
    const pinned = [...this.host.pinned()];
    const targets = new Float64Array((added.length + pinned.length) * 3);
    added.forEach((control, i) =>
      targets.set(net.vertices.subarray(control * 3, control * 3 + 3), i * 3),
    );
    targets.set(limitsOf(surface, pinned), added.length * 3);
    placeLimits(surface, shown.vertices, [...added, ...pinned], targets);
    this.host.choose(added, 'replace');
    await this.host.moved();
  }
}
