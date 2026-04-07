from __future__ import annotations

import json
import mimetypes
import signal
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from .config import AppConfig, load_config
from .downloader import DownloadManager
from .formats import build_format_payload
from .jobs import JobStore
from .utils import now_iso


class AppState:
    def __init__(self, config: AppConfig):
        self.config = config
        self.jobs = JobStore()
        self.jobs.clear()
        self.downloader = DownloadManager(config, self.jobs)
        self.stopping = False

    def health(self) -> dict:
        return {
            "ok": True,
            "time": now_iso(),
            "downloads_dir": str(self.config.downloads_dir),
            "host": self.config.host,
            "port": self.config.port,
            "js_runtime": self.config.js_runtime or "",
        }

    def app_state(self) -> dict:
        return {
            "app": {
                "name": "yt-dlp Web UI",
                "downloads_dir": str(self.config.downloads_dir),
                "version": "3.0",
            }
        }


class QuietThreadingHTTPServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionAbortedError, BrokenPipeError, ConnectionResetError, OSError)):
            return
        return super().handle_error(request, client_address)


def create_handler(app: AppState):
    class Handler(BaseHTTPRequestHandler):
        server_version = "yt-dlp-webui/3.0"

        def log_message(self, format_, *args):
            return

        def _send_json(self, data, status=HTTPStatus.OK):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json_body(self):
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                return json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                raise ValueError("请求体不是合法的 JSON。")

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/":
                return self._serve_static("index.html")
            if path.startswith("/static/"):
                return self._serve_static(path.replace("/static/", "", 1))
            if path == "/api/health":
                return self._send_json(app.health())
            if path == "/api/app-state":
                return self._send_json(app.app_state())
            if path == "/api/events":
                return self._serve_events()
            if path == "/api/thumbnail":
                target = (parse_qs(parsed.query).get("url") or [""])[0].strip()
                return self._serve_thumbnail(target)
            if path.startswith("/api/downloads/"):
                job_id = path.rsplit("/", 1)[-1]
                job = app.jobs.get(job_id)
                if not job:
                    return self._send_json({"error": "任务不存在。"}, HTTPStatus.NOT_FOUND)
                return self._send_json(job)
            return self._send_json({"error": "未找到资源。"}, HTTPStatus.NOT_FOUND)

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                payload = self._read_json_body()
                if path == "/api/formats":
                    target_url = (payload.get("url") or "").strip()
                    if not target_url:
                        raise ValueError("请先输入链接。")
                    return self._send_json(build_format_payload(app.config, target_url, (payload.get("cookies_path") or "").strip()))
                if path == "/api/downloads":
                    job_id = app.downloader.create_job(payload)
                    app.downloader.start(job_id, payload)
                    return self._send_json({"job_id": job_id}, HTTPStatus.CREATED)
                if path.startswith('/api/downloads/') and path.endswith('/action'):
                    parts = path.strip('/').split('/')
                    job_id = parts[2]
                    action = (payload.get('action') or '').strip().lower()
                    if action == 'pause':
                        app.downloader.pause(job_id)
                    elif action == 'resume':
                        app.downloader.resume(job_id)
                    elif action == 'cancel':
                        app.downloader.cancel(job_id)
                    else:
                        raise ValueError('不支持的操作。')
                    return self._send_json(app.jobs.get(job_id) or {"ok": True})
                if path == "/api/open-target":
                    target = (payload.get("path") or "").strip()
                    if not target:
                        raise ValueError("缺少路径。")
                    return self._send_json(open_target(target, app.config))
                if path == "/api/pick-folder":
                    current = (payload.get("current") or "").strip()
                    return self._send_json(pick_folder(current, app.config))
                if path == "/api/pick-cookie":
                    current = (payload.get("current") or "").strip()
                    return self._send_json(pick_cookie_file(current, app.config))
                return self._send_json({"error": "未找到资源。"}, HTTPStatus.NOT_FOUND)
            except ValueError as exc:
                return self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except RuntimeError as exc:
                return self._send_json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
            except Exception as exc:
                return self._send_json({"error": f"服务器错误：{exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

        def _serve_static(self, relative_name):
            safe_path = (app.config.web_dir / relative_name).resolve()
            web_root = app.config.web_dir.resolve()
            if web_root not in safe_path.parents and safe_path != web_root:
                return self._send_json({"error": "非法路径。"}, HTTPStatus.BAD_REQUEST)
            if not safe_path.exists() or not safe_path.is_file():
                return self._send_json({"error": "静态文件不存在。"}, HTTPStatus.NOT_FOUND)
            mime_type, _ = mimetypes.guess_type(str(safe_path))
            body = safe_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            if mime_type and (mime_type.startswith("text/") or mime_type in {"application/javascript", "application/json"}):
                mime_type = mime_type + "; charset=utf-8"
            self.send_header("Content-Type", mime_type or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_events(self):
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            last_status = None
            try:
                while True:
                    status = "stopping" if app.stopping else "running"
                    if status != last_status:
                        payload = json.dumps({"status": status, "time": now_iso()}, ensure_ascii=False)
                        self.wfile.write(f"event: status\ndata: {payload}\n\n".encode("utf-8"))
                        self.wfile.flush()
                        last_status = status
                    heartbeat = json.dumps({"time": now_iso()}, ensure_ascii=False)
                    self.wfile.write(f"event: heartbeat\ndata: {heartbeat}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    if app.stopping:
                        break
                    time.sleep(2)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                return

        def _serve_thumbnail(self, target_url: str):
            if not target_url:
                return self._send_json({"error": "缺少缩略图地址。"}, HTTPStatus.BAD_REQUEST)
            parsed = urlparse(target_url)
            if parsed.scheme not in {"http", "https"}:
                return self._send_json({"error": "缩略图地址不合法。"}, HTTPStatus.BAD_REQUEST)
            headers = {
                "User-Agent": "Mozilla/5.0",
            }
            host = (parsed.netloc or "").lower()
            if "hdslb.com" in host or "bilibili.com" in host:
                headers["Referer"] = "https://www.bilibili.com/"
            req = Request(target_url, headers=headers)
            try:
                with urlopen(req, timeout=20) as resp:
                    body = resp.read()
                    content_type = resp.headers.get("Content-Type") or "image/jpeg"
            except Exception as exc:
                return self._send_json({"error": f"缩略图加载失败：{exc}"}, HTTPStatus.BAD_GATEWAY)

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def open_target(target: str, config: AppConfig) -> dict:
    path = Path(target)
    if not path.is_absolute():
        path = (config.root / path).resolve()
    else:
        path = path.resolve()
    if not path.exists():
        raise ValueError("目标路径不存在。")
    subprocess.Popen(["explorer.exe", "/select,", str(path)])
    return {"ok": True, "path": str(path)}


def pick_folder(current: str, config: AppConfig) -> dict:
    initial = current or str(config.downloads_dir)
    initial_path = Path(initial)
    if not initial_path.is_absolute():
        initial_path = (config.root / initial_path).resolve()
    if not initial_path.exists():
        initial_path = config.downloads_dir

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(
            parent=root,
            initialdir=str(initial_path),
            title="选择下载文件夹",
            mustexist=False,
        )
    finally:
        root.destroy()
    if not selected:
        return {"path": current or str(config.downloads_dir), "cancelled": True}
    return {"path": str(Path(selected).resolve()), "cancelled": False}


def pick_cookie_file(current: str, config: AppConfig) -> dict:
    initial_path = Path(current).expanduser() if current else config.root
    if initial_path.is_file():
        initial_dir = initial_path.parent
    elif initial_path.exists():
        initial_dir = initial_path
    else:
        initial_dir = config.root

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askopenfilename(
            parent=root,
            initialdir=str(initial_dir),
            title="选择 cookies.txt 文件",
            filetypes=[("Cookies 文件", "*.txt"), ("所有文件", "*.*")],
        )
    finally:
        root.destroy()
    if not selected:
        return {"path": current or "", "cancelled": True}
    return {"path": str(Path(selected).resolve()), "cancelled": False}


def run_server(config: AppConfig) -> None:
    try:
        config.yt_dlp_command
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc
    try:
        config.ffmpeg_location
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc
    app = AppState(config)
    httpd = QuietThreadingHTTPServer((config.host, config.port), create_handler(app))
    print("yt-dlp Web UI 已启动", flush=True)
    print(f"请在浏览器打开：{config.start_url}", flush=True)
    print("按 Ctrl+C 退出。", flush=True)

    original_sigint = signal.getsignal(signal.SIGINT)
    original_sigterm = signal.getsignal(signal.SIGTERM)
    stopping = {"value": False}

    def handle_stop(signum, frame):
        if stopping["value"]:
            return
        stopping["value"] = True
        app.stopping = True
        print("\n正在停止服务...", flush=True)
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)
    try:
        httpd.serve_forever()
    finally:
        signal.signal(signal.SIGINT, original_sigint)
        signal.signal(signal.SIGTERM, original_sigterm)
        httpd.server_close()


def main() -> None:
    run_server(load_config())

