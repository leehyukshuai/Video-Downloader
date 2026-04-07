from __future__ import annotations

import sys
from urllib.parse import urlparse

import yt_dlp
from yt_dlp.extractor.bilibili import BilibiliBaseIE


_ORIGINAL_EXTRACT_FORMATS = BilibiliBaseIE.extract_formats


def _prefer_backup_url(url: str | None, backup_urls: list[str] | None) -> str | None:
    if not url:
        return url
    parsed = urlparse(url)
    if parsed.port != 8082:
        return url
    preferred: list[str] = []
    fallback: list[str] = []
    for candidate in backup_urls or []:
        if not candidate:
            continue
        candidate_parsed = urlparse(candidate)
        if candidate_parsed.port in (None, 443) and candidate_parsed.hostname and candidate_parsed.hostname.endswith(".bilivideo.com"):
            preferred.append(candidate)
        elif candidate_parsed.port in (None, 443):
            fallback.append(candidate)
    if preferred:
        return preferred[0]
    if fallback:
        return fallback[0]
    return url


def _patch_stream_item(item: dict | None) -> None:
    if not isinstance(item, dict):
        return
    backup_urls = item.get("backupUrl") or item.get("backup_url") or []
    chosen = _prefer_backup_url(item.get("baseUrl") or item.get("base_url") or item.get("url"), backup_urls)
    if not chosen:
        return
    item["baseUrl"] = chosen
    item["base_url"] = chosen
    item["url"] = chosen


def _patched_extract_formats(self, play_info):
    dash = (play_info or {}).get("dash") or {}
    for stream in dash.get("video") or []:
        _patch_stream_item(stream)
    for stream in dash.get("audio") or []:
        _patch_stream_item(stream)
    dolby_audio = (dash.get("dolby") or {}).get("audio") or []
    for stream in dolby_audio:
        _patch_stream_item(stream)
    flac_audio = (dash.get("flac") or {}).get("audio")
    _patch_stream_item(flac_audio)
    return _ORIGINAL_EXTRACT_FORMATS(self, play_info)


BilibiliBaseIE.extract_formats = _patched_extract_formats


def main() -> int:
    return yt_dlp.main()


if __name__ == "__main__":
    raise SystemExit(main())
