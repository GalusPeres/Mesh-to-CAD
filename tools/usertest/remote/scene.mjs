// What the remote pipeline reads from the document: features, bodies, the edges the
// view draws, plane heights, and waiting until the window shows the latest revision.

export const uint32 = (values) => ({ $typed: 'uint32', values: Array.from(values) });

/** The document snapshot: `document`, `status`, `scene`, `revision`. */
export const snapshot = (d) => d.kernel('doc.get');

/** Apply document operations as one undoable step, like the window does. */
export async function applyOps(d, ops, label) {
  const { revision } = await snapshot(d);
  const result = await d.kernel('doc.apply', { baseRevision: revision, ops, label });
  await shown(d);
  return result;
}

/** Wait until the window shows the document's current revision. */
export async function shown(d) {
  const { revision } = await snapshot(d);
  await d.until(
    async () => ((await d.state())?.revision ?? -1) >= revision,
    `the window at revision ${revision}`,
  );
  return revision;
}

/** Features added after `before` features, each with its status. */
export async function addedFeatures(d, before) {
  const { document, status } = await snapshot(d);
  return document.features.slice(before).map((feature) => ({
    id: feature.id,
    type: feature.type,
    name: feature.name ?? null,
    state: status.features[feature.id]?.state ?? 'unknown',
    error: status.features[feature.id]?.error?.code ?? null,
    issues: (status.features[feature.id]?.issues ?? []).map((issue) => issue.code),
  }));
}

/** Height of a plane (origin, normal) above the point (x, y). */
export function planeHeight(plane, x, y) {
  const [ox, oy, oz] = plane.origin;
  const [nx, ny, nz] = plane.normal;
  return oz - (nx * (x - ox) + ny * (y - oy)) / nz;
}

/**
 * The edges the view draws for a body: line segments with their B-Rep edge and the
 * tags of the faces on both sides (what Verrundung stores as an edge reference).
 */
export async function bodyEdges(d, bodyId) {
  const { scene, status } = await snapshot(d);
  const item = scene.items.find((entry) => entry.bodyId === bodyId && entry.kind === 'lines');
  const body = status.bodies.find((entry) => entry.id === bodyId);
  if (!item || !body) throw new Error(`no edges of body ${bodyId}`);
  const [payload] = (await d.kernel('scene.fetch', { keys: [item.key] })).payloads;
  const segments = [];
  for (let index = 0; index < payload.ids.length; index += 1) {
    const s = payload.segments.slice(index * 6, index * 6 + 6);
    const faces = payload.faces
      ? [body.faceTags[payload.faces[index * 2]], body.faceTags[payload.faces[index * 2 + 1]]]
      : null;
    segments.push({ edge: payload.ids[index], a: s.slice(0, 3), b: s.slice(3, 6), faces });
  }
  return segments;
}

/** The body a feature made, or null. */
export async function bodyOf(d, featureId) {
  const { status } = await snapshot(d);
  return status.bodies.find((body) => body.owner === featureId) ?? null;
}
