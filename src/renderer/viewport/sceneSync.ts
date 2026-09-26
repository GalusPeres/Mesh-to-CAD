// Keeps the drawn scene in line with the document's scene manifest (docs/
// ARCHITECTURE.md 4.8): fetches the payloads it lacks, places the scan with the
// alignment transform, swaps in a new scan once its preparation is done, and
// applies the document's regions. A newer manifest always wins over an older one
// that is still loading; a scan that is being prepared is never prepared twice.

import * as THREE from 'three';

import type {
  SceneItem,
  SceneManifest,
  SceneScan,
} from '@shared/protocol/generated/document-display';

import type { ItemLayer, PayloadFetcher } from './itemLayer';
import type { ScanLayer } from './scanLayer';
import { loadScanMesh } from './scanLoading';
import type { ScanMesh } from './scanMesh';

export type SceneChange = 'placement' | 'scan' | 'topology' | 'items';

export interface SceneSyncHost {
  readonly fetch: PayloadFetcher;
  readonly scan: ScanLayer;
  readonly items: ItemLayer;
  /** Parent of the scan meshes; its matrix places the scan in part coordinates. */
  readonly scanGroup: THREE.Group;
  changed(change: SceneChange): void;
  /** The first scan arrived. */
  firstScan(): void;
}

export class SceneSync {
  private token = 0;
  private regionsKey: string | null = null;
  private loading: { key: string; mesh: Promise<ScanMesh> } | null = null;

  constructor(private readonly host: SceneSyncHost) {}

  async sync(manifest: SceneManifest | null): Promise<void> {
    const token = ++this.token;
    const { scan, items } = this.host;
    const entry = manifest?.scan ?? null;
    const wantedItems: readonly SceneItem[] = manifest?.items ?? [];
    const regionsKey = manifest?.regions ?? null;
    const needsScan = !!entry && scan.current?.displayKey !== entry.key;
    if (this.loading && this.loading.key !== entry?.key) this.abandonLoading();
    const fetchScan = needsScan && this.loading?.key !== entry.key;
    const keys = items.missing(wantedItems);
    if (fetchScan) keys.unshift(entry.key);
    if (regionsKey && regionsKey !== this.regionsKey) keys.push(regionsKey);

    const payloads = keys.length ? await this.host.fetch(keys) : [];
    if (token !== this.token) return;
    const byKey = new Map(payloads.map((payload) => [payload.key, payload]));

    if (regionsKey !== this.regionsKey) {
      const regions = regionsKey ? byKey.get(regionsKey) : undefined;
      if (regions?.type === 'regions') scan.setDocumentRegions(regions.labels, regions.colorIndex);
      else scan.setDocumentRegions(null, null);
      this.regionsKey = regionsKey;
    }
    items.sync(wantedItems, byKey);
    this.host.changed('items');
    if (!entry) this.replaceScan(null);
    else this.place(entry);
    if (!entry || !needsScan) return;

    if (fetchScan) {
      const loading = loadScanMesh(
        entry,
        byKey.get(entry.key),
        this.host.fetch,
        scan.materials.opaque,
      );
      this.loading = { key: entry.key, mesh: loading };
      loading.catch(() => {
        if (this.loading?.mesh === loading) this.loading = null;
      });
    }
    const mesh = await this.loading!.mesh;
    if (token !== this.token) return;
    this.loading = null;
    const first = !scan.current;
    this.replaceScan(mesh);
    if (first) this.host.firstScan();
  }

  dispose(): void {
    this.token += 1;
    this.abandonLoading();
    this.host.scan.current?.dispose();
  }

  /** A scan that is no longer wanted is disposed once its preparation finishes. */
  private abandonLoading(): void {
    const abandoned = this.loading?.mesh;
    this.loading = null;
    abandoned?.then(
      (mesh) => {
        if (this.host.scan.current !== mesh) mesh.dispose();
      },
      () => undefined,
    );
  }

  /** Positions are relative to the scan origin; the alignment places them in the part. */
  private place(entry: SceneScan): void {
    const matrix = new THREE.Matrix4()
      .set(...(entry.transform as Parameters<THREE.Matrix4['set']>))
      .multiply(new THREE.Matrix4().makeTranslation(...entry.origin));
    const group = this.host.scanGroup;
    if (matrix.equals(group.matrix)) return;
    group.matrix.copy(matrix);
    group.matrixWorldNeedsUpdate = true;
    this.host.changed('placement');
  }

  private replaceScan(mesh: ScanMesh | null): void {
    const { scan, scanGroup } = this.host;
    const previous = scan.current;
    if (previous === mesh) return;
    if (mesh) {
      mesh.showNextChunk();
      scanGroup.add(mesh.group);
      mesh.preparation.topology
        .then((topology) => {
          if (scan.current !== mesh) return;
          mesh.attachTopology(topology);
          scan.topologyReady();
          this.host.changed('topology');
        })
        .catch((error: unknown) => {
          window.m2c.app.log({ level: 'error', message: `scan topology failed: ${String(error)}` });
        });
    }
    scan.attach(mesh);
    if (previous) {
      scanGroup.remove(previous.group);
      previous.dispose();
    }
    this.host.changed('scan');
  }
}
