import {
  BookmarkPlus,
  Combine,
  Eye,
  EyeOff,
  Focus,
  MousePointerClick,
  Pencil,
  SquareMinus,
  SquarePlus,
  Trash2,
} from 'lucide-react';

import type { AppCommand } from '../app/commands/types';
import { documentStore } from '../state/documentStore';
import { exclusiveJobRunning } from '../state/jobStore';
import {
  addSelectionToRegion,
  deleteRegions,
  mergeRegions,
  removeSelectionFromRegion,
  saveSelectionAsRegion,
  selectRegions,
  selectedRegions,
  startRegionRename,
} from './regionActions';
import {
  clearSelectedFaces,
  growSelection,
  hasHidden,
  hasSelection,
  hideSelection,
  invertSelection,
  isolateSelection,
  selectAllVisible,
  showAllFaces,
  shrinkSelection,
} from './selectionEdits';

function hasScan(): boolean {
  return !!documentStore.getState().snapshot?.document.scan && !exclusiveJobRunning();
}

const SELECTION_GROUP = 3;
const VISIBILITY_GROUP = 4;
const REGION_GROUP = 5;

function selectionCommand(
  id: string,
  shortcut: AppCommand['shortcuts'],
  order: number,
  run: () => unknown,
  isEnabled: () => boolean = hasScan,
  group = SELECTION_GROUP,
  icon?: AppCommand['icon'],
): AppCommand {
  return {
    id: `selection.${id}`,
    label: `selection:commands.${id}`,
    icon,
    shortcuts: shortcut,
    scope: 'viewport',
    placement: { menu: 'edit', group, order },
    isEnabled,
    run: async () => {
      await run();
    },
  };
}

const withSelection = () => hasScan() && hasSelection();
const oneRegion = () => hasScan() && selectedRegions().length === 1;
const oneRegionAndSelection = () => oneRegion() && hasSelection();

export const commands: readonly AppCommand[] = [
  selectionCommand('selectAllVisible', [{ key: 'a', ctrl: true }], 1, selectAllVisible),
  selectionCommand('clear', [{ key: 'd', ctrl: true }], 2, clearSelectedFaces, withSelection),
  selectionCommand('invert', [{ key: 'i', ctrl: true, shift: true }], 3, invertSelection),
  selectionCommand('grow', [{ key: 'g' }], 4, growSelection, withSelection),
  selectionCommand('shrink', [{ key: 'g', shift: true }], 5, shrinkSelection, withSelection),
  selectionCommand(
    'hide',
    [{ key: 'h' }],
    1,
    hideSelection,
    withSelection,
    VISIBILITY_GROUP,
    EyeOff,
  ),
  selectionCommand(
    'showAll',
    [{ key: 'h', shift: true }],
    2,
    showAllFaces,
    () => hasScan() && hasHidden(),
    VISIBILITY_GROUP,
    Eye,
  ),
  selectionCommand(
    'isolate',
    [{ key: 'i' }],
    3,
    isolateSelection,
    withSelection,
    VISIBILITY_GROUP,
    Focus,
  ),
  selectionCommand(
    'saveAsRegion',
    [{ key: 'r', ctrl: true }],
    1,
    saveSelectionAsRegion,
    withSelection,
    REGION_GROUP,
    BookmarkPlus,
  ),
  selectionCommand(
    'selectRegion',
    undefined,
    2,
    () => selectRegions(selectedRegions()),
    () => hasScan() && selectedRegions().length > 0,
    REGION_GROUP,
    MousePointerClick,
  ),
  selectionCommand(
    'addToRegion',
    undefined,
    3,
    async () => {
      const [region] = selectedRegions();
      if (region) await addSelectionToRegion(region);
    },
    oneRegionAndSelection,
    REGION_GROUP,
    SquarePlus,
  ),
  selectionCommand(
    'removeFromRegion',
    undefined,
    4,
    async () => {
      const [region] = selectedRegions();
      if (region) await removeSelectionFromRegion(region);
    },
    oneRegionAndSelection,
    REGION_GROUP,
    SquareMinus,
  ),
  selectionCommand(
    'mergeRegions',
    undefined,
    5,
    () => mergeRegions(selectedRegions()),
    () => hasScan() && selectedRegions().length >= 2,
    REGION_GROUP,
    Combine,
  ),
  selectionCommand(
    'renameRegion',
    undefined,
    6,
    () => {
      const [region] = selectedRegions();
      if (region) startRegionRename(region);
    },
    oneRegion,
    REGION_GROUP,
    Pencil,
  ),
  selectionCommand(
    'deleteRegions',
    undefined,
    7,
    () => deleteRegions(selectedRegions()),
    () => hasScan() && selectedRegions().length > 0,
    REGION_GROUP,
    Trash2,
  ),
];
