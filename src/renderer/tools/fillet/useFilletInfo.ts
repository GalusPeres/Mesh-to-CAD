import { useEffect } from 'react';

import { setToolInfoProvider } from '../../automation/toolInfo';

interface FilletInfo {
  edges: number;
  size: number;
  /** Radius aus Scan: running, ok (with the radius), tooFewFaces or error. */
  measurement: { status: string; radius?: number; measured?: number } | null;
  /** OK is possible: the preview of the picked edges with this size is there. */
  ready: boolean;
}

/** What the open Verrundung tells automation clients: picked edges, size, the scan radius. */
export function useFilletInfo(info: FilletInfo): void {
  const { edges, size, measurement, ready } = info;
  useEffect(
    () =>
      setToolInfoProvider(() => ({
        state: { job: measurement?.status === 'running' },
        edges,
        size,
        measurement,
        ready,
      })),
    [edges, size, measurement, ready],
  );
}
