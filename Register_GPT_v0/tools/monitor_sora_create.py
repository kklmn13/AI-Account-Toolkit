#!/usr/bin/env python3
import argparse
import json
import sys
import time
from typing import Iterable

from playwright.sync_api import sync_playwright


WATCH_PATHS = (
    "/backend/video_gen",
    "/backend/nf/create",
    "/backend/nf/bulk_create",
)


def _matches(url: str, paths: Iterable[str]) -> bool:
    value = (url or "").strip()
    return any(path in value for path in paths)


def _print_json(prefix: str, payload) -> None:
    try:
        text = json.dumps(payload, ensure_ascii=False)
    except Exception:
        text = repr(payload)
    print(f"{prefix} {text}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor Sora create requests in a real Chrome via CDP.")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--open-explore", action="store_true")
    args = parser.parse_args()

    deadline = time.time() + max(1, int(args.timeout))
    hit = {"done": False}

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(args.cdp_url)
        contexts = browser.contexts
        if not contexts:
            print("No browser contexts available.", file=sys.stderr, flush=True)
            return 2
        context = contexts[0]

        def on_request(request):
            if not _matches(request.url, WATCH_PATHS):
                return
            payload = {
                "method": request.method,
                "url": request.url,
                "headers": {
                    k: v
                    for k, v in request.headers.items()
                    if k.lower() in {"content-type", "origin", "referer", "user-agent", "x-requested-with"}
                },
            }
            try:
                post_data = request.post_data
            except Exception:
                post_data = None
            if post_data:
                payload["post_data"] = post_data[:4000]
            _print_json("REQUEST", payload)

        def on_response(response):
            if not _matches(response.url, WATCH_PATHS):
                return
            payload = {
                "status": response.status,
                "url": response.url,
                "headers": {
                    k: v
                    for k, v in response.headers.items()
                    if k.lower() in {"content-type", "cf-ray", "server", "location"}
                },
            }
            try:
                text = response.text()
            except Exception as exc:
                text = f"<read failed: {exc}>"
            payload["body_preview"] = (text or "")[:4000]
            _print_json("RESPONSE", payload)
            hit["done"] = True

        for page in context.pages:
            page.on("request", on_request)
            page.on("response", on_response)
        context.on("page", lambda page: (page.on("request", on_request), page.on("response", on_response)))

        pages = context.pages
        page = pages[0] if pages else context.new_page()
        if args.open_explore:
            page.goto("https://sora.chatgpt.com/explore", wait_until="domcontentloaded", timeout=120000)
        print(
            json.dumps(
                {
                    "page_count": len(context.pages),
                    "active_url": page.url,
                    "active_title": page.title(),
                    "deadline_epoch": int(deadline),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

        while time.time() < deadline and not hit["done"]:
            page.wait_for_timeout(1000)

        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
