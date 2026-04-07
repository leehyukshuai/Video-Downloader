from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .config import AppConfig
from .utils import clean_lines, dynamic_range_rank, format_bytes, format_duration, summarize_codec

AUTH_ERROR_MARKERS = (
    "sign in to confirm you're not a bot",
    "use --cookies-from-browser or --cookies",
    "requested content is not available, sign in",
)


def is_video_only(fmt: dict[str, Any]) -> bool:
    return fmt.get("vcodec") not in (None, "none") and fmt.get("acodec") == "none"


def is_audio_only(fmt: dict[str, Any]) -> bool:
    return fmt.get("acodec") not in (None, "none") and fmt.get("vcodec") == "none"


def build_video_format(fmt: dict[str, Any]) -> dict[str, Any]:
    size = fmt.get("filesize") or fmt.get("filesize_approx")
    dynamic_range = fmt.get("dynamic_range") or ("HDR10" if "HDR" in (fmt.get("format_note") or "") else "SDR")
    return {
        "id": fmt.get("format_id"),
        "ext": fmt.get("ext"),
        "width": fmt.get("width"),
        "height": fmt.get("height"),
        "resolution": fmt.get("resolution")
        or (f"{fmt.get('width')}x{fmt.get('height')}" if fmt.get("width") and fmt.get("height") else "未知"),
        "fps": fmt.get("fps"),
        "dynamic_range": dynamic_range,
        "codec": summarize_codec(fmt.get("vcodec")),
        "filesize": size,
        "filesize_text": format_bytes(size),
        "bitrate_kbps": round(fmt.get("tbr") or 0),
        "note": fmt.get("format_note") or fmt.get("format") or "",
        "container_rank": 1 if fmt.get("ext") == "mp4" else 0,
    }


def build_audio_format(fmt: dict[str, Any]) -> dict[str, Any]:
    size = fmt.get("filesize") or fmt.get("filesize_approx")
    return {
        "id": fmt.get("format_id"),
        "ext": fmt.get("ext"),
        "codec": summarize_codec(fmt.get("acodec")),
        "abr": round(fmt.get("abr") or fmt.get("tbr") or 0),
        "channels": fmt.get("audio_channels"),
        "sample_rate": fmt.get("asr"),
        "filesize": size,
        "filesize_text": format_bytes(size),
        "note": fmt.get("format_note") or fmt.get("format") or "",
        "container_rank": 1 if fmt.get("ext") == "m4a" else 0,
    }


def sort_video_formats(formats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        formats,
        key=lambda item: (
            item.get("filesize") or 0,
            dynamic_range_rank(item.get("dynamic_range")),
            item.get("height") or 0,
            item.get("fps") or 0,
            item.get("container_rank") or 0,
            item.get("bitrate_kbps") or 0,
        ),
        reverse=True,
    )


def sort_audio_formats(formats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        formats,
        key=lambda item: (
            item.get("filesize") or 0,
            item.get("abr") or 0,
            item.get("channels") or 0,
            item.get("container_rank") or 0,
        ),
        reverse=True,
    )


def pick_first(formats: list[dict[str, Any]], predicate) -> dict[str, Any] | None:
    for item in formats:
        if predicate(item):
            return item
    return formats[0] if formats else None


def recommend_merge_format(video_format: dict[str, Any] | None, audio_format: dict[str, Any] | None) -> str:
    video_ext = (video_format or {}).get("ext")
    audio_ext = (audio_format or {}).get("ext")
    if video_ext in {"mp4", "m4v"} and audio_ext in {"m4a", "mp4", "m4b", "aac"}:
        return "mp4"
    if video_ext == "webm" and audio_ext in {"webm", "weba", "opus", "ogg"}:
        return "webm"
    if video_ext and audio_ext:
        return "mkv"
    return (audio_ext or video_ext or "").lower()


def build_presets(video_formats: list[dict[str, Any]], audio_formats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_video = video_formats[0] if video_formats else None
    best_audio = audio_formats[0] if audio_formats else None
    best_hdr = pick_first(video_formats, lambda item: "HDR" in (item.get("dynamic_range") or "").upper())
    best_mp4 = pick_first(video_formats, lambda item: item.get("ext") == "mp4")
    best_compact = pick_first(
        video_formats,
        lambda item: (item.get("height") or 0) <= 1080 and (item.get("fps") or 0) >= 30,
    )
    best_m4a = pick_first(audio_formats, lambda item: item.get("ext") == "m4a")
    presets = []
    if best_video:
        presets.append(
            {
                "id": "best",
                "label": "最佳画质",
                "description": f"优先使用最高规格视频 {best_video['resolution']} / {best_video.get('dynamic_range') or 'SDR'}",
                "video_format_id": best_video["id"],
                "audio_format_id": best_audio["id"] if best_audio else "",
                "audio_only": False,
                "merge_format": recommend_merge_format(best_video, best_audio),
            }
        )
    if best_hdr:
        presets.append(
            {
                "id": "hdr",
                "label": "最佳 HDR",
                "description": f"优先选择 HDR 视频 {best_hdr['resolution']} / {best_hdr.get('ext')}",
                "video_format_id": best_hdr["id"],
                "audio_format_id": best_audio["id"] if best_audio else "",
                "audio_only": False,
                "merge_format": "mkv",
            }
        )
    if best_mp4:
        presets.append(
            {
                "id": "compatibility",
                "label": "兼容优先",
                "description": "优先 MP4 / M4A，适合本地播放器与分享",
                "video_format_id": best_mp4["id"],
                "audio_format_id": (best_m4a or best_audio or {}).get("id", ""),
                "audio_only": False,
                "merge_format": "mp4",
            }
        )
    if best_compact:
        presets.append(
            {
                "id": "compact",
                "label": "清晰且较省空间",
                "description": "优先 1080p 或以下，兼顾清晰度和体积",
                "video_format_id": best_compact["id"],
                "audio_format_id": best_audio["id"] if best_audio else "",
                "audio_only": False,
                "merge_format": recommend_merge_format(best_compact, best_audio),
            }
        )
    if best_audio:
        presets.append(
            {
                "id": "audio",
                "label": "仅音频",
                "description": f"只下载最佳音频 {best_audio['ext']} / {best_audio.get('abr') or '-'} kbps",
                "video_format_id": "",
                "audio_format_id": best_audio["id"],
                "audio_only": True,
                "merge_format": recommend_merge_format(None, best_audio),
            }
        )
    return presets


def is_auth_error(message: str) -> bool:
    lowered = (message or "").lower()
    return any(marker in lowered for marker in AUTH_ERROR_MARKERS)


def run_yt_dlp_command(config: AppConfig, target_url: str, extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    cmd = [
        *config.yt_dlp_command,
        "--dump-single-json",
        "--no-playlist",
        "--ffmpeg-location",
        config.ffmpeg_location,
        *config.yt_dlp_runtime_args,
        *(extra_args or []),
        target_url,
    ]
    return subprocess.run(
        cmd,
        cwd=str(config.root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def parse_yt_dlp_json(result: subprocess.CompletedProcess) -> tuple[dict[str, Any], list[str]]:
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"yt-dlp 输出无法解析为 JSON: {exc}") from exc
    return data, clean_lines(result.stderr)


def run_yt_dlp_json(config: AppConfig, target_url: str, cookies_path: str = "") -> tuple[dict[str, Any], list[str], dict[str, str]]:
    cookie_value = (cookies_path or "").strip()
    if cookie_value:
        cookie_file = Path(cookie_value).expanduser().resolve()
        if not cookie_file.exists():
            raise ValueError("cookies.txt 文件不存在。")
        result = run_yt_dlp_command(config, target_url, ["--cookies", str(cookie_file)])
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "yt-dlp 解析失败"
            if is_auth_error(message):
                raise RuntimeError("已使用 cookies.txt，但该链接仍需要登录验证。请确认这个 cookies.txt 仍然有效。")
            raise RuntimeError(message)
        data, warnings = parse_yt_dlp_json(result)
        return data, warnings, {"mode": "file", "value": str(cookie_file)}

    result = run_yt_dlp_command(config, target_url)
    if result.returncode == 0:
        data, warnings = parse_yt_dlp_json(result)
        return data, warnings, {}

    message = result.stderr.strip() or result.stdout.strip() or "yt-dlp 解析失败"
    if not is_auth_error(message):
        raise RuntimeError(message)

    for target in config.auto_cookie_targets:
        spec = target.get("spec") or ""
        label = target.get("label") or spec
        if not spec:
            continue
        retried = run_yt_dlp_command(config, target_url, ["--cookies-from-browser", spec])
        if retried.returncode == 0:
            data, warnings = parse_yt_dlp_json(retried)
            warnings.append(f"已自动使用 {label} 的浏览器登录信息。")
            return data, warnings, {"mode": "browser", "value": spec, "label": label}

    raise RuntimeError("该链接需要登录验证。请选择 cookies.txt 后重试。")


def build_format_payload(config: AppConfig, target_url: str, cookies_path: str = "") -> dict[str, Any]:
    data, warnings, cookie_source = run_yt_dlp_json(config, target_url, cookies_path)
    raw_formats = data.get("formats") or []
    video_formats = sort_video_formats([build_video_format(fmt) for fmt in raw_formats if is_video_only(fmt)])
    audio_formats = sort_audio_formats([build_audio_format(fmt) for fmt in raw_formats if is_audio_only(fmt)])
    presets = build_presets(video_formats, audio_formats)
    stats = {
        "video_count": len(video_formats),
        "audio_count": len(audio_formats),
        "has_hdr": any("HDR" in (item.get("dynamic_range") or "").upper() for item in video_formats),
        "top_resolution": video_formats[0]["resolution"] if video_formats else "未知",
        "best_audio": audio_formats[0]["abr"] if audio_formats else None,
    }
    return {
        "url": target_url,
        "id": data.get("id"),
        "title": data.get("title"),
        "uploader": data.get("uploader") or data.get("channel"),
        "duration": data.get("duration"),
        "duration_text": format_duration(data.get("duration")),
        "thumbnail": data.get("thumbnail"),
        "description": data.get("description", "")[:800],
        "warnings": warnings,
        "video_formats": video_formats,
        "audio_formats": audio_formats,
        "cookie_source": cookie_source,
        "defaults": {
            "video_id": None,
            "audio_id": None,
            "merge_format": "",
        },
        "presets": presets,
        "stats": stats,
    }
