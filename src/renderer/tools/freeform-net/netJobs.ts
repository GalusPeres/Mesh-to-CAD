// The freeform-net tool's kernel requests: one at a time (a new one cancels the
// running one), with its kind and progress in the editor state and its failure as
// the editor's error. Cancelled or superseded requests resolve to null.

import type { MethodName } from '@shared/protocol/generated/index';

import { isSilentFailure } from '../../kernel/KernelFailure';
import type { KernelJob, ParamsOf, ResultOf } from '../../kernel/KernelClient';
import { kernel } from '../../kernel/kernel';
import { toFailure } from '../framework/hooks';
import type { NetEditorState, NetJobKind } from './netState';

export class NetJobs {
  private running: KernelJob<unknown> | null = null;

  constructor(
    private readonly lane: string,
    private readonly update: (patch: Partial<NetEditorState>) => void,
    /** False once the tool is closed: a finished job no longer touches the state. */
    private readonly shown: () => boolean,
  ) {}

  async run<M extends MethodName>(
    kind: NetJobKind,
    method: M,
    params: ParamsOf<M>,
  ): Promise<ResultOf<M> | null> {
    this.running?.cancel();
    const job = kernel().call(method, params, { lane: `${method}:${this.lane}` });
    this.running = job;
    this.update({ job: { kind, fraction: null, stage: null }, error: null });
    job.onProgress((fraction, stage) => {
      if (this.running === job) this.update({ job: { kind, fraction, stage } });
    });
    try {
      return await job.result;
    } catch (error) {
      if (this.running === job && !isSilentFailure(error)) this.update({ error: toFailure(error) });
      return null;
    } finally {
      if (this.running === job) {
        this.running = null;
        if (this.shown()) this.update({ job: null });
      }
    }
  }

  cancel(): void {
    this.running?.cancel();
  }
}
