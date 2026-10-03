// One-step changes of the net on the user's command, as in QuickSurface's context
// menu: split the ring of quads across an edge (S), bridge two chosen chains, increase
// the resolution (every quad into four), weld a dropped point onto another one, and
// delete the chosen quads. New points are snapped to the scan.

import type { BuildHost } from './netBuilder';
import { bridgeRuns, mergePoints, removeQuads, splitRing, subdivide } from './netBuild';
import type { Net } from './netModel';
import { joinableBorder, nearestJoin } from './netRows';
import { type Edge, borderEdges, borderRuns, edgeKey } from './netTopology';

/** The chosen edges an edit works on, and how to forget them after it. */
export interface EdgeChoice {
  edges(): Edge[];
  clear(): void;
}

export class NetEdits {
  constructor(
    private readonly host: BuildHost,
    private readonly chosen: EdgeChoice,
  ) {}

  /** Split the ring of quads crossing an edge with a new loop, snapped to the scan. */
  async split(edge: Edge): Promise<void> {
    const net = this.ready();
    if (!net) return;
    const result = splitRing(net, edge.a, edge.b);
    if (result.added.length > 0) await this.host.settle(result.net, result.added);
  }

  /** The two border runs of the chosen edges if they can be bridged (same length). */
  bridgeable(): [Edge[], Edge[]] | null {
    const net = this.host.net();
    if (!net) return null;
    const runs = borderRuns(net, this.chosen.edges());
    const [from, to] = runs;
    return runs.length === 2 && from && to && from.length === to.length ? [from, to] : null;
  }

  /** Close the gap between the two chosen border chains with a row of quads. */
  async bridge(): Promise<boolean> {
    const net = this.ready();
    const runs = this.bridgeable();
    const bridged = net && runs ? bridgeRuns(net, runs[0], runs[1]) : null;
    if (!bridged) return false;
    this.chosen.clear();
    await this.host.record(bridged);
    return true;
  }

  /** Every quad into four, the new points snapped to the scan. */
  async refine(): Promise<void> {
    const net = this.ready();
    if (!net) return;
    const fine = subdivide(net);
    this.chosen.clear();
    await this.host.settle(fine.net, fine.added);
  }

  /** A dragged border point dropped onto another border point: weld them (true if so). */
  weldOnto(control: number): boolean {
    const net = this.ready();
    const screen = this.host.screenOf(control);
    if (!net || !screen) return false;
    if (!borderEdges(net).some(({ a, b }) => a === control || b === control)) return false;
    const border = joinableBorder(net, (v) => this.host.screenOf(v), new Set([control]));
    const into = nearestJoin(border, screen);
    const welded = into === null ? null : mergePoints(net, control, into);
    if (!welded) return false;
    void this.host.record(welded);
    return true;
  }

  /**
   * Delete the quads of the chosen edges, else the quads using chosen points (all of
   * them empties the net); false if nothing is chosen.
   */
  deleteChosen(): boolean {
    const net = this.ready();
    if (!net) return false;
    const points = this.host.chosenPoints();
    const edges = new Set(this.chosen.edges().map(({ a, b }) => edgeKey(a, b)));
    if (edges.size === 0 && points.size === 0) return false;
    const touches = (corners: number[]) =>
      edges.size > 0
        ? corners.some((p, k) => edges.has(edgeKey(p, corners[(k + 1) % 4] ?? p)))
        : corners.some((p) => points.has(p));
    const rest = removeQuads(net, touches);
    if (!rest) return false;
    this.chosen.clear();
    void this.host.record(rest);
    return true;
  }

  private ready(): Net | null {
    return this.host.busy() ? null : this.host.net();
  }
}
