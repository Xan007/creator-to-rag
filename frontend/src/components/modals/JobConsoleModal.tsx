import { useState, useEffect, useRef, useCallback } from "react";
import { Loader2, Terminal, X, RefreshCw } from "lucide-react";
import { api, isAbortError } from "../../lib/api";
import { useTranslation } from "../../lib/i18n";
import type { JobInfo } from "../../lib/api-types";

interface JobConsoleModalProps {
  isOpen: boolean;
  onClose: () => void;
  jobId: string | null;
}

function useJobConsoleModalModel({
  isOpen,
  onClose,
  jobId,
}: JobConsoleModalProps) {
  const { t } = useTranslation();
  const [job, setJob] = useState<JobInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const jobStatusRef = useRef<string | undefined>(undefined);

  const fetchJob = useCallback(
    async (signal?: AbortSignal) => {
      if (!jobId) return;
      try {
        const data = await api.getJob(jobId, { signal });
        if (signal?.aborted) return;
        setJob(data);
        jobStatusRef.current = data?.status;
      } catch (error) {
        if (!isAbortError(error)) console.error(error);
      } finally {
        setLoading(false);
      }
    },
    [jobId],
  );

  useEffect(() => {
    const controller = new AbortController();
    let inFlight = false;
    const tick = async () => {
      if (inFlight || controller.signal.aborted) return;
      inFlight = true;
      try {
        await fetchJob(controller.signal);
      } finally {
        inFlight = false;
      }
    };
    const timer = setInterval(() => {
      const active = ["running", "queued"].includes(jobStatusRef.current ?? "");
      if (active) void tick();
      else clearInterval(timer);
    }, 2000);
    if (isOpen && jobId) void tick();
    return () => {
      clearInterval(timer);
      controller.abort();
    };
  }, [isOpen, jobId, fetchJob]);

  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [job?.log?.length]);

  const handleCancel = async () => {
    if (!jobId) return;
    if (!confirm(t("jobs.cancelPrompt"))) return;
    try {
      await api.cancelJob(jobId);
      await fetchJob();
    } catch (error) {
      alert(
        t("jobs.cancelFailed") + (error instanceof Error ? error.message : ""),
      );
    }
  };

  if (!isOpen) return null;

  return { onClose, t, job, loading, logsEndRef, handleCancel };
}

export function JobConsoleModal(
  props: Parameters<typeof useJobConsoleModalModel>[0],
) {
  const model = useJobConsoleModalModel(props);
  if (!model) return null;
  return <ConsoleOverlay model={model} />;
}

function ConsoleOverlay({
  model,
}: {
  model: NonNullable<ReturnType<typeof useJobConsoleModalModel>>;
}) {
  return (
    <div className="fixed inset-0 z-[60] bg-black/60 flex flex-col items-center justify-center p-4 md:p-10 animate-in fade-in">
      <ConsoleWindow model={model} />
    </div>
  );
}

function logEntries(lines: string[]) {
  const counts = new Map<string, number>();
  return lines.map((text) => {
    const count = counts.get(text) ?? 0;
    counts.set(text, count + 1);
    return { text, id: `${text}-${count}` };
  });
}

function ConsoleWindow({
  model,
}: {
  model: NonNullable<ReturnType<typeof useJobConsoleModalModel>>;
}) {
  return (
    <div className="bg-[#1e1e1e] border border-gray-700 rounded-xl shadow-2xl w-full max-w-4xl flex flex-col overflow-hidden max-h-[90vh]">
      <ConsoleHeader model={model} />

      <ConsoleOutput model={model} />
    </div>
  );
}

function ConsoleOutput({
  model,
}: {
  model: NonNullable<ReturnType<typeof useJobConsoleModalModel>>;
}) {
  const { loading, job, t, logsEndRef } = model;
  return (
    <div className="flex-1 bg-[#121212] p-4 overflow-y-auto font-mono text-[13px] leading-relaxed text-gray-300">
      {loading && !job ? (
        <div className="flex items-center gap-2 text-slate-400 h-full justify-center">
          <Loader2 size={16} className="animate-spin" />
          <span>{t("jobs.connecting")}</span>
        </div>
      ) : !job ? (
        <div className="text-red-400">{t("jobs.jobNotFound")}</div>
      ) : (
        <div className="space-y-1">
          <div className="text-gray-500">
            System: Initialized job {job.id} at{" "}
            {new Date((job.created_at ?? 0) * 1000).toLocaleString()}
          </div>
          {job.error && (
            <div className="text-red-400 mt-4 mb-4 font-semibold">
              FATAL EXCEPTION: {job.error}
            </div>
          )}
          {logEntries(job.log ?? []).map(({ text: log, id }) => (
            <div
              key={id}
              className="flex gap-4 hover:bg-white/5 px-2 -mx-2 rounded transition-colors"
            >
              <span
                className={
                  log.toLowerCase().includes("error") ||
                  log.toLowerCase().includes("fail")
                    ? "text-red-400"
                    : log.includes("cancellation")
                      ? "text-yellow-400"
                      : "text-gray-300"
                }
              >
                {log}
              </span>
            </div>
          ))}
          {job.status === "running" && (
            <div className="flex gap-4 px-2 -mx-2 mt-2 items-center text-slate-400">
              <span className="text-gray-600 shrink-0">--:--:--</span>
              <span className="flex items-center gap-2">
                <RefreshCw size={12} className="animate-spin" />
                {t("jobs.processing")}
              </span>
            </div>
          )}
          {job.status === "completed" && Boolean(job.result) && (
            <div className="mt-4 p-4 bg-[#1e1e1e] border border-gray-700 rounded-lg">
              <div className="text-green-400 font-bold mb-2 flex items-center gap-2">
                ✓ {t("jobs.jobStats")}
              </div>
              <pre className="text-gray-300 text-xs font-mono overflow-x-auto">
                {JSON.stringify(job.result, null, 2)}
              </pre>
            </div>
          )}
          {job.status === "completed" && !job.result && (
            <div className="text-green-400 mt-2 flex items-center gap-2">
              <span className="text-green-400 font-bold">✓</span>{" "}
              {t("jobs.jobFinished")}
            </div>
          )}
          <div ref={logsEndRef} className="h-4" />
        </div>
      )}
    </div>
  );
}

function ConsoleHeader({
  model,
}: {
  model: NonNullable<ReturnType<typeof useJobConsoleModalModel>>;
}) {
  const { job, t, handleCancel, onClose } = model;
  return (
    <div className="h-12 bg-[#2d2d2d] border-b border-gray-700 flex items-center justify-between px-4 shrink-0">
      <div className="flex items-center gap-2 text-gray-300">
        <Terminal size={16} className="text-slate-400" />
        <span className="text-sm font-mono tracking-tight">
          {job
            ? t("jobs.consoleTitle", { kind: job.kind, id: job.id })
            : t("jobs.loadingConsole")}
        </span>
        {job && (
          <span
            className={`ml-3 px-2 py-0.5 rounded text-[10px] uppercase font-bold tracking-wider ${
              job.status === "running"
                ? "bg-slate-500/20 text-slate-400"
                : job.status === "queued"
                  ? "bg-yellow-500/20 text-yellow-400"
                  : job.status === "completed"
                    ? "bg-green-500/20 text-green-400"
                    : job.status === "cancelled"
                      ? "bg-gray-500/20 text-gray-400"
                      : "bg-red-500/20 text-red-400"
            }`}
          >
            {job.status}
          </span>
        )}
      </div>
      <div className="flex items-center gap-3">
        {job && (job.status === "running" || job.status === "queued") && (
          <button
            onClick={handleCancel}
            className="text-xs font-medium text-red-400 hover:text-red-300 border border-red-900/50 hover:bg-red-900/20 px-2 py-1 rounded transition-colors cursor-pointer"
          >
            {t("jobs.cancelBtn")}
          </button>
        )}
        <button
          aria-label={t("modal.cancel")}
          onClick={onClose}
          className="text-gray-400 hover:text-white p-1 rounded hover:bg-white/10 transition-colors cursor-pointer"
        >
          <X size={18} />
        </button>
      </div>
    </div>
  );
}
