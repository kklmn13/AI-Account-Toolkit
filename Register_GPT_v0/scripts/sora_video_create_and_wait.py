#!/usr/bin/env python3
import argparse
import json
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _post_json(url: str, body: dict[str, Any], api_key: str, timeout: int = 1800) -> tuple[int, dict[str, Any]]:
    payload = json.dumps(body).encode("utf-8")
    request = Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return response.status, json.loads(raw or "{}")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw or "{}")
        except Exception:
            payload = {"raw": raw}
        return exc.code, payload
    except URLError as exc:
        raise RuntimeError(f"请求失败: {exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a Sora video task and wait until succeeded or timeout.")
    parser.add_argument("--base-url", default="http://127.0.0.1:1989", help="Local backend base URL")
    parser.add_argument("--api-key", default="", help="Pool or account-bound srk_ API key")
    parser.add_argument("--account-id", type=int, default=0, help="Optional fixed account_id for admin-mode calls")
    parser.add_argument("--prompt", required=True, help="Video prompt")
    parser.add_argument("--n-variants", type=int, default=1, help="Number of variants")
    parser.add_argument("--n-frames", type=int, default=300, help="Frame count")
    parser.add_argument("--resolution", type=int, default=360, help="Base resolution")
    parser.add_argument("--orientation", choices=["wide", "tall", "square"], default="wide", help="Video orientation")
    parser.add_argument("--task-family", choices=["video_gen", "nf2"], default="", help="Optional generation chain override")
    parser.add_argument("--model", default="", help="Optional model override")
    parser.add_argument("--seed", type=int, default=None, help="Optional random seed")
    parser.add_argument("--poll-interval", type=float, default=5.0, help="Polling interval in seconds")
    parser.add_argument("--timeout", type=int, default=900, help="Polling timeout in seconds")
    parser.add_argument("--json", action="store_true", help="Print full JSON response")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    api_key = (args.api_key or "").strip()
    if not api_key:
        parser.error("--api-key 不能为空")

    body = {
        "prompt": args.prompt,
        "n_variants": max(1, int(args.n_variants or 1)),
        "n_frames": max(60, int(args.n_frames or 300)),
        "resolution": max(360, int(args.resolution or 360)),
        "orientation": args.orientation,
        "poll_interval_seconds": max(1.0, float(args.poll_interval or 5.0)),
        "timeout_seconds": max(5, int(args.timeout or 900)),
    }
    if (args.task_family or "").strip():
        body["task_family"] = args.task_family.strip()
    if args.account_id > 0:
        body["account_id"] = int(args.account_id)
    if (args.model or "").strip():
        body["model"] = args.model.strip()
    if args.seed is not None:
        body["seed"] = int(args.seed)

    url = args.base_url.rstrip("/") + "/api/sora-api/video-gen/create-and-wait"
    status_code, result = _post_json(url, body, api_key=api_key, timeout=max(30, int(args.timeout) + 60))

    if args.json:
        print(json.dumps({"http_status": status_code, "result": result}, ensure_ascii=False, indent=2))
    else:
        print(f"http_status: {status_code}")
        print(f"task_id: {result.get('task_id') or ''}")
        print(f"status: {result.get('normalized_status') or result.get('status') or ''}")
        print(f"used_account_id: {result.get('used_account_id') or ''}")
        print(f"used_email: {result.get('used_email') or ''}")
        print(f"poll_attempts: {result.get('poll_attempts') or 0}")
        print(f"elapsed_seconds: {result.get('elapsed_seconds') or 0}")
        print(f"timed_out: {bool(result.get('timed_out'))}")
        print(f"message: {result.get('message') or ''}")
        video_urls = result.get("video_urls") or []
        if video_urls:
            print("video_urls:")
            for item in video_urls:
                print(f"  - {item}")

    if status_code >= 400:
        return 1
    if result.get("ok") and result.get("is_success"):
        return 0
    if result.get("timed_out"):
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
