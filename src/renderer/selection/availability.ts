import type { Availability, ToolContext } from '../tools/framework/types';

/** Selection modes and region tools need a scan. */
export function scanRequired({ snapshot }: ToolContext): Availability {
  return snapshot?.document.scan
    ? { enabled: true }
    : { enabled: false, reasonKey: 'errors:regions.noScan' };
}
