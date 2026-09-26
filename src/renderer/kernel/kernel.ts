import { jobFinished, jobProgress, jobStarted } from '../state/jobStore';
import { KernelClient } from './KernelClient';

let client: KernelClient | null = null;

/** The application's kernel client (created on first use). */
export function kernel(): KernelClient {
  client ??= new KernelClient(window.m2c.kernel, {
    started: jobStarted,
    progress: jobProgress,
    finished: jobFinished,
  });
  return client;
}
