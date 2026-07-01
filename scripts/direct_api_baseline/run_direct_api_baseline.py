"""Run a Direct API baseline for PURE-JADE comparisons.

This runner deliberately skips the PURE-JADE state, strategy, behavior, and
evaluation chain. It sends the dialogue history plus the latest user message
directly to an OpenAI-compatible chat-completions API and stores the result in
files shaped closely enough for the existing frontend to display.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
V024_DIR = PROJECT_ROOT / "scripts" / "full_chain_v024"
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "reports" / "direct_api_baseline"

if str(V024_DIR) not in sys.path:
    sys.path.insert(0, str(V024_DIR))

import pure_jade_api  # noqa: E402


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def safe_path_component(value: str, fallback: str = "conversation") -> str:
    invalid_chars = set('<>:"/\\|?*')
    cleaned = "".join("_" if char in invalid_chars or ord(char) < 32 else char for char in str(value))
    cleaned = cleaned.strip(" .")
    return cleaned or fallback


def default_conversation_id() -> str:
    return "direct_baseline_" + time.strftime("%Y%m%d_%H%M%S")


def build_output_dir(args: argparse.Namespace, conversation_id: str) -> Path:
    run_id = safe_path_component(args.run_id, fallback="run") if args.run_id else "run_" + time.strftime("%Y%m%d_%H%M%S")
    return args.output_dir / "conversations" / safe_path_component(conversation_id) / run_id


def conversation_dir_from_output(output_dir: Path) -> Path:
    return output_dir.parent


def current_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def append_dialogue_entry(record: dict[str, Any], turn_id: int, speaker: str, content: str) -> None:
    content = content.strip()
    if not content:
        return
    record.setdefault("dialogue_log", [])
    key = (turn_id, speaker, content)
    for item in record["dialogue_log"]:
        if not isinstance(item, dict):
            continue
        if (item.get("turn_id"), item.get("speaker"), item.get("content")) == key:
            return
    record["dialogue_log"].append(
        {
            "turn_id": turn_id,
            "speaker": speaker,
            "content": content,
            "timestamp": current_timestamp(),
        }
    )


def complete_dialogue_log_from_turn_records(record: dict[str, Any]) -> dict[str, Any]:
    for item in record.get("turn_records", []):
        if not isinstance(item, dict):
            continue
        turn_id = item.get("turn_id")
        if not isinstance(turn_id, int):
            continue

        user_text = first_present_string(
            item.get("user_text"),
            item.get("state_update_request", {}).get("current_user_message")
            if isinstance(item.get("state_update_request"), dict)
            else None,
            item.get("behavior_response_request", {}).get("current_user_message")
            if isinstance(item.get("behavior_response_request"), dict)
            else None,
        )
        if user_text:
            append_dialogue_entry(record, turn_id, "user", user_text)

        behavior_card = item.get("behavior_response_card")
        assistant_text = None
        if isinstance(behavior_card, dict):
            assistant_text = first_present_string(behavior_card.get("text_response"), behavior_card.get("response_text"))
        assistant_text = assistant_text or first_present_string(item.get("direct_response_text"))
        if assistant_text:
            append_dialogue_entry(record, turn_id, "assistant", assistant_text)

    record["dialogue_log"] = sorted(
        [item for item in record.get("dialogue_log", []) if isinstance(item, dict)],
        key=lambda item: (item.get("turn_id", 0), 0 if item.get("speaker") == "user" else 1),
    )
    return record


def first_present_string(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def get_next_turn_id(record: dict[str, Any], requested_turn_id: int | None) -> int:
    if requested_turn_id is not None:
        return requested_turn_id
    current_turn_id = record.get("current_turn_id")
    if isinstance(current_turn_id, int):
        return current_turn_id + 1
    turn_ids = [
        item.get("turn_id")
        for item in record.get("dialogue_log", [])
        if isinstance(item, dict) and isinstance(item.get("turn_id"), int)
    ]
    return max(turn_ids, default=0) + 1


def get_record_turn_id(record: dict[str, Any], requested_turn_id: int | None) -> int:
    if requested_turn_id is not None:
        return requested_turn_id
    current_turn_id = record.get("current_turn_id")
    if isinstance(current_turn_id, int):
        return current_turn_id
    turn_ids = [
        item.get("turn_id")
        for item in record.get("turn_records", [])
        if isinstance(item, dict) and isinstance(item.get("turn_id"), int)
    ]
    return max(turn_ids, default=1)


def user_text_for_turn(record: dict[str, Any], turn_id: int) -> str | None:
    for item in record.get("turn_records", []):
        if not isinstance(item, dict) or item.get("turn_id") != turn_id:
            continue
        value = first_present_string(
            item.get("user_text"),
            item.get("state_update_request", {}).get("current_user_message")
            if isinstance(item.get("state_update_request"), dict)
            else None,
        )
        if value:
            return value
    for item in record.get("dialogue_log", []):
        if (
            isinstance(item, dict)
            and item.get("turn_id") == turn_id
            and item.get("speaker") == "user"
            and isinstance(item.get("content"), str)
        ):
            return item["content"].strip()
    return None


def history_before_turn(record: dict[str, Any], turn_id: int, max_recent_turns: int) -> list[dict[str, str]]:
    max_items = max(max_recent_turns, 1) * 2
    entries: list[dict[str, str]] = []
    for item in record.get("dialogue_log", []):
        if not isinstance(item, dict):
            continue
        item_turn = item.get("turn_id")
        speaker = item.get("speaker")
        content = item.get("content")
        if not (isinstance(item_turn, int) and item_turn < turn_id and isinstance(content, str) and content.strip()):
            continue
        if speaker == "user":
            entries.append({"role": "user", "content": content.strip()})
        elif speaker == "assistant":
            entries.append({"role": "assistant", "content": content.strip()})
    return entries[-max_items:]


def build_messages(
    baseline_mode: str,
    history: list[dict[str, str]],
    current_user_message: str,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if baseline_mode == "minimal-support":
        messages.append(
            {
                "role": "system",
                "content": (
                    "你是一个自然、真诚、谨慎的情绪支持助手。请根据对话历史直接回复用户。"
                    "先回应当前最迫切的感受或现实处境；必要时给一个低负担、可执行的下一步。"
                    "不要说教，不要编造学校、医疗、法律等具体政策或保证结果。"
                    "如果出现自伤、伤人或紧急危险信号，优先提供安全支持，并建议联系现实中的可信任人员或当地紧急服务。"
                ),
            }
        )
    messages.extend(history)
    messages.append({"role": "user", "content": current_user_message})
    return messages


def call_direct_api(messages: list[dict[str, str]], config: pure_jade_api.ApiConfig) -> tuple[str, dict[str, Any]]:
    original_json_mode = config.json_mode
    config.json_mode = False
    attempts: list[dict[str, Any]] = []
    started = time.time()
    last_error: str | None = None
    for attempt_index in range(config.max_retries + 1):
        try:
            raw_output, response_json = pure_jade_api.request_chat_completion(messages, config)
            attempts.append(
                {
                    "attempt": attempt_index + 1,
                    "status": "valid",
                    "raw_output": raw_output,
                }
            )
            api_report = {
                "status": "valid",
                "attempts": attempts,
                "model": config.model,
                "url": config.url,
                "json_mode": False,
                "json_mode_overridden_from_env": original_json_mode,
                "elapsed_seconds": round(time.time() - started, 3),
                "usage": response_json.get("usage") if isinstance(response_json, dict) else None,
            }
            return raw_output.strip(), api_report
        except Exception as error:  # noqa: BLE001 - report API provider errors.
            last_error = str(error)
            attempts.append({"attempt": attempt_index + 1, "status": "error", "error": last_error})
            if attempt_index >= config.max_retries:
                break
            time.sleep(min(2**attempt_index, 4))
    raise RuntimeError(f"Direct API baseline failed: {last_error}")


def find_or_create_turn_record(record: dict[str, Any], turn_id: int) -> dict[str, Any]:
    record.setdefault("turn_records", [])
    for item in record["turn_records"]:
        if isinstance(item, dict) and item.get("turn_id") == turn_id:
            return item
    item = {"turn_id": turn_id}
    record["turn_records"].append(item)
    record["turn_records"] = sorted(
        [entry for entry in record["turn_records"] if isinstance(entry, dict)],
        key=lambda entry: entry.get("turn_id", 0),
    )
    return item


def build_behavior_card(conversation_id: str, turn_id: int, text_response: str, baseline_mode: str) -> dict[str, Any]:
    return {
        "conversation_id": conversation_id,
        "turn_id": turn_id,
        "schema_version": "direct-baseline-v0.1",
        "baseline_mode": baseline_mode,
        "text_response": text_response,
        "tone_style": "direct",
        "strategy_realization": [],
        "follow_up_question_count": text_response.count("？") + text_response.count("?"),
        "facial_expression": "none",
        "action": "none",
        "safety_message_used": False,
        "uses_previous_context": False,
        "context_used": [],
    }


def write_behavior_report(
    output_dir: Path,
    conversation_id: str,
    turn_id: int,
    baseline_mode: str,
    messages: list[dict[str, str]],
    text_response: str,
    behavior_card: dict[str, Any],
    api_report: dict[str, Any],
) -> dict[str, Any]:
    report = {
        "status": "pass",
        "module_scope": "direct_api_baseline",
        "mode": baseline_mode,
        "input_contract": {
            "uses_dialogue": True,
            "uses_user_state_card": False,
            "uses_strategy_decision_card": False,
            "uses_behavior_schema_prompt": False,
        },
        "input": {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "baseline_mode": baseline_mode,
            "messages": messages,
        },
        "output": {
            "direct_response_text": text_response,
            "behavior_response_card": behavior_card,
        },
        "api": api_report,
        "validation": {"status": "pass", "errors": [], "warnings": []},
    }
    write_json(output_dir / "03_behavior_report.json", report)
    return report


def write_request_report(
    output_dir: Path,
    conversation_id: str,
    turn_id: int,
    baseline_mode: str,
    current_user_message: str,
    history: list[dict[str, str]],
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    report = {
        "status": "pass",
        "stage": "direct_api_baseline/request",
        "conversation_id": conversation_id,
        "turn_id": turn_id,
        "baseline_mode": baseline_mode,
        "current_user_message": current_user_message,
        "history_message_count": len(history),
        "messages": messages,
    }
    write_json(output_dir / "01_direct_request_report.json", report)
    return report


def update_latest_artifacts(output_dir: Path, working_record: Path, summary_path: Path) -> None:
    conversation_dir = conversation_dir_from_output(output_dir)
    latest_record = conversation_dir / "conversation_record_latest.json"
    latest_summary = conversation_dir / "latest_run_summary.json"
    shutil.copyfile(working_record, latest_record)
    latest_summary.write_text(
        json.dumps(
            {
                "latest_run_dir": str(output_dir),
                "latest_record": str(latest_record),
                "latest_summary": str(summary_path),
                "updated_at": current_timestamp(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_summary(
    output_dir: Path,
    working_record: Path,
    args: argparse.Namespace,
    conversation_id: str,
    turn_id: int,
    request_report: dict[str, Any],
    behavior_report: dict[str, Any],
) -> Path:
    summary = {
        "status": "pass",
        "chain": ["direct_api_baseline/run_direct_api_baseline.py"],
        "conversation_id": conversation_id,
        "turn_id": turn_id,
        "modes": {
            "baseline_mode": args.baseline_mode,
            "strategy_mode": "not_applicable",
            "behavior_mode": "direct_api",
            "evaluation_skipped": True,
            "eval_mode": None,
            "eval_stage": None,
            "eval_scope": None,
        },
        "paths": {
            "output_dir": str(output_dir),
            "conversation_dir": str(conversation_dir_from_output(output_dir)),
            "working_record": str(working_record),
            "direct_request_report": str(output_dir / "01_direct_request_report.json"),
            "direct_behavior_report": str(output_dir / "03_behavior_report.json"),
            "continue_record": str(args.continue_record) if args.continue_record else None,
            "source_record": str(args.record) if args.record else None,
        },
        "stages": {
            "first": {
                "status": "skipped",
                "reason": "Direct API baseline does not generate a PURE-JADE state card.",
            },
            "strategy": {
                "status": "skipped",
                "reason": "Direct API baseline does not generate a PURE-JADE strategy card.",
            },
            "behavior": {
                "status": "pass",
                "mode": args.baseline_mode,
                "turn_id": turn_id,
                "api": behavior_report.get("api", {}),
            },
            "evaluation": {
                "status": "skipped",
                "reason": "Direct API baseline keeps generation to one API call.",
            },
        },
        "request": {
            "baseline_mode": args.baseline_mode,
            "history_message_count": request_report.get("history_message_count"),
        },
    }
    path = output_dir / "full_chain_summary.json"
    write_json(path, summary)
    return path


def init_record(args: argparse.Namespace) -> tuple[dict[str, Any], str, int, str]:
    if args.record:
        record = complete_dialogue_log_from_turn_records(read_json(args.record))
        conversation_id = args.conversation_id or str(record.get("conversation_id") or default_conversation_id())
        turn_id = get_record_turn_id(record, args.turn_id)
        current_user_message = user_text_for_turn(record, turn_id)
        if not current_user_message:
            raise RuntimeError(f"record does not contain user text for turn_id={turn_id}")
        return record, conversation_id, turn_id, current_user_message

    if args.continue_record:
        record = complete_dialogue_log_from_turn_records(read_json(args.continue_record))
        conversation_id = args.conversation_id or str(record.get("conversation_id") or default_conversation_id())
        turn_id = get_next_turn_id(record, args.turn_id)
    else:
        conversation_id = args.conversation_id or default_conversation_id()
        turn_id = args.turn_id or 1
        record = {
            "report_type": "direct_api_baseline_conversation_record",
            "schema_version": "direct-baseline-v0.1",
            "conversation_id": conversation_id,
            "created_at": current_timestamp(),
            "dialogue_log": [],
            "turn_records": [],
        }
    if not args.message:
        raise RuntimeError("--message is required unless --record is provided")
    return record, conversation_id, turn_id, args.message.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--message", help="Current user message for direct baseline generation.")
    input_group.add_argument("--record", type=Path, help="Existing conversation_record; replies to the selected turn.")
    parser.add_argument("--continue-record", type=Path, help="Existing conversation_record to continue with --message.")
    parser.add_argument("--conversation-id")
    parser.add_argument("--turn-id", type=int)
    parser.add_argument("--run-id")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--max-recent-turns", type=int, default=6)
    parser.add_argument("--baseline-mode", choices=("raw", "minimal-support"), default="minimal-support")

    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--api-key", help="Temporarily override PURE_JADE_API_KEY without editing .env.")
    parser.add_argument("--api-url")
    parser.add_argument("--api-model")
    parser.add_argument("--api-temperature", type=float)
    parser.add_argument("--api-timeout", type=int)
    parser.add_argument("--api-max-retries", type=int)

    # Compatibility with the existing frontend command builder. These options
    # are accepted but intentionally ignored by the direct baseline.
    parser.add_argument("--strategy-mode", choices=("rules", "mock", "api"), default="api")
    parser.add_argument("--behavior-mode", choices=("dry-run", "mock", "api"), default="api")
    parser.add_argument("--skip-evaluation", action="store_true")
    parser.add_argument("--eval-mode", choices=("fast", "full"), default="fast")
    parser.add_argument(
        "--eval-stage",
        choices=("scenario_understanding", "empathetic_planning", "empathetic_actions", "multi_turn_state_update"),
        default="empathetic_actions",
    )
    parser.add_argument("--eval-scope", choices=("current-turn", "all-turns", "both"), default="current-turn")
    parser.add_argument("--references", type=Path)
    parser.add_argument("--no-references", action="store_true")
    parser.add_argument("--reference-id", action="append", dest="reference_ids")
    parser.add_argument("--dimensions", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.env_file = args.env_file.resolve()
    args.output_dir = args.output_dir.resolve()
    if args.record:
        args.record = args.record.resolve()
    if args.continue_record:
        args.continue_record = args.continue_record.resolve()
    if args.continue_record and not args.message:
        raise SystemExit("--continue-record must be used together with --message")
    if args.max_recent_turns < 1:
        raise SystemExit("--max-recent-turns must be at least 1")

    output_dir: Path | None = None
    try:
        record, conversation_id, turn_id, current_user_message = init_record(args)
        record["conversation_id"] = conversation_id
        record["report_type"] = "direct_api_baseline_conversation_record"
        record["schema_version"] = "direct-baseline-v0.1"

        output_dir = build_output_dir(args, conversation_id)
        output_dir.mkdir(parents=True, exist_ok=True)

        config, config_errors = pure_jade_api.load_api_config(args)
        if config_errors or config is None:
            raise RuntimeError("Direct API configuration errors: " + "; ".join(config_errors))

        history = history_before_turn(record, turn_id, args.max_recent_turns)
        messages = build_messages(args.baseline_mode, history, current_user_message)
        request_report = write_request_report(
            output_dir,
            conversation_id,
            turn_id,
            args.baseline_mode,
            current_user_message,
            history,
            messages,
        )

        text_response, api_report = call_direct_api(messages, config)
        behavior_card = build_behavior_card(conversation_id, turn_id, text_response, args.baseline_mode)
        behavior_report = write_behavior_report(
            output_dir,
            conversation_id,
            turn_id,
            args.baseline_mode,
            messages,
            text_response,
            behavior_card,
            api_report,
        )

        append_dialogue_entry(record, turn_id, "user", current_user_message)
        append_dialogue_entry(record, turn_id, "assistant", text_response)
        turn_record = find_or_create_turn_record(record, turn_id)
        turn_record["user_text"] = current_user_message
        turn_record["direct_api_request"] = request_report
        turn_record["direct_api_response"] = {
            "text_response": text_response,
            "api": api_report,
            "baseline_mode": args.baseline_mode,
        }
        turn_record["behavior_response_card"] = behavior_card
        record["current_turn_id"] = turn_id
        record["updated_at"] = current_timestamp()

        working_record = output_dir / "conversation_record_direct_baseline.json"
        write_json(working_record, record)
        summary_path = write_summary(
            output_dir,
            working_record,
            args,
            conversation_id,
            turn_id,
            request_report,
            behavior_report,
        )
        update_latest_artifacts(output_dir, working_record, summary_path)
    except Exception as error:  # noqa: BLE001 - CLI should surface provider and data errors.
        if output_dir is None:
            fallback_id = args.conversation_id or "failed_direct_baseline"
            output_dir = build_output_dir(args, fallback_id)
            output_dir.mkdir(parents=True, exist_ok=True)
        failure_path = output_dir / "full_chain_summary.json"
        write_json(
            failure_path,
            {
                "status": "fail",
                "error": str(error),
                "chain": ["direct_api_baseline/run_direct_api_baseline.py"],
                "modes": {"baseline_mode": args.baseline_mode},
                "output_dir": str(output_dir),
            },
        )
        print("status=fail")
        print(f"error={error}")
        print(f"summary={failure_path}")
        return 1

    print("status=pass")
    print(f"conversation_id={conversation_id} turn_id={turn_id}")
    print(f"record={working_record}")
    print(f"summary={summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
