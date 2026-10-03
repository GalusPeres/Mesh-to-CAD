// Named regions: save the selection as a region, change a region by the
// selection, select, merge, rename and delete regions. Every change is a
// document revision (undoable with Ctrl+Z); the kernel keeps regions disjoint.

import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

import type { Region } from '@shared/protocol/generated/document-model';
import type { RegionsPayload } from '@shared/protocol/generated/document-display';

import { i18n } from '../i18n';
import { kernel } from '../kernel/kernel';
import { documentStore } from '../state/documentStore';
import { showMessage } from '../state/messageStore';
import { objectSelectionStore, selectObjects } from '../state/objectSelectionStore';
import { setDisplayMode, viewStore } from '../state/viewStore';
import { selectedFaces } from './api';
import { reportFailure } from './reportFailure';
import { changeSelection, currentScan, hiddenMask } from './selectionActions';

export function documentRegions(): Region[] {
  return documentStore.getState().snapshot?.document.regions.items ?? [];
}

/** Regions selected in the project tree (or the viewport), in document order. */
export function selectedRegions(): Region[] {
  const ids = new Set(
    objectSelectionStore
      .getState()
      .selected.filter((ref) => ref.kind === 'region')
      .map((ref) => ref.id),
  );
  return documentRegions().filter((region) => ids.has(region.id));
}

let labelCache: { key: string; labels: Promise<Uint16Array | null> } | null = null;

/** Region label per face of the current scan, fetched once per regions payload. */
export function regionLabels(): Promise<Uint16Array | null> {
  const key = documentStore.getState().snapshot?.scene.regions ?? null;
  if (!key) return Promise.resolve(null);
  if (labelCache?.key !== key) {
    const labels = kernel()
      .call('scene.fetch', { keys: [key] })
      .result.then(({ payloads }) => {
        const payload = payloads.find((item): item is RegionsPayload => item.type === 'regions');
        return payload?.labels ?? null;
      })
      .catch(() => null);
    labelCache = { key, labels };
  }
  return labelCache.labels;
}

/** Faces carrying one of the labels. */
export function facesWithLabels(labels: Uint16Array, wanted: ReadonlySet<number>): Uint32Array {
  let count = 0;
  for (const value of labels) if (wanted.has(value)) count += 1;
  const faces = new Uint32Array(count);
  let next = 0;
  labels.forEach((value, face) => {
    if (wanted.has(value)) faces[next++] = face;
  });
  return faces;
}

function showRegions(): void {
  if (viewStore.getState().displayMode !== 'deviation') setDisplayMode('regions');
}

async function run(task: () => Promise<void>): Promise<boolean> {
  try {
    await task();
    return true;
  } catch (error) {
    reportFailure(error);
    return false;
  }
}

/** Ctrl+R: the selected triangles become a new region (and leave the regions they were in). */
export async function saveSelectionAsRegion(): Promise<boolean> {
  const scan = currentScan();
  if (!scan) return false;
  const faces = selectedFaces(scan.key);
  if (!faces.length) {
    showMessage('warning', i18n.t('errors:regions.emptySelection'));
    return false;
  }
  return run(async () => {
    const { regionId } = await kernel().call('regions.create', { scanKey: scan.key, faces }).result;
    showRegions();
    if (regionId) selectObjects([{ kind: 'region', id: regionId }]);
    showMessage('success', i18n.t('selection:regions.saved', { count: faces.length }));
  });
}

/** Add the regions' faces to the selection (one undo step). */
export async function selectRegions(regions: readonly Region[]): Promise<void> {
  const labels = await regionLabels();
  if (!labels || !currentScan() || labels.length !== currentScan()?.faceCount) return;
  const faces = facesWithLabels(labels, new Set(regions.map((region) => region.label)));
  const hidden = hiddenMask();
  changeSelection({ selected: hidden ? faces.filter((face) => !hidden[face]) : faces });
}

export async function addSelectionToRegion(region: Region): Promise<boolean> {
  return updateBySelection(region, 'addFaces');
}

export async function removeSelectionFromRegion(region: Region): Promise<boolean> {
  return updateBySelection(region, 'removeFaces');
}

async function updateBySelection(
  region: Region,
  field: 'addFaces' | 'removeFaces',
): Promise<boolean> {
  const scan = currentScan();
  if (!scan) return false;
  const faces = selectedFaces(scan.key);
  if (!faces.length) {
    showMessage('warning', i18n.t('errors:regions.emptySelection'));
    return false;
  }
  return run(async () => {
    await kernel().call('regions.update', {
      regionId: region.id,
      scanKey: scan.key,
      [field]: faces,
    }).result;
    showRegions();
  });
}

export async function mergeRegions(regions: readonly Region[]): Promise<boolean> {
  if (regions.length < 2) return false;
  return run(async () => {
    const { regionId } = await kernel().call('regions.merge', {
      regionIds: regions.map((region) => region.id),
    }).result;
    if (regionId) selectObjects([{ kind: 'region', id: regionId }]);
  });
}

export async function deleteRegions(regions: readonly Region[]): Promise<boolean> {
  if (!regions.length) return false;
  return run(async () => {
    await kernel().call('regions.delete', { regionIds: regions.map((region) => region.id) }).result;
    selectObjects([]);
  });
}

/** An empty name returns to the default name ("Bereich 7"). */
export async function renameRegion(region: Region, name: string): Promise<boolean> {
  const trimmed = name.trim();
  if ((region.name ?? '') === trimmed) return false;
  const scanKey = currentScan()?.key;
  if (!scanKey) return false;
  return run(async () => {
    await kernel().call('regions.update', {
      regionId: region.id,
      scanKey,
      rename: { name: trimmed === '' ? null : trimmed },
    }).result;
  });
}

/** Default display name of a region: "Bereich 7". */
export function regionDisplayName(region: Region): string {
  return region.name ?? i18n.t('selection:regions.defaultName', { number: region.label });
}

// ---------------------------------------------------------------------------------
// Rename dialog state (the dialog is selection/RegionRenameDialog.dialog.tsx).

interface RegionDialogState {
  rename: { regionId: string; name: string } | null;
}

export const regionDialogStore = createStore<RegionDialogState>(() => ({ rename: null }));

export function useRegionDialogs<T>(selector: (state: RegionDialogState) => T): T {
  return useStore(regionDialogStore, selector);
}

export function startRegionRename(region: Region): void {
  regionDialogStore.setState({ rename: { regionId: region.id, name: region.name ?? '' } });
}

export function closeRegionDialogs(): void {
  regionDialogStore.setState({ rename: null });
}
