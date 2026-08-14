from __future__ import annotations

import threading

from app.core.config import Settings
from app.workers.tasks import execute_query_job


def dispatch_query_job(job_id: str, settings: Settings) -> None:
    mode = settings.query_execution_mode.strip().lower()
    if mode == "celery":
        execute_query_job.delay(job_id)
        return
    if mode == "thread":
        threading.Thread(
            target=execute_query_job.run,
            args=(job_id,),
            name=f"event-export-{job_id[:8]}",
            daemon=True,
        ).start()
        return
    raise RuntimeError("QUERY_EXECUTION_MODE 只允许 thread 或 celery。")
