import { useEffect, useRef, useState } from 'react';

import type { PreviewResult } from '@shared/protocol/generated/doc';
import type { MeshPayload } from '@shared/protocol/generated/document-display';

import { kernel } from '../../kernel/kernel';
import { getViewport } from '../../viewport/api';
import { type Caps, type Vec3, findCaps, scanExtent } from './extrusionGeometry';

/**
 * Caps of the extrusion in the latest preview, read from the previewed body's faces.
 * While the next payload loads, the previous caps stay (they rarely move).
 */
export function usePreviewCaps(result: PreviewResult | null): Caps | null {
  const [loaded, setLoaded] = useState<Caps | null>(null);
  const body = result?.bodies[0];
  const item = result?.items.find((entry) => entry.kind === 'mesh' && entry.bodyId === body?.id);
  const itemKey = item?.key ?? null;
  const featureId = result?.featureId ?? null;
  const faceTags = body?.faceTags;

  useEffect(() => {
    if (!itemKey || !featureId || !faceTags) return;
    let current = true;
    kernel()
      .call('scene.fetch', { keys: [itemKey] })
      .result.then(({ payloads }) => {
        const mesh = payloads.find((payload): payload is MeshPayload => payload.type === 'mesh');
        if (current) setLoaded(mesh ? findCaps(mesh, faceTags, featureId) : null);
      })
      .catch(() => {
        if (current) setLoaded(null);
      });
    return () => {
      current = false;
    };
  }, [itemKey, featureId, faceTags]);

  return itemKey ? loaded : null;
}

/**
 * How far the scan reaches from the profile plane in front of and behind it, over the
 * profile's footprint (docs/DESIGN.md 5.2: the extrude distance is pre-filled from the scan).
 */
export async function scanDistances(
  caps: Caps,
  planePoint: Vec3,
): Promise<{ ahead: number | null; behind: number | null }> {
  const viewport = getViewport();
  if (!viewport || viewport.scan.faceCount === 0) return { ahead: null, behind: null };
  const { centroids } = await viewport.scanTopology();
  const [x, y, z] = caps.direction;
  return {
    ahead: scanExtent(centroids, caps.footprint, planePoint, caps.direction),
    behind: scanExtent(centroids, caps.footprint, planePoint, [-x, -y, -z]),
  };
}

interface HandleOptions {
  /** Point of the sketch plane under the profile, or null to hide the handle. */
  planePoint: Vec3 | null;
  direction: Vec3 | null;
  value: number;
  /** Changes when the value was set outside the handle (typed), to move the handle. */
  revision: number;
  onChange: (value: number) => void;
}

/**
 * Arrow handle for the extrusion distance. It is rebuilt when the plane moves or the
 * value is typed, never while it is dragged.
 */
export function useDistanceHandle({
  planePoint,
  direction,
  value,
  revision,
  onChange,
}: HandleOptions): void {
  const latest = useRef({ value, onChange });
  useEffect(() => {
    latest.current = { value, onChange };
  });
  const key =
    planePoint && direction
      ? [...planePoint, ...direction].map((number) => number.toFixed(4)).join(',')
      : null;

  useEffect(() => {
    const viewport = getViewport();
    if (!viewport || key === null || !planePoint || !direction) return;
    const handle = viewport.handles.arrow({
      origin: planePoint,
      direction,
      value: latest.current.value,
      color: 'neutral',
      onChange: (next) => {
        if (typeof next === 'number') latest.current.onChange(Math.max(0, next));
      },
      onCommit: (next) => {
        if (typeof next === 'number') latest.current.onChange(Math.max(0, next));
      },
    });
    return () => handle.dispose();
    // `key` stands for the plane point and direction.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, revision]);
}
