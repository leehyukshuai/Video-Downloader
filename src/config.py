from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AppConfig:
    root: Path
    host: str = "127.0.0.1"
    port: int = 8765
    js_runtime: str = ""

    @property
    def web_dir(self) -> Path:
        return self.root / "web"

    @property
    def downloads_dir(self) -> Path:
        return default_downloads_dir()

    @property
    def start_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def auto_cookie_browsers(self) -> list[str]:
        return detect_cookie_browsers()

    @property
    def auto_cookie_targets(self) -> list[dict[str, str]]:
        return detect_cookie_targets()

    @property
    def yt_dlp_runtime_args(self) -> list[str]:
        return ["--js-runtimes", self.js_runtime] if self.js_runtime else []

    @property
    def yt_dlp_command(self) -> list[str]:
        if importlib.util.find_spec("yt_dlp"):
            return [sys.executable, "-m", "src.yt_dlp_compat"]
        executable = shutil.which("yt-dlp")
        if executable:
            return [executable]
        raise FileNotFoundError("未找到 yt-dlp。请先在当前环境中安装 yt-dlp。")

    @property
    def ffmpeg_location(self) -> str:
        executable = shutil.which("ffmpeg")
        if executable:
            return str(Path(executable).resolve().parent)
        raise FileNotFoundError("未找到 ffmpeg。请先在当前环境中安装 ffmpeg。")

    def ensure_dirs(self) -> None:
        self.downloads_dir.mkdir(exist_ok=True)

    def resolve_output_dir(self, raw_path: str | None) -> Path:
        value = (raw_path or "").strip()
        if not value:
            target = self.downloads_dir
        else:
            path = Path(value)
            target = path if path.is_absolute() else (self.root / path)
        target = target.resolve()
        target.mkdir(parents=True, exist_ok=True)
        return target


def detect_js_runtime() -> str:
    explicit = os.environ.get("YT_DLP_JS_RUNTIME", "").strip()
    if explicit:
        return explicit
    for candidate in ("node", "deno", "bun"):
        if shutil.which(candidate):
            return candidate
    return ""


def detect_cookie_browsers() -> list[str]:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    roaming = Path(os.environ.get("APPDATA", ""))
    candidates = [
        ("edge", local / "Microsoft" / "Edge" / "User Data"),
        ("chrome", local / "Google" / "Chrome" / "User Data"),
        ("brave", local / "BraveSoftware" / "Brave-Browser" / "User Data"),
        ("chromium", local / "Chromium" / "User Data"),
        ("firefox", roaming / "Mozilla" / "Firefox" / "Profiles"),
    ]
    found: list[str] = []
    for name, path in candidates:
        if path.exists():
            found.append(name)
    return found


def _detect_chromium_profiles(base_dir: Path) -> list[str]:
    profiles: list[str] = []
    if not base_dir.exists():
        return profiles
    preferred = ["Default"]
    preferred.extend(sorted(path.name for path in base_dir.glob("Profile *") if path.is_dir()))
    seen: set[str] = set()
    for name in preferred:
        if name in seen:
            continue
        if (base_dir / name).exists():
            seen.add(name)
            profiles.append(name)
    return profiles


def detect_cookie_targets() -> list[dict[str, str]]:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    targets: list[dict[str, str]] = []
    browser_roots = [
        ("edge", "Edge", local / "Microsoft" / "Edge" / "User Data"),
        ("chrome", "Chrome", local / "Google" / "Chrome" / "User Data"),
        ("brave", "Brave", local / "BraveSoftware" / "Brave-Browser" / "User Data"),
        ("chromium", "Chromium", local / "Chromium" / "User Data"),
    ]

    for browser, label, root in browser_roots:
        if not root.exists():
            continue
        targets.append({"spec": browser, "label": label})
        for profile in _detect_chromium_profiles(root):
            targets.append({
                "spec": f"{browser}:{profile}",
                "label": f"{label} / {profile}",
            })
    return targets


def default_downloads_dir() -> Path:
    home = Path.home()
    windows_downloads = Path(os.environ.get("USERPROFILE", "")) / "Downloads"
    candidates = [windows_downloads, home / "Downloads"]
    for candidate in candidates:
        candidate = candidate.expanduser()
        if str(candidate).strip() and candidate.exists():
            return candidate
    return (home / "Downloads").expanduser()


def load_config() -> AppConfig:
    root = Path(__file__).resolve().parent.parent
    port = int(os.environ.get("YT_DLP_WEBUI_PORT", "8765"))
    config = AppConfig(root=root, port=port, js_runtime=detect_js_runtime())
    config.ensure_dirs()
    return config
