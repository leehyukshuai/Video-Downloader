from __future__ import annotations

import threading
from typing import Any

from .utils import job_status_label, now_iso


class JobStore:
    def __init__(self):
        self.lock = threading.RLock()
        self.jobs: dict[str, dict[str, Any]] = {}

    def _trim_logs(self, lines: list[str], max_lines: int = 200) -> list[str]:
        return lines[-max_lines:]

    def create(self, payload: dict[str, Any], job_id: str) -> str:
        job = {
            "id": job_id,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "status": "queued",
            "status_label": job_status_label("queued"),
            "stage_text": job_status_label("queued"),
            "url": payload["url"],
            "title": payload.get("title") or "",
            "thumbnail": payload.get("thumbnail") or "",
            "output_dir": payload.get("output_dir") or "",
            "progress_percent": 0.0,
            "downloaded_bytes": 0,
            "downloaded_text": "0 B",
            "total_bytes": None,
            "total_text": "未知",
            "speed_text": "-",
            "eta_text": "-",
            "current_file": "",
            "final_path": "",
            "merge_format": payload.get("merge_format") or "",
            "video_format_id": payload.get("video_format_id"),
            "audio_format_id": payload.get("audio_format_id"),
            "audio_only": bool(payload.get("audio_only")),
            "warnings": [],
            "logs": [],
            "error": "",
            "can_pause": False,
            "can_resume": False,
            "can_cancel": True,
        }
        with self.lock:
            self.jobs[job_id] = job
        return job_id

    def update(self, job_id: str, **changes) -> None:
        with self.lock:
            job = self.jobs[job_id]
            job.update(changes)
            status = job.get("status")
            job["status_label"] = job_status_label(status)
            if "stage_text" not in changes and status in {"queued", "starting", "paused", "cancelled", "completed", "error"}:
                job["stage_text"] = job["status_label"]
            job["updated_at"] = now_iso()
            if status in {"queued", "starting", "downloading", "processing", "merging"}:
                job["can_cancel"] = True
                job["can_pause"] = status in {"downloading", "processing"}
                job["can_resume"] = False
            elif status == "paused":
                job["can_cancel"] = True
                job["can_pause"] = False
                job["can_resume"] = True
            else:
                job["can_cancel"] = False
                job["can_pause"] = False
                job["can_resume"] = False

    def append_log(self, job_id: str, line: str) -> None:
        with self.lock:
            job = self.jobs[job_id]
            job.setdefault("logs", []).append(line)
            job["logs"] = self._trim_logs(job["logs"])
            job["updated_at"] = now_iso()

    def append_warning(self, job_id: str, line: str) -> None:
        with self.lock:
            job = self.jobs[job_id]
            job.setdefault("warnings", []).append(line)
            job["warnings"] = self._trim_logs(job["warnings"], 20)
            job["updated_at"] = now_iso()

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.lock:
            job = self.jobs.get(job_id)
            return dict(job) if job else None

    def clear(self) -> None:
        with self.lock:
            self.jobs.clear()
