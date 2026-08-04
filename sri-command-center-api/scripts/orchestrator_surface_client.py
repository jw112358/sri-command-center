"""Provider-neutral client for a trusted SRI agent surface.

This client never approves shipping. Jeff's dashboard action is the only
production/external-action approval path.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx


def _json_file(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _request(method: str, path: str, payload: dict | None = None):
    base_url = os.environ.get("SRI_COMMAND_CENTER_API_URL", "").rstrip("/")
    token = os.environ.get("ORCHESTRATOR_RUNNER_TOKEN", "")
    if not base_url or not token:
        raise SystemExit(
            "SRI_COMMAND_CENTER_API_URL and ORCHESTRATOR_RUNNER_TOKEN are required"
        )
    response = httpx.request(
        method,
        f"{base_url}{path}",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
        timeout=30,
    )
    if response.is_error:
        raise SystemExit(f"Command Center returned {response.status_code}: {response.text}")
    if response.status_code == 204:
        return None
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    claim = sub.add_parser("claim")
    claim.add_argument("--worker", required=True)
    claim.add_argument("--limit", type=int, default=1, choices=range(1, 5))

    heartbeat = sub.add_parser("heartbeat")
    heartbeat.add_argument("--worker", required=True)

    for name in ("review-ready", "complete", "blocked"):
        command = sub.add_parser(name)
        command.add_argument("--task", required=True)
        command.add_argument("--payload", required=True, help="Path to a JSON request body")

    summary = sub.add_parser("summary")
    summary.add_argument("--payload", required=True, help="Path to a JSON request body")

    args = parser.parse_args()
    if args.command == "claim":
        result = _request(
            "POST",
            "/api/tasks/claim",
            {"workerId": args.worker, "limit": args.limit},
        )
    elif args.command == "heartbeat":
        result = _request(
            "POST",
            "/api/tasks/heartbeat",
            {"workerId": args.worker},
        )
    elif args.command == "summary":
        result = _request("POST", "/api/session-briefs", _json_file(args.payload))
    else:
        result = _request(
            "POST",
            f"/api/tasks/{args.task}/{args.command}",
            _json_file(args.payload),
        )
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
