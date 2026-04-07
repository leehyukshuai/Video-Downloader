from __future__ import annotations

import ctypes
from pathlib import Path
import re
import subprocess
import threading
import uuid
from ctypes import wintypes
from typing import Any

from .config import AppConfig
from .jobs import JobStore
from .utils import format_bytes, parse_float, parse_percent_text

TH32CS_SNAPTHREAD = 0x00000004
THREAD_SUSPEND_RESUME = 0x0002
THREAD_QUERY_INFORMATION = 0x0040


class THREADENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ThreadID", wintypes.DWORD),
        ("th32OwnerProcessID", wintypes.DWORD),
        ("tpBasePri", wintypes.LONG),
        ("tpDeltaPri", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
    ]


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class DownloadManager:
    def __init__(self, config: AppConfig, job_store: JobStore):
        self.config = config
        self.job_store = job_store
        self._processes: dict[str, subprocess.Popen] = {}
        self._lock = threading.RLock()

    def validate_payload(self, payload: dict[str, Any]) -> None:
        url = (payload.get("url") or "").strip()
        if not url:
            raise ValueError("请先输入视频链接。")
        if not payload.get("audio_only") and not (payload.get("video_format_id") or "").strip():
            raise ValueError("请选择一个视频规格。")
        if payload.get("audio_only") and not (payload.get("audio_format_id") or "").strip():
            raise ValueError("仅音频模式下需要选择一个音频规格。")
        try:
            output_dir = self.config.resolve_output_dir(payload.get("output_dir"))
        except Exception as exc:
            raise ValueError(f"下载路径无效：{exc}") from exc
        payload["output_dir"] = str(output_dir)
        cookie_value = (payload.get("cookies_path") or "").strip()
        if cookie_value:
            cookie_file = Path(cookie_value).expanduser().resolve()
            if not cookie_file.exists():
                raise ValueError("cookies.txt 文件不存在。")
            payload["cookies_path"] = str(cookie_file)
        cookie_source = payload.get("cookie_source")
        if isinstance(cookie_source, dict):
            mode = str(cookie_source.get("mode") or "").strip().lower()
            value = str(cookie_source.get("value") or "").strip()
            label = str(cookie_source.get("label") or value or "").strip()
            if mode == "browser" and value:
                payload["cookie_source"] = {"mode": "browser", "value": value, "label": label}
            else:
                payload["cookie_source"] = {}
        else:
            payload["cookie_source"] = {}

    def create_job(self, payload: dict[str, Any]) -> str:
        self.validate_payload(payload)
        job_id = uuid.uuid4().hex[:12]
        return self.job_store.create(payload, job_id)

    def start(self, job_id: str, payload: dict[str, Any]) -> None:
        worker = threading.Thread(target=self._run_job, args=(job_id, payload), daemon=True)
        worker.start()

    def pause(self, job_id: str) -> None:
        proc = self._get_process(job_id)
        if not proc or proc.poll() is not None:
            raise ValueError("当前任务不可暂停。")
        self._suspend_process(proc.pid)
        self.job_store.update(job_id, status="paused", speed_text="-", eta_text="-")
        self.job_store.append_log(job_id, "任务已暂停。")

    def resume(self, job_id: str) -> None:
        proc = self._get_process(job_id)
        if not proc or proc.poll() is not None:
            raise ValueError("当前任务不可继续。")
        self._resume_process(proc.pid)
        self.job_store.update(job_id, status="downloading", stage_text="继续下载中")
        self.job_store.append_log(job_id, "任务已继续。")

    def cancel(self, job_id: str) -> None:
        proc = self._get_process(job_id)
        if proc and proc.poll() is None:
            proc.terminate()
        self.job_store.update(job_id, status="cancelled", speed_text="-", eta_text="-", error="用户已终止任务")
        self.job_store.append_log(job_id, "任务已终止。")

    def _get_process(self, job_id: str):
        with self._lock:
            return self._processes.get(job_id)

    def _set_process(self, job_id: str, proc):
        with self._lock:
            self._processes[job_id] = proc

    def _clear_process(self, job_id: str):
        with self._lock:
            self._processes.pop(job_id, None)

    def _iter_thread_ids(self, pid: int):
        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
        if snapshot == wintypes.HANDLE(-1).value:
            raise OSError("无法枚举线程")
        try:
            entry = THREADENTRY32()
            entry.dwSize = ctypes.sizeof(THREADENTRY32)
            success = kernel32.Thread32First(snapshot, ctypes.byref(entry))
            while success:
                if entry.th32OwnerProcessID == pid:
                    yield entry.th32ThreadID
                success = kernel32.Thread32Next(snapshot, ctypes.byref(entry))
        finally:
            kernel32.CloseHandle(snapshot)

    def _suspend_process(self, pid: int) -> None:
        for tid in self._iter_thread_ids(pid):
            handle = kernel32.OpenThread(THREAD_SUSPEND_RESUME, False, tid)
            if handle:
                try:
                    kernel32.SuspendThread(handle)
                finally:
                    kernel32.CloseHandle(handle)

    def _resume_process(self, pid: int) -> None:
        for tid in self._iter_thread_ids(pid):
            handle = kernel32.OpenThread(THREAD_SUSPEND_RESUME, False, tid)
            if handle:
                try:
                    while kernel32.ResumeThread(handle) > 0:
                        pass
                finally:
                    kernel32.CloseHandle(handle)

    def _build_command(self, payload: dict[str, Any], extra_args: list[str] | None = None) -> list[str]:
        output_dir = self.config.resolve_output_dir(payload.get("output_dir"))
        target_format = (payload.get("merge_format") or "").strip().lower()
        video_source_ext = (payload.get("video_source_ext") or "").strip().lower()
        audio_source_ext = (payload.get("audio_source_ext") or "").strip().lower()
        cmd = [
            *self.config.yt_dlp_command,
            "--ffmpeg-location",
            self.config.ffmpeg_location,
            *self.config.yt_dlp_runtime_args,
            "--no-playlist",
            "--newline",
            "--progress",
            "--progress-template",
            "download:PROGRESS|%(progress.status)s|%(progress.downloaded_bytes)s|%(progress.total_bytes)s|%(progress.total_bytes_estimate)s|%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s|%(progress.filename)s",
            "--print",
            "after_move:AFTERMOVE|%(filepath)s",
            "-P",
            str(output_dir),
            "-o",
            "%(title).200B [%(id)s].%(ext)s",
        ]
        if extra_args:
            cmd.extend(extra_args)
        cookies_path = (payload.get("cookies_path") or "").strip()
        if cookies_path:
            cmd.extend(["--cookies", cookies_path])
        else:
            cookie_source = payload.get("cookie_source") or {}
            if cookie_source.get("mode") == "browser" and cookie_source.get("value"):
                cmd.extend(["--cookies-from-browser", str(cookie_source["value"])])

        video_format_id = (payload.get("video_format_id") or "").strip()
        audio_format_id = (payload.get("audio_format_id") or "").strip()

        if video_format_id and audio_format_id:
            if target_format:
                cmd.extend(["--merge-output-format", target_format])
            selector = f"{video_format_id}+{audio_format_id}"
        elif video_format_id:
            if target_format and target_format != video_source_ext:
                cmd.extend(["--recode-video", target_format])
            selector = video_format_id
        elif audio_format_id:
            if target_format and target_format != audio_source_ext:
                cmd.extend(["-x", "--audio-format", target_format])
            selector = audio_format_id
        else:
            raise ValueError("请至少选择一个视频规格或音频规格。")
        cmd.extend(["-f", selector, payload["url"]])
        return cmd

    def _should_retry_ssl_compat(self, job_id: str, return_code: int) -> bool:
        if return_code == 0:
            return False
        job = self.job_store.get(job_id) or {}
        haystack = "\n".join([
            *(job.get("logs") or []),
            job.get("error") or "",
        ]).lower()
        markers = (
            "unexpected_eof_while_reading",
            "eof occurred in violation of protocol",
            "ssl:",
            "got error:",
        )
        return "eof" in haystack and all(marker in haystack for marker in markers)

    def _run_command(self, job_id: str, payload: dict[str, Any], cmd: list[str]) -> int:
        proc = subprocess.Popen(
            cmd,
            cwd=str(self.config.root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self._set_process(job_id, proc)

        assert proc.stdout is not None
        for raw_line in proc.stdout:
            line = raw_line.rstrip("\r\n")
            if not line:
                continue
            existing = self.job_store.get(job_id)
            if existing and existing.get("status") == "cancelled":
                break
            if line.startswith("PROGRESS|"):
                progress = self._parse_progress(line)
                if progress:
                    stage_key = self._detect_stage_key(payload, filename=progress.get("current_file") or "")
                    if stage_key:
                        self._set_stage(job_id, payload, stage_key)
                    raw_status = progress.get("status", "downloading")
                    mapped_status = "downloading" if raw_status == "downloading" else "processing"
                    payload2 = dict(progress)
                    payload2["status"] = mapped_status
                    current = self.job_store.get(job_id)
                    if current and current.get("status") != "paused":
                        self.job_store.update(job_id, **payload2)
                continue
            if line.startswith("AFTERMOVE|"):
                final_path = line.split("|", 1)[1]
                self.job_store.update(job_id, final_path=final_path, current_file=final_path, stage_text="整理文件中")
                self.job_store.append_log(job_id, f"输出文件：{final_path}")
                continue
            if "[Merger]" in line:
                self.job_store.update(job_id, status="merging", progress_percent=100.0, speed_text="-", eta_text="-")
                self._set_stage(job_id, payload, "merge")
            elif line.startswith("WARNING:"):
                self.job_store.append_warning(job_id, line)
            self.job_store.append_log(job_id, line)

        return proc.wait()

    def _match_format_id(self, filename: str, format_id: str) -> bool:
        if not filename or not format_id:
            return False
        lowered = filename.lower()
        escaped = re.escape(format_id.lower())
        patterns = [
            rf"\.f{escaped}\.",
            rf"\.f{escaped}-",
            rf"\.f{escaped}_",
            rf"format[_-]?{escaped}\.",
            rf"(?<![a-z0-9]){escaped}(?:\.[a-z0-9]+)?\.part$",
        ]
        return any(re.search(pattern, lowered) for pattern in patterns)

    def _detect_stage_key(self, payload: dict[str, Any], filename: str = "", line: str = "") -> str | None:
        keep_video = bool(payload.get("keep_video"))
        keep_audio = bool(payload.get("keep_audio"))
        video_id = (payload.get("video_format_id") or "").strip()
        audio_id = (payload.get("audio_format_id") or "").strip()

        if "[Merger]" in line:
            return "merge"
        if not keep_video and keep_audio:
            return "audio"
        if keep_video and not keep_audio:
            return "video"
        if keep_video and keep_audio:
            if self._match_format_id(filename, video_id):
                return "video"
            if self._match_format_id(filename, audio_id):
                return "audio"
        return None

    def _stage_text(self, payload: dict[str, Any], stage_key: str) -> tuple[str, str]:
        keep_video = bool(payload.get("keep_video"))
        keep_audio = bool(payload.get("keep_audio"))
        if stage_key == "video":
            if keep_audio:
                return "下载视频中", "正在下载视频流…"
            return "下载视频中", "正在下载视频…"
        if stage_key == "audio":
            if keep_video:
                return "下载音频中", "正在下载音频流…"
            return "下载音频中", "正在下载音频…"
        if stage_key == "merge":
            return "合并中", "音视频已下载完成，正在合并…"
        return "处理中", "正在处理…"

    def _set_stage(self, job_id: str, payload: dict[str, Any], stage_key: str, *, force_log: bool = False) -> None:
        stage_text, log_text = self._stage_text(payload, stage_key)
        current = self.job_store.get(job_id) or {}
        previous = current.get("stage_text")
        if previous != stage_text:
            self.job_store.update(job_id, stage_text=stage_text)
            self.job_store.append_log(job_id, log_text)
        elif force_log:
            self.job_store.append_log(job_id, log_text)

    def _parse_progress(self, line: str) -> dict[str, Any] | None:
        parts = line.split("|", 8)
        if len(parts) < 9:
            return None
        downloaded_bytes = parse_float(parts[2]) or 0
        total_bytes = parse_float(parts[3])
        estimated_total = parse_float(parts[4])
        percent = parse_percent_text(parts[5])
        final_total = total_bytes or estimated_total
        if percent is None and final_total:
            percent = round(downloaded_bytes / final_total * 100, 2)
        return {
            "status": parts[1],
            "downloaded_bytes": int(downloaded_bytes),
            "downloaded_text": format_bytes(downloaded_bytes),
            "total_bytes": int(final_total) if final_total else None,
            "total_text": format_bytes(final_total),
            "progress_percent": max(0.0, min(percent or 0.0, 100.0)),
            "speed_text": parts[6] if parts[6] not in ("", "NA") else "-",
            "eta_text": parts[7] if parts[7] not in ("", "NA") else "-",
            "current_file": parts[8],
        }

    def _run_job(self, job_id: str, payload: dict[str, Any]) -> None:
        try:
            self.job_store.update(job_id, status="starting", stage_text="准备下载")
            self.job_store.append_log(job_id, "启动下载任务...")
            self.job_store.append_log(job_id, f"下载目录：{payload.get('output_dir') or str(self.config.downloads_dir)}")
            if payload.get("cookies_path"):
                self.job_store.append_log(job_id, "已附带 cookies.txt 登录信息。")
            elif (payload.get("cookie_source") or {}).get("mode") == "browser":
                browser_name = (payload.get("cookie_source") or {}).get("label") or (payload.get("cookie_source") or {}).get("value") or "浏览器"
                self.job_store.append_log(job_id, f"已自动使用 {browser_name} 浏览器登录信息。")
            target_format = (payload.get("merge_format") or "").strip().lower()
            video_source_ext = (payload.get("video_source_ext") or "").strip().lower()
            audio_source_ext = (payload.get("audio_source_ext") or "").strip().lower()
            if payload.get("keep_video") and payload.get("keep_audio"):
                self.job_store.append_log(job_id, "将依次下载视频和音频，完成后自动合并。")
                if target_format:
                    self.job_store.append_log(job_id, f"最终输出格式：{target_format.upper()}。")
            elif payload.get("keep_video"):
                self.job_store.append_log(job_id, "即将开始下载视频。")
                if target_format and target_format != video_source_ext:
                    self.job_store.append_log(job_id, f"下载完成后将转换为 {target_format.upper()}。")
            elif payload.get("keep_audio"):
                self.job_store.append_log(job_id, "即将开始下载音频。")
                if target_format and target_format != audio_source_ext:
                    self.job_store.append_log(job_id, f"下载完成后将转换为 {target_format.upper()}。")
            return_code = self._run_command(job_id, payload, self._build_command(payload))
            if self._should_retry_ssl_compat(job_id, return_code):
                current = self.job_store.get(job_id) or {}
                if current.get("status") != "cancelled":
                    self.job_store.update(job_id, status="starting", stage_text="网络重试中", speed_text="-", eta_text="-", error="")
                    self.job_store.append_log(job_id, "检测到下载连接被站点中断，正在切换兼容网络模式后重试一次…")
                    compat_args = [
                        "--compat-options",
                        "prefer-legacy-http-handler",
                        "--retries",
                        "20",
                        "--fragment-retries",
                        "20",
                        "--retry-sleep",
                        "http:exp=1:8",
                        "--retry-sleep",
                        "fragment:exp=1:8",
                    ]
                    return_code = self._run_command(job_id, payload, self._build_command(payload, compat_args))
            job = self.job_store.get(job_id) or {}
            status = job.get("status")
            if status == "cancelled":
                return
            if return_code == 0:
                self.job_store.update(
                    job_id,
                    status="completed",
                    stage_text="已完成",
                    progress_percent=100.0,
                    speed_text="-",
                    eta_text="-",
                    total_bytes=job.get("total_bytes") or job.get("downloaded_bytes"),
                    total_text=job.get("total_text") if job.get("total_bytes") else job.get("downloaded_text"),
                )
                self.job_store.append_log(job_id, "下载完成。")
            else:
                last_log = next((line for line in reversed(job.get("logs", [])) if line), "")
                self.job_store.update(job_id, status="error", error=last_log or f"yt-dlp 退出码 {return_code}")
                if "Sign in to confirm you" in (last_log or "") or "Use --cookies-from-browser or --cookies" in (last_log or ""):
                    self.job_store.append_log(job_id, "提示：该链接可能需要 cookies.txt 登录信息。")
        except Exception as exc:
            self.job_store.update(job_id, status="error", stage_text="失败", error=str(exc))
            self.job_store.append_log(job_id, f"错误：{exc}")
        finally:
            self._clear_process(job_id)
