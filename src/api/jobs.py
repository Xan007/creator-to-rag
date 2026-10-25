"""Background job manager for long-running pipeline operations."""
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

from storage.db import get_session
import storage.repositories as repo

logger = logging.getLogger(__name__)


class JobCancelledError(Exception):
    pass


class JobAdapter:
    """Provides a consistent dictionary interface for API serialization."""
    def __init__(self, j):
        self.id = j.id
        self.kind = j.kind
        self.status = j.status
        self.created_at = j.created_at
        self.started_at = j.started_at
        self.finished_at = j.finished_at
        self.result = j.result
        self.error = j.error
        self.log = j.log or []

    def to_dict(self, include_log: bool = True, log_limit: int = 200) -> Dict[str, Any]:
        log_limit = max(0, min(log_limit, 2000))
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_s": (
                round((self.finished_at or time.time()) - self.started_at, 1)
                if self.started_at
                else None
            ),
            "result": self.result,
            "error": self.error,
            "log": (self.log[-log_limit:] if log_limit else []) if include_log else None,
        }


def _run_job_process(job_id: str, kind: str, fn: Callable, args: tuple, kwargs: dict):
    # Transition to running with a short-lived DB session
    init_db = get_session()
    try:
        job = repo.get_job(init_db, job_id)
        if not job or job.status == "cancelled":
            return
        job.status = "running"
        job.started_at = time.time()
        repo.update_job(init_db, job)
    finally:
        init_db.close()

    def progress(msg: str):
        # Dedicated session per progress step to prevent keeping DB locks
        p_db = get_session()
        try:
            current_job = repo.get_job(p_db, job_id)
            if current_job and current_job.status == "cancelled":
                logger.info("[job %s] cancellation requested", job_id)
                raise JobCancelledError("Job was cancelled by user")
            repo.append_job_log(p_db, job_id, msg)
            logger.info("[job %s] %s", job_id, msg)
        finally:
            p_db.close()

    if "progress_kw" in kwargs:
        pk = kwargs.pop("progress_kw")
        if pk:
            kwargs[pk] = progress

    try:
        # Execute long-running work WITHOUT holding a database session
        result = fn(*args, **kwargs)

        done_db = get_session()
        try:
            job = repo.get_job(done_db, job_id)
            if job:
                # Do not overwrite if cancellation occurred in parallel
                if job.status != "cancelled":
                    job.result = result
                    job.status = "completed"
                job.finished_at = time.time()
                repo.update_job(done_db, job)
        finally:
            done_db.close()

    except JobCancelledError:
        logger.info("Job %s marked cancelled", job_id)
        c_db = get_session()
        try:
            job = repo.get_job(c_db, job_id)
            if job:
                job.status = "cancelled"
                job.finished_at = time.time()
                repo.update_job(c_db, job)
        finally:
            c_db.close()

    except Exception as e:
        logger.exception("Job %s failed", job_id)
        err_db = get_session()
        try:
            job = repo.get_job(err_db, job_id)
            if job:
                job.error = f"{type(e).__name__}: {e}"
                job.status = "failed"
                job.finished_at = time.time()
                repo.update_job(err_db, job)
                repo.append_job_log(err_db, job_id, job.error)
        finally:
            err_db.close()


class JobManager:
    """Serializes heavy pipeline jobs on a single worker."""

    def __init__(self, max_workers: int = 1):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self.cleanup_stuck_jobs()

    def cleanup_stuck_jobs(self) -> None:
        """Mark any jobs left in 'running' state as failed after server restart."""
        db = get_session()
        try:
            from storage.models import JobRecord
            stuck_jobs = db.query(JobRecord).filter(JobRecord.status.in_(("running", "queued"))).all()
            for j in stuck_jobs:
                j.status = "failed"
                j.error = "Worker restarted before job completed; submit it again to retry."
                j.finished_at = time.time()
            if stuck_jobs:
                db.commit()
                logger.info("Cleaned up %d stuck running jobs from prior session.", len(stuck_jobs))
        except Exception as e:
            logger.warning("Error cleaning up stuck jobs: %s", e)
        finally:
            db.close()

    def submit(
        self,
        kind: str,
        fn: Callable[..., Any],
        *args: Any,
        progress_kw: Optional[str] = "progress",
        **kwargs: Any,
    ):
        job_id = uuid.uuid4().hex[:12]
        db = get_session()
        try:
            job = repo.create_job(db, job_id, kind)
        finally:
            db.close()

        kwargs["progress_kw"] = progress_kw
        self._executor.submit(_run_job_process, job_id, kind, fn, args, kwargs)
        return type("DummyJob", (), {"id": job_id, "kind": kind})()

    def cancel(self, job_id: str) -> bool:
        db = get_session()
        try:
            job = repo.get_job(db, job_id)
            if job and job.status in ("queued", "running"):
                job.status = "cancelled"
                repo.update_job(db, job)
                repo.append_job_log(db, job_id, "Job cancellation requested by user.")
                return True
            return False
        finally:
            db.close()

    def get(self, job_id: str) -> Optional[JobAdapter]:
        db = get_session()
        try:
            job = repo.get_job(db, job_id)
            return JobAdapter(job) if job else None
        finally:
            db.close()

    def current(self) -> Optional[JobAdapter]:
        db = get_session()
        try:
            from storage.models import JobRecord
            job = db.query(JobRecord).filter(JobRecord.status == "running").first()
            return JobAdapter(job) if job else None
        finally:
            db.close()

    def all_jobs(self) -> List[JobAdapter]:
        db = get_session()
        try:
            from storage.models import JobRecord
            jobs = db.query(JobRecord).order_by(JobRecord.created_at.desc()).limit(100).all()
            return [JobAdapter(j) for j in jobs]
        finally:
            db.close()


manager = JobManager()
