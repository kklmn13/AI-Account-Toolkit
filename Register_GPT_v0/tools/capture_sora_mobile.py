#!/usr/bin/env python3
import json
from datetime import datetime
from pathlib import Path

from mitmproxy import ctx, http


DOMAINS = (
    "sora.chatgpt.com",
    "chatgpt.com",
    "auth.openai.com",
    "openai.com",
    "sentinel.openai.com",
    "videos.openai.com",
)

OUT_DIR = Path("/Users/mac/Desktop/Sora-Register-main/logs/mobile_capture")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _matches(host: str) -> bool:
    value = (host or "").strip().lower()
    return any(value == domain or value.endswith(f".{domain}") for domain in DOMAINS)


def _now() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def _save(kind: str, data: dict) -> None:
    path = OUT_DIR / f"{_now()}_{kind}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    ctx.log.info(f"[capture] wrote {path}")


def request(flow: http.HTTPFlow) -> None:
    if not _matches(flow.request.pretty_host):
        return
    payload = {
        "kind": "request",
        "host": flow.request.pretty_host,
        "method": flow.request.method,
        "url": flow.request.pretty_url,
        "headers": dict(flow.request.headers),
        "content_length": len(flow.request.raw_content or b""),
        "text_preview": (flow.request.get_text(strict=False) or "")[:8000],
    }
    _save("request", payload)


def response(flow: http.HTTPFlow) -> None:
    if not _matches(flow.request.pretty_host):
        return
    payload = {
        "kind": "response",
        "host": flow.request.pretty_host,
        "method": flow.request.method,
        "url": flow.request.pretty_url,
        "status_code": flow.response.status_code if flow.response else 0,
        "headers": dict(flow.response.headers) if flow.response else {},
        "content_length": len((flow.response.raw_content if flow.response else b"") or b""),
        "text_preview": ((flow.response.get_text(strict=False) if flow.response else "") or "")[:8000],
    }
    _save("response", payload)
