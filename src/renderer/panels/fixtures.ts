// Documents for the panel tests. Only the fields the tree and properties read are
// meaningful; blob references are placeholders.

import i18next, { type TFunction } from 'i18next';

import type { Document, Feature, Region } from '@shared/protocol/generated/document-model';
import type { BodyInfo } from '@shared/protocol/generated/document-results';
import type {
  DocumentSnapshot,
  DocumentStatus,
} from '@shared/protocol/generated/document-snapshot';

import { buildResources } from '../i18n/resources';

const blob = { id: 'blob', byteLength: 0 } as never;

export async function testTranslator(language: 'de' | 'en' = 'de'): Promise<TFunction> {
  const instance = i18next.createInstance();
  await instance.init({
    resources: buildResources(),
    lng: language,
    fallbackLng: 'de',
    defaultNS: 'common',
    interpolation: { escapeValue: false },
  });
  return instance.t;
}

export function region(id: string, label: number, kind: Region['kind'], rms: number | null = 0.02) {
  return {
    id,
    label,
    name: null,
    kind,
    rms,
    faceCount: 100,
    area: 10,
    colorIndex: label,
  } satisfies Region;
}

export function fit(id: string, kind: string, extra: Partial<Feature> = {}, sourceRegion?: string) {
  return {
    id,
    type: 'fit',
    name: null,
    suppressed: false,
    params: { kind, sourceRegion: sourceRegion ?? null },
    ...extra,
  } satisfies Feature;
}

export function body(id: string, extra: Partial<BodyInfo> = {}): BodyInfo {
  return {
    id,
    owner: id,
    valid: true,
    solids: 1,
    volume: 1000,
    area: 600,
    maxTolerance: 1e-7,
    faceTags: [],
    ...extra,
  };
}

export function makeDocument(features: Feature[] = [], regions: Region[] = []): Document {
  return {
    revision: 3,
    nextId: 10,
    scan: {
      key: 'scan:k',
      source: { fileName: 'bracket.stl', sha256: 'x', importUnit: 'mm' },
      vertices: blob,
      faces: blob,
      synthetic: null,
      vertexCount: 600,
      faceCount: 1200,
      origin: [0, 0, 0],
      noise: 0.03,
      displaySmoothing: 0,
      operations: [
        { op: 'import', counts: {} },
        { op: 'repair', counts: { degenerateFaces: 3 } },
        { op: 'decimate', counts: { facesBefore: 2400, facesAfter: 1200 } },
      ],
    },
    alignment: {
      method: 'faces',
      params: null,
      adjust: { flipX: false, flipZ: false, rotateZ90: 0 },
      matrix: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] as never,
    },
    regions: { labels: null, items: regions },
    features,
    settings: { tolerance: 0.1, snapUnits: 'metric', noiseOverride: null, deviationMaxDistance: 1 },
  };
}

export function makeSnapshot(
  document: Document,
  status: DocumentStatus = { features: {}, bodies: [] },
): DocumentSnapshot {
  return {
    revision: document.revision,
    cause: 'current',
    label: '',
    document,
    status,
    scene: { scan: null, regions: null, items: [] },
  };
}
