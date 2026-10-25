import { useCallback, useEffect, useRef, useState } from 'react';
import { Activity, CheckCircle2, AlertCircle, Bell, XCircle } from 'lucide-react';
import { useTranslation } from '../../lib/i18n';
import { cn } from '../../lib/utils';
import { useJobs } from '../../hooks/useJobs';
import type { JobInfo } from '../../lib/api-types';
import { JobConsoleModal } from '../modals/JobConsoleModal';

export function NotificationsBell() {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [toast, setToast] = useState<{ msg: string; type: 'success' | 'error' } | null>(null);

  const showToast = useCallback((msg: string, type: 'success' | 'error') => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    setToast({ msg, type });
    toastTimerRef.current = setTimeout(() => setToast(null), 5000);
  }, []);

  useEffect(
    () => () => {
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    },
    [],
  );

  const handleStatusChange = useCallback(
    (job: JobInfo, previousStatus: string | undefined) => {
      if (previousStatus !== 'running' && previousStatus !== 'queued') return;
      if (job.status === 'completed') {
        showToast(t('jobs.taskCompleted', { kind: job.kind }), 'success');
      } else if (job.status === 'failed') {
        showToast(t('jobs.taskFailed', { kind: job.kind }), 'error');
      }
    },
    [showToast, t],
  );

  const { jobs } = useJobs({ onStatusChange: handleStatusChange });

  // Reset scroll to top when opening dropdown
  useEffect(() => {
    if (isOpen && scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = 0;
    }
  }, [isOpen]);

  // Close dropdown on click outside
  useEffect(() => {
    if (!isOpen) return;
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  const runningCount = jobs.filter((job) => job.status === 'running' || job.status === 'queued').length;

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'completed': return t('jobs.statusCompleted');
      case 'failed': return t('jobs.statusFailed');
      case 'cancelled': return t('jobs.statusCancelled');
      case 'running': return t('jobs.statusRunning');
      case 'queued': return t('jobs.statusQueued');
      default: return status;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return 'bg-emerald-50 text-emerald-700 border-emerald-200';
      case 'failed':
        return 'bg-red-50 text-red-700 border-red-200';
      case 'cancelled':
        return 'bg-slate-100 text-slate-600 border-slate-200';
      case 'running':
        return 'bg-blue-50 text-blue-700 border-blue-200';
      case 'queued':
        return 'bg-amber-50 text-amber-700 border-amber-200';
      default:
        return 'bg-slate-100 text-slate-600 border-slate-200';
    }
  };

  const getKindLabel = (kind: string) => {
    switch (kind?.toLowerCase()) {
      case 'run': return t('jobs.kindRun');
      case 'hydrate': return t('jobs.kindHydrate');
      case 'profile': return t('jobs.kindProfile');
      case 'reel': return t('jobs.kindReel');
      case 'scrape': return t('jobs.kindScrape');
      default: return kind?.toUpperCase() || t('jobs.kindUnknown');
    }
  };

  return (
    <>
      
      {toast && (
        <div className={`fixed top-6 right-6 z-[100] px-4 py-3 rounded-lg shadow-xl border animate-in slide-in-from-top-2 flex items-center gap-3 ${
          toast.type === 'success' ? 'bg-green-50 border-green-200 text-green-800' : 'bg-red-50 border-red-200 text-red-800'
        }`}>
          {toast.type === 'success' ? <CheckCircle2 size={18} className="text-green-500" /> : <AlertCircle size={18} className="text-red-500" />}
          <span className="text-sm font-medium">{toast.msg}</span>
        </div>
      )}

      <div className="relative" ref={dropdownRef}>
        <button
          type="button"
          onClick={() => setIsOpen((open) => !open)}
          className={cn(
            'relative p-2 text-slate-500 hover:text-slate-900 transition-colors rounded-lg hover:bg-slate-100 cursor-pointer',
            isOpen && 'bg-slate-100 text-slate-900',
          )}
          title={t('header.notifications')}
        >
          <Bell size={20} />
          {runningCount > 0 && (
            <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-blue-600 rounded-full ring-2 ring-white animate-pulse" />
          )}
        </button>

        {isOpen && (
          <div className="absolute right-0 mt-2 w-80 sm:w-96 bg-white border border-slate-200 shadow-xl rounded-xl overflow-hidden z-50 animate-in fade-in zoom-in-95 duration-150">
            <div className="px-4 py-3 border-b border-slate-100 bg-slate-50/80 flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-700">
                {t('jobs.notifications')}
              </h3>
              {runningCount > 0 && (
                <span className="text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200 px-2 py-0.5 rounded-full">
                  {t('jobs.jobsRunning', { count: runningCount })}
                </span>
              )}
            </div>
            <div ref={scrollContainerRef} className="max-h-80 overflow-y-auto divide-y divide-slate-100 text-xs">
              {jobs.length === 0 ? (
                <div className="p-8 text-center text-slate-400">
                  {t('jobs.noTasks')}
                </div>
              ) : (
                jobs.map((job) => (
                  <button
                    key={job.id}
                    type="button"
                    onClick={() => {
                      setSelectedJobId(job.id);
                      setIsOpen(false);
                    }}
                    className="w-full text-left p-3.5 hover:bg-slate-50 transition-colors flex items-start gap-3 group cursor-pointer"
                  >
                    <div className="mt-0.5 shrink-0">
                      {job.status === 'running' || job.status === 'queued' ? (
                        <Activity size={15} className="text-blue-600 animate-spin" />
                      ) : job.status === 'completed' ? (
                        <CheckCircle2 size={15} className="text-emerald-600" />
                      ) : job.status === 'cancelled' ? (
                        <XCircle size={15} className="text-slate-400" />
                      ) : (
                        <AlertCircle size={15} className="text-red-500" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <p className="text-xs font-semibold text-slate-900 truncate">
                          {getKindLabel(job.kind)}
                        </p>
                        <span className={cn('text-[10px] px-2 py-0.5 rounded-full font-medium border shrink-0', getStatusBadge(job.status))}>
                          {getStatusLabel(job.status)}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-500 truncate font-mono">
                        {job.log && job.log.length > 0 ? job.log[job.log.length - 1] : t('jobs.taskLabel', { id: job.id?.slice(0, 8) })}
                      </p>
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>
        )}
      </div>

      <JobConsoleModal
        isOpen={!!selectedJobId}
        onClose={() => setSelectedJobId(null)}
        jobId={selectedJobId}
      />
    </>
  );
}
