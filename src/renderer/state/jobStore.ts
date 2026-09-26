import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

import type { KernelStatus } from '@shared/bridge';

export interface RunningJob {
  clientId: number;
  method: string;
  lane: string | null;
  exclusive: boolean;
  fraction: number | null;
  stage: string | null;
  startedAt: number;
}

export interface JobState {
  kernel: KernelStatus;
  jobs: Record<number, RunningJob>;
}

export const jobStore = createStore<JobState>(() => ({ kernel: { state: 'starting' }, jobs: {} }));

export function useJobs<T>(selector: (state: JobState) => T): T {
  return useStore(jobStore, selector);
}

export function setKernelStatus(kernel: KernelStatus): void {
  jobStore.setState({ kernel });
}

export function jobStarted(job: Omit<RunningJob, 'fraction' | 'stage' | 'startedAt'>): void {
  jobStore.setState((state) => ({
    jobs: {
      ...state.jobs,
      [job.clientId]: { ...job, fraction: null, stage: null, startedAt: Date.now() },
    },
  }));
}

export function jobProgress(clientId: number, fraction: number | null, stage: string): void {
  jobStore.setState((state) => {
    const job = state.jobs[clientId];
    return job ? { jobs: { ...state.jobs, [clientId]: { ...job, fraction, stage } } } : state;
  });
}

export function jobFinished(clientId: number): void {
  jobStore.setState((state) => {
    const { [clientId]: _finished, ...jobs } = state.jobs;
    return { jobs };
  });
}

/** An exclusive job (segmentation, deviation) blocks tools and undo while it runs. */
export function exclusiveJobRunning(state: JobState = jobStore.getState()): boolean {
  return Object.values(state.jobs).some((job) => job.exclusive);
}
