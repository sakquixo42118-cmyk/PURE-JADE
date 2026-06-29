"""Check PURE-JADE API configuration with a minimal non-project payload.

Default mode is dry-run: it loads .env, prints the effective configuration
summary, and writes the exact test messages without sending a network request.

Use --send only when you intentionally want to call the configured API.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import pure_jade_api as api_client


DEFAULT_ENV_FILE = Path(".env")
DEFAULT_REPORT = Path("reports/final/local/api_smoke_test_dry_run_report.json")
DEFAULT_SEND_REPORT = Path("reports/final/api/api_smoke_test_report.json")


def smoke_messages() -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": "You are a connectivity smoke test. Output only one JSON object.",
        },
        {
            "role": "user",
            "content": 'Return exactly this JSON meaning, with any concise wording: {"ok": true, "message": "pong"}',
        },
    ]


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true", help="Actually call the configured API.")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--api-url")
    parser.add_argument("--api-model")
    parser.add_argument("--api-temperature", type=float)
    parser.add_argument("--api-timeout", type=int)
    parser.add_argument("--api-max-retries", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config, config_errors = api_client.load_api_config(args)
    if config_errors:
        print("API configuration is incomplete:")
        for error in config_errors:
            print(f"  - {error}")
        print("Create .env from .env.example or pass --api-model / --api-url.")
        return 2

    assert config is not None
    messages = smoke_messages()
    report_path = args.report or (DEFAULT_SEND_REPORT if args.send else DEFAULT_REPORT)

    report: dict[str, Any] = {
        "status": "dry_run" if not args.send else "pending",
        "sent_network_request": False,
        "api": api_client.config_summary(config),
        "messages": messages,
    }

    if not args.send:
        write_json(report_path, report)
        print("status=dry_run")
        print(f"url={config.url}")
        print(f"model={config.model}")
        print(f"json_mode={config.json_mode}")
        print(f"report={report_path}")
        return 0

    started = time.time()
    try:
        raw_output, response_json = api_client.request_chat_completion(messages, config)
        parsed, parse_error = api_client.extract_json_object(raw_output)
    except Exception as error:  # noqa: BLE001 - keep CLI errors readable.
        report.update(
            {
                "status": "api_error",
                "sent_network_request": True,
                "error": str(error),
                "elapsed_seconds": round(time.time() - started, 3),
            }
        )
        write_json(report_path, report)
        print("status=api_error")
        print(f"error={error}")
        print(f"report={report_path}")
        return 1

    report.update(
        {
            "status": "pass" if parse_error is None else "parse_error",
            "sent_network_request": True,
            "raw_output": raw_output,
            "parsed_json": parsed,
            "parse_error": parse_error,
            "elapsed_seconds": round(time.time() - started, 3),
            "response_id": response_json.get("id") if isinstance(response_json, dict) else None,
        }
    )
    write_json(report_path, report)

    print(f"status={report['status']}")
    print(f"elapsed_seconds={report['elapsed_seconds']}")
    print(f"report={report_path}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
