// The sketch draft of the open tool: its undo history (registered as the draft
// history, so Ctrl+Z undoes sketch edits while the tool is open), and the kernel
// refit that follows every edit in sketch mode.

import { useCallback, useEffect, useRef, useState } from 'react';

import type {
  AutoFitResult,
  EntityFitInfo,
  ProfileState,
  SketchFrame,
} from '@shared/protocol/generated/sketch';
import type { SketchParams } from '@shared/protocol/generated/sketch-params';

import type { KernelFailure } from '../../kernel/KernelFailure';
import { isSilentFailure } from '../../kernel/KernelFailure';
import { kernel } from '../../kernel/kernel';
import { setDraftHistoryHandler } from '../../state/historyStore';
import { setDraftDirty } from '../../state/toolStore';
import { toFailure } from '../framework/hooks';
import {
  type DraftHistory,
  canRedo,
  canUndo,
  currentDraft,
  pushDraft,
  redoDraft,
  replaceDraft,
  startHistory,
  undoDraft,
} from './draftHistory';

export const FIT_LANE = 'sketch.autoFit:section-sketch';

/** What the kernel reported for one version of the sketch. */
export interface FitState {
  fits: readonly EntityFitInfo[];
  profile: ProfileState;
  frame: SketchFrame;
  noise: number;
  tolerance: number;
}

export function fitStateOf(result: AutoFitResult): FitState {
  return {
    fits: result.fits,
    profile: result.profile,
    frame: result.frame,
    noise: result.noise,
    tolerance: result.tolerance,
  };
}

export interface SketchDraft {
  draft: SketchParams;
  /** Kernel state of the current draft; null while its refit runs. */
  fit: FitState | null;
  /** Last state known for any version (shown greyed while a refit runs). */
  lastFit: FitState | null;
  refitError: KernelFailure | null;
  /** A user edit: a new undo step, followed by a refit in sketch mode. */
  edit: (next: SketchParams) => void;
  /** Continue the current edit (a handle drag) without a new undo step. */
  adjust: (next: SketchParams) => void;
  /** A fitted sketch from the kernel (new fit or painted entity) with its state. */
  accept: (result: AutoFitResult) => void;
  /** The current draft, refitted first if an edit is still being refitted. */
  settled: () => Promise<SketchParams>;
  changed: boolean;
}

export function useSketchDraft(initial: SketchParams, refitEdits: boolean): SketchDraft {
  const [history, setHistory] = useState<DraftHistory<SketchParams>>(() => startHistory(initial));
  const [fits, setFits] = useState<ReadonlyMap<SketchParams, FitState>>(() => new Map());
  const [lastFit, setLastFit] = useState<FitState | null>(null);
  const [refitError, setRefitError] = useState<KernelFailure | null>(null);
  const latest = useRef(history);
  const draft = currentDraft(history);
  const changed = canUndo(history);

  useEffect(() => {
    latest.current = history;
  }, [history]);

  useEffect(() => {
    setDraftDirty(changed);
  }, [changed]);

  useEffect(() => {
    setDraftHistoryHandler({
      undo: () => {
        if (!canUndo(latest.current)) return false;
        setHistory(undoDraft);
        return true;
      },
      redo: () => {
        if (!canRedo(latest.current)) return false;
        setHistory(redoDraft);
        return true;
      },
    });
    return () => setDraftHistoryHandler(null);
  }, []);

  const remember = useCallback((sketch: SketchParams, state: FitState) => {
    setFits((previous) => new Map(previous).set(sketch, state));
    setLastFit(state);
    setRefitError(null);
  }, []);

  const needsRefit = refitEdits && draft.entities.length > 0 && !fits.has(draft);
  useEffect(() => {
    if (!needsRefit) return;
    let current = true;
    kernel()
      .call('sketch.autoFit', { sketch: draft, refit: true }, { lane: FIT_LANE })
      .result.then((result) => {
        if (!current) return;
        setHistory((h) => (currentDraft(h) === draft ? replaceDraft(h, result.sketch) : h));
        remember(result.sketch, fitStateOf(result));
      })
      .catch((error: unknown) => {
        if (current && !isSilentFailure(error)) setRefitError(toFailure(error));
      });
    return () => {
      current = false;
    };
  }, [draft, needsRefit, remember]);

  const edit = useCallback((next: SketchParams) => {
    setHistory((h) => pushDraft(h, next));
  }, []);

  const adjust = useCallback((next: SketchParams) => {
    setHistory((h) => replaceDraft(h, next));
  }, []);

  const accept = useCallback(
    (result: AutoFitResult) => {
      setHistory((h) => pushDraft(h, result.sketch));
      remember(result.sketch, fitStateOf(result));
    },
    [remember],
  );

  const settled = useCallback(async () => {
    const sketch = currentDraft(latest.current);
    if (!refitEdits || fits.has(sketch) || sketch.entities.length === 0) return sketch;
    const result = await kernel().call(
      'sketch.autoFit',
      { sketch, refit: true },
      { lane: FIT_LANE },
    ).result;
    return result.sketch;
  }, [fits, refitEdits]);

  return {
    draft,
    fit: fits.get(draft) ?? null,
    lastFit,
    refitError,
    edit,
    adjust,
    accept,
    settled,
    changed,
  };
}
