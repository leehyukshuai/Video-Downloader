from __future__ import annotations

from datetime import datetime
import re


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def format_bytes(size) -> str:
    if size in (None, "", "NA"):
        return "未知"
    try:
        value = float(size)
    except (TypeError, ValueError):
        return "未知"
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    idx = 0
    while value >= 1024 and idx < len(units) - 1:
        value /= 1024
        idx += 1
    return f"{int(value)} {units[idx]}" if idx == 0 else f"{value:.2f} {units[idx]}"


def format_duration(seconds) -> str:
    if not seconds:
        return "未知"
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def clean_lines(text: str | None) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def summarize_codec(codec: str | None) -> str:
    if not codec or codec == "none":
        return "-"
    return codec.split(".")[0]


def dynamic_range_rank(value: str | None) -> int:
    return 1 if "HDR" in (value or "").upper() else 0


def parse_float(value):
    if value in (None, "", "NA"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_percent_text(value: str | None):
    if not value:
        return None
    match = re.search(r"([\d.]+)", value)
    return float(match.group(1)) if match else None


def job_status_label(status: str) -> str:
    mapping = {
        "queued": "排队中",
        "starting": "准备中",
        "downloading": "下载中",
        "processing": "处理中",
        "merging": "合并中",
        "paused": "已暂停",
        "cancelled": "已终止",
        "completed": "已完成",
        "error": "失败",
    }
    return mapping.get(status, status or "未知")
