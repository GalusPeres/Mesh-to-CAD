// Step: round the base body's top edge, the way the user does it: Verrundung, click
// the edges in the view, "Radius aus Scan", OK. Where the tool cannot do that yet, the
// gap is recorded and the fillet is added with the remote's measured 0.78 mm instead,
// so the steps after it still run.

import { setView } from '../view.mjs';
import { applyOps, bodyEdges, snapshot } from '../scene.mjs';

/** The remote's top edge radius, measured on the scan by hand. */
const FALLBACK_RADIUS = 0.78;

/** Points along an edge where the user may click it. */
const SAMPLES = 16;

/**
 * The edges of the body's top (the highest edges): their face tags, a point on each
 * (what the fillet stores) and points spread along it to click.
 */
async function topEdges(d, bodyId) {
  const segments = await bodyEdges(d, bodyId);
  const top = Math.max(...segments.flatMap(({ a, b }) => [a[2], b[2]]));
  const edges = new Map();
  for (const segment of segments) {
    if (Math.min(segment.a[2], segment.b[2]) < top - 0.02) continue;
    const middle = segment.a.map((value, axis) => (value + segment.b[axis]) / 2);
    const edge = edges.get(segment.edge) ?? { faces: segment.faces, points: [] };
    edge.points.push(middle);
    edges.set(segment.edge, edge);
  }
  return [...edges.values()].map(({ faces, points }) => ({
    faces,
    point: points[0],
    along: points.filter((_, index) => index % Math.max(1, Math.floor(points.length / SAMPLES)) === 0),
  }));
}

/** A screen point where a click finds `edge`, or what the clicks found instead. */
async function clickable(d, edge) {
  const found = new Set();
  for (const point of edge.along) {
    const screen = await d.at(point).catch(() => null);
    const hit = screen && (await d.pick(screen));
    if (hit?.kind === 'edge') return { screen };
    found.add(hit?.kind === 'item' ? `${hit.kind} of ${hit.owner}` : (hit?.kind ?? 'nothing'));
  }
  return { found: [...found] };
}

async function closeTool(d) {
  await d.press('panel-cancel').catch(() => undefined);
  await d.press('discard-confirm').catch(() => undefined);
}

/** Verrundung through its panel; returns the radius, or a gap that stopped it. */
async function filletInTool(d, edges) {
  await d.press('tool-fillet');
  await setView(d, 'iso', 'bodies');
  let picked = 0;
  const missed = [];
  for (const edge of edges) {
    const { screen, found } = await clickable(d, edge);
    if (!screen) {
      missed.push(...found);
      continue;
    }
    await d.tap(screen);
    picked += 1;
  }
  if (picked === 0) {
    await closeTool(d);
    return { gap: `a click on the top edge finds ${[...new Set(missed)].join(', ')}, no edge` };
  }
  await d.until(async () => (await d.toolInfo())?.edges > 0, 'the picked edges', 10_000);
  await d.press('fillet-from-scan');
  const { measurement } = await d.until(async () => {
    const info = await d.toolInfo();
    return info?.measurement && info.measurement.status !== 'running' ? info : null;
  }, 'Radius aus Scan');
  if (measurement.status !== 'ok') {
    await closeTool(d);
    return { gap: `Radius aus Scan: ${measurement.status} ${measurement.message ?? ''}`.trim() };
  }
  await d.until(async () => (await d.toolInfo())?.ready, 'the fillet preview', 180_000);
  await d.press('panel-ok');
  await d.until(async () => (await d.state()).activeTool === null, 'the fillet', 120_000);
  return { radius: measurement.radius, measured: measurement.measured, picked };
}

export const topFillet = {
  id: 'fillet',
  title: 'Top edge: Verrundung, Radius aus Scan',
  async run(ctx) {
    const { d } = ctx;
    const edges = await topEdges(d, ctx.body);
    if (edges.length === 0) throw new Error('the body has no top edge');
    const before = (await snapshot(d)).document.features.length;
    const done = await filletInTool(d, edges);
    if (!done.gap) return { edges: edges.length, source: 'scan', ...done };

    await applyOps(
      d,
      [
        {
          type: 'addFeature',
          feature: {
            type: 'fillet',
            params: {
              targetBody: ctx.body,
              edges: edges.map(({ faces, point }) => ({ faces, point })),
              mode: 'fillet',
              size: FALLBACK_RADIUS,
            },
          },
        },
      ],
      'fillet',
    );
    const { document, status } = await snapshot(d);
    const fillet = document.features.slice(before).find((item) => item.type === 'fillet');
    const state = fillet ? status.features[fillet.id] : null;
    if (state?.state === 'error') {
      throw new Error(
        `${done.gap}; the kernel fillet with ${FALLBACK_RADIUS} mm on ${edges.length} ` +
          `top edges fails too: ${state.error?.code}`,
      );
    }
    return {
      edges: edges.length,
      radius: FALLBACK_RADIUS,
      source: 'fixed',
      gaps: [`${done.gap}; added by kernel call with ${FALLBACK_RADIUS} mm`],
    };
  },
};
