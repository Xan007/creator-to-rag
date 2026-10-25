import { useCallback, useEffect, useRef, useState } from 'react';
import { api, isAbortError } from '../lib/api';
import type { JobInfo } from '../lib/api-types';

const RUNNING_POLL_MS = 3_000;
const IDLE_POLL_MS = 15_000;

function isRunning(job: JobInfo): boolean {
  return job.status === 'running' || job.status === 'queued';
}

/** Cheap structural comparison so identical polls don't trigger React renders. */
function jobsChanged(previous: JobInfo[], next: JobInfo[]): boolean {
  if (previous.length !== next.length) return true;
  for (let index = 0; index < next.length; index += 1) {
    const a = previous[index];
    const b = next[index];
    if (!a || !b) return true;
    if (a.id !== b.id || a.status !== b.status) return true;
    if ((a.log?.length ?? 0) !== (b.log?.length ?? 0)) return true;
    if ((a.log?.[a.log.length - 1] ?? '') !== (b.log?.[b.log.length - 1] ?? '')) return true;
    if ((a.error ?? '') !== (b.error ?? '')) return true;
    if ((a.finished_at ?? null) !== (b.finished_at ?? null)) return true;
  }
  return false;
}

interface UseJobsOptions {
  /** Called when a job transitions between statuses (e.g. running -> completed). */
  onStatusChange?: (job: JobInfo, previousStatus: string | undefined) => void;
  enabled?: boolean;
}

/**
 * Single source of truth for background-job polling.
 *
 * - Only one request in flight, even if the app has several consumers.
 * - Faster cadence while something is running, slow cadence when idle.
 * - Pauses while the tab is hidden (no wasted requests in background tabs).
 */
export function useJobs({ onStatusChange, enabled = true }: UseJobsOptions = {}) {
  const [jobs, setJobs] = useState<JobInfo[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const jobsRef = useRef<JobInfo[]>([]);
  const callbackRef = useRef(onStatusChange);

  useEffect(() => {
    callbackRef.current = onStatusChange;
  }, [onStatusChange]);

  const applyJobs = useCallback((next: JobInfo[]) => {
    const previous = jobsRef.current;
    const previousById = new Map(previous.map((job) => [job.id, job.status]));

    next.forEach((job) => {
      const previousStatus = previousById.get(job.id);
      if (previousStatus !== undefined && previousStatus !== job.status) {
        callbackRef.current?.(job, previousStatus);
      }
    });

    jobsRef.current = next;
    if (jobsChanged(previous, next)) setJobs(next);
  }, []);

  useEffect(() => {
    if (!enabled) return;

    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let inFlight: AbortController | undefined;

    function schedule(delay: number) {
      if (disposed) return;
      if (timer) clearTimeout(timer);
      timer = setTimeout(poll, delay);
    }

    async function poll() {
      if (disposed) return;
      if (typeof document !== 'undefined' && document.hidden) {
        schedule(IDLE_POLL_MS);
        return;
      }

      inFlight?.abort();
      const controller = new AbortController();
      inFlight = controller;

      try {
        const data = await api.getJobs({ signal: controller.signal });
        if (disposed) return;
        const nextJobs = Array.isArray(data?.jobs) ? data.jobs : [];
        applyJobs(nextJobs);
        schedule(nextJobs.some(isRunning) ? RUNNING_POLL_MS : IDLE_POLL_MS);
      } catch (error) {
        if (isAbortError(error) || disposed) return;
        // Backend unreachable: keep the last known state and retry slowly.
        schedule(IDLE_POLL_MS);
      } finally {
        if (inFlight === controller) inFlight = undefined;
        if (!disposed) setIsLoading(false);
      }
    }

    const handleVisibility = () => {
      if (!document.hidden) {
        if (timer) clearTimeout(timer);
        void poll();
      }
    };

    void poll();
    document.addEventListener('visibilitychange', handleVisibility);

    return () => {
      disposed = true;
      if (timer) clearTimeout(timer);
      inFlight?.abort();
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, [applyJobs, enabled]);

  return { jobs, isLoading };
}
