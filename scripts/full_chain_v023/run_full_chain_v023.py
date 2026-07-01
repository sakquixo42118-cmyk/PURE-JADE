"""Run the full PURE-JADE v0.2.3 chain.

Chain:
    full_chain_v023/first -> full_chain_v023/strategy/run_strategy_pipeline_v023.py
    -> full_chain_v023/behavior/behavior_generator_api_schema_aligned_v023.py
    -> full_chain_v023/forth/run_full_evaluation.py

This runner is an orchestration layer over copied stage code. It does not
modify the v0.2.1 runner or the original first/third/forth source files.
Reports are grouped by conversation:

    reports/full_chain_v023/conversations/<conversation_id>/<run_id>/
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any


V023_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
FIRST_V023_DIR = V023_DIR / "first"
STRATEGY_V023_DIR = V023_DIR / "strategy"
BEHAVIOR_V023_DIR = V023_DIR / "behavior"
FORTH_V023_DIR = V023_DIR / "forth"

DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"
DEFAULT_REFERENCES = PROJECT_ROOT / "examples" / "strategy-references-v0.1.json"
DEFAULT_DIMENSIONS = FORTH_V023_DIR / "evaluation_dimensions.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "reports" / "full_chain_v023"


def load_module(name: str, path: Path, prepend_paths: list[Path] | None = None) -> ModuleType:
    for item in reversed(prepend_paths or []):
        item_text = str(item)
        if item_text not in sys.path:
            sys.path.insert(0, item_text)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def strip_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = strip_env_value(value)


def apply_api_overrides(args: argparse.Namespace) -> None:
    if getattr(args, "api_key", None):
        os.environ["PURE_JADE_API_KEY"] = args.api_key
    if args.api_url:
        os.environ["PURE_JADE_API_URL"] = args.api_url
    if args.api_model:
        os.environ["PURE_JADE_API_MODEL"] = args.api_model
    if args.api_temperature is not None:
        os.environ["PURE_JADE_API_TEMPERATURE"] = str(args.api_temperature)
    if args.api_timeout is not None:
        os.environ["PURE_JADE_API_TIMEOUT_SECONDS"] = str(args.api_timeout)
    if args.api_max_retries is not None:
        os.environ["PURE_JADE_API_MAX_RETRIES"] = str(args.api_max_retries)


def safe_conversation_filename(conversation_id: str) -> str:
    return safe_path_component(conversation_id) + ".json"


def safe_path_component(value: str, fallback: str = "conversation") -> str:
    invalid_chars = set('<>:"/\\|?*')
    cleaned = "".join("_" if char in invalid_chars or ord(char) < 32 else char for char in str(value))
    cleaned = cleaned.strip(" .")
    return cleaned or fallback


def default_conversation_id() -> str:
    return "chain_v023_" + time.strftime("%Y%m%d_%H%M%S")


def stage_status(code: int) -> str:
    return "pass" if code == 0 else "fail"


def find_turn_record(record: dict[str, Any], turn_id: int) -> dict[str, Any]:
    for item in record.get("turn_records", []):
        if isinstance(item, dict) and item.get("turn_id") == turn_id:
            return item
    raise RuntimeError(f"turn_records does not contain turn_id={turn_id}")


def get_record_turn_id(record: dict[str, Any], requested_turn_id: int | None) -> int:
    if requested_turn_id is not None:
        return requested_turn_id
    current_turn_id = record.get("current_turn_id")
    return current_turn_id if isinstance(current_turn_id, int) else 1


def get_next_turn_id(record: dict[str, Any], requested_turn_id: int | None) -> int:
    if requested_turn_id is not None:
        return requested_turn_id
    current_turn_id = record.get("current_turn_id")
    return current_turn_id + 1 if isinstance(current_turn_id, int) else 1


def build_output_dir(args: argparse.Namespace, conversation_id: str) -> Path:
    root = args.output_dir or DEFAULT_OUTPUT_ROOT
    if args.run_id:
        run_id = safe_path_component(args.run_id, fallback="run")
    else:
        turn_label = args.turn_id if isinstance(args.turn_id, int) else "x"
        run_id = f"turn_{turn_label}_" + time.strftime("%Y%m%d_%H%M%S")
    return root / "conversations" / safe_path_component(conversation_id) / run_id


def conversation_dir_from_output(output_dir: Path) -> Path:
    return output_dir.parent


def append_dialogue_entry(record: dict[str, Any], turn_id: int, speaker: str, content: str) -> None:
    content = content.strip()
    if not content:
        return
    record.setdefault("dialogue_log", [])
    key = (turn_id, speaker, content)
    for item in record["dialogue_log"]:
        if not isinstance(item, dict):
            continue
        existing_key = (item.get("turn_id"), item.get("speaker"), item.get("content"))
        if existing_key == key:
            return
    record["dialogue_log"].append(
        {
            "turn_id": turn_id,
            "speaker": speaker,
            "content": content,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
    )


def complete_dialogue_log_from_turn_records(record: dict[str, Any]) -> dict[str, Any]:
    """Fill dialogue_log from turn_records when older runs only stored cards."""
    for item in record.get("turn_records", []):
        if not isinstance(item, dict):
            continue
        turn_id = item.get("turn_id")
        if not isinstance(turn_id, int):
            continue
        request = item.get("state_update_request")
        if isinstance(request, dict) and isinstance(request.get("current_user_message"), str):
            append_dialogue_entry(record, turn_id, "user", request["current_user_message"])
        behavior_card = item.get("behavior_response_card")
        if isinstance(behavior_card, dict) and isinstance(behavior_card.get("text_response"), str):
            append_dialogue_entry(record, turn_id, "assistant", behavior_card["text_response"])
    record["dialogue_log"] = sorted(
        [item for item in record.get("dialogue_log", []) if isinstance(item, dict)],
        key=lambda item: (item.get("turn_id", 0), 0 if item.get("speaker") == "user" else 1),
    )
    return record


def previous_state_snapshot_from_record(record: dict[str, Any]) -> dict[str, Any]:
    current_state = record.get("current_state") if isinstance(record.get("current_state"), dict) else {}
    state_card = current_state.get("user_state_card") if isinstance(current_state.get("user_state_card"), dict) else {}
    if not state_card:
        raise RuntimeError("continue-record does not contain current_state.user_state_card")
    return {
        "turn_id": state_card.get("turn_id", record.get("current_turn_id", 0)),
        "dialogue_summary": current_state.get("dialogue_summary", ""),
        "user_state_card": state_card,
        "risk_memory": current_state.get(
            "risk_memory",
            {"highest_risk_level": "low", "risk_signals_seen": [], "safety_followup_needed": False},
        ),
        "open_questions": current_state.get("open_questions", []),
    }


def recent_dialogue_window_from_record(record: dict[str, Any], next_turn_id: int, max_recent_turns: int) -> list[dict[str, Any]]:
    max_items = max(max_recent_turns, 1) * 2
    entries: list[dict[str, Any]] = []
    for item in record.get("dialogue_log", []):
        if not isinstance(item, dict):
            continue
        item_turn = item.get("turn_id")
        speaker = item.get("speaker")
        content = item.get("content")
        if (
            isinstance(item_turn, int)
            and item_turn < next_turn_id
            and isinstance(speaker, str)
            and isinstance(content, str)
            and content.strip()
        ):
            entries.append({"turn_id": item_turn, "speaker": speaker, "content": content})
    return entries[-max_items:]


def configure_first_stage_data_dir(output_dir: Path) -> Path:
    data_dir = output_dir / "_first_stage_conversations"
    data_dir.mkdir(parents=True, exist_ok=True)
    recorder_module = sys.modules.get("recorder")
    if recorder_module is not None and hasattr(recorder_module, "CONVERSATIONS_DIR"):
        recorder_module.CONVERSATIONS_DIR = str(data_dir)
    return data_dir


def run_first_stage(args: argparse.Namespace, output_dir: Path) -> tuple[Path, dict[str, Any]]:
    first_main = load_module(
        "pure_jade_first_v023_main",
        FIRST_V023_DIR / "main.py",
        prepend_paths=[FIRST_V023_DIR],
    )

    conversation_id = args.conversation_id
    if not conversation_id:
        raise RuntimeError("conversation_id was not initialized")
    turn_id = args.turn_id or 1
    first_data_dir = configure_first_stage_data_dir(output_dir)

    continue_record: dict[str, Any] | None = None
    if args.continue_record:
        continue_record = complete_dialogue_log_from_turn_records(read_json(args.continue_record))
        seeded_record = first_data_dir / safe_conversation_filename(conversation_id)
        write_json(seeded_record, continue_record)

    request_payload = {
        "conversation_id": conversation_id,
        "turn_id": turn_id,
        "current_user_message": args.message,
        "recent_dialogue_window": (
            recent_dialogue_window_from_record(continue_record, turn_id, args.max_recent_turns)
            if continue_record
            else []
        ),
    }
    if continue_record:
        request_payload["previous_state_snapshot"] = previous_state_snapshot_from_record(continue_record)

    if hasattr(first_main, "update_runtime_config"):
        updates: dict[str, Any] = {}
        if getattr(args, "api_key", None):
            updates["llm_api_key"] = args.api_key
        if args.api_url:
            updates["llm_base_url"] = args.api_url.rstrip("/").removesuffix("/chat/completions")
        if args.api_model:
            updates["llm_model"] = args.api_model
        if "PURE_JADE_API_JSON_MODE" in os.environ:
            updates["llm_use_json_mode"] = os.environ["PURE_JADE_API_JSON_MODE"].lower() not in {
                "0",
                "false",
                "no",
                "off",
            }
        if updates:
            first_main.update_runtime_config(**updates)

    request = first_main.StateCardRequest(**request_payload)
    started = time.time()
    response = asyncio.run(first_main.generate_state_card(request))
    elapsed = round(time.time() - started, 3)

    generated_record = first_data_dir / safe_conversation_filename(conversation_id)
    if not generated_record.exists():
        raise RuntimeError(f"first stage did not create conversation record: {generated_record}")

    first_report = {
        "status": "pass",
        "stage": "full_chain_v023/first",
        "elapsed_seconds": elapsed,
        "record_path": str(generated_record),
        "response": response.model_dump() if hasattr(response, "model_dump") else dict(response),
    }
    write_json(output_dir / "01_first_state_report.json", first_report)
    return generated_record, first_report


def prepare_working_record(source_record: Path, output_dir: Path) -> Path:
    working_record = output_dir / "conversation_record_v023_chain.json"
    working_record.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_record, working_record)
    return working_record


def run_strategy_stage(args: argparse.Namespace, working_record: Path, output_dir: Path, turn_id: int) -> dict[str, Any]:
    strategy_module = load_module(
        "pure_jade_strategy_v023",
        STRATEGY_V023_DIR / "run_strategy_pipeline_v023.py",
        prepend_paths=[STRATEGY_V023_DIR, V023_DIR],
    )
    api_client = load_module(
        "pure_jade_api_for_chain_v023",
        V023_DIR / "pure_jade_api.py",
        prepend_paths=[V023_DIR],
    )

    api_config = None
    if args.strategy_mode == "api":
        config_args = argparse.Namespace(
            env_file=args.env_file,
            api_key=getattr(args, "api_key", None),
            api_url=args.api_url,
            api_model=args.api_model,
            api_temperature=args.api_temperature,
            api_timeout=args.api_timeout,
            api_max_retries=args.api_max_retries,
        )
        api_config, config_errors = api_client.load_api_config(config_args)
        if config_errors:
            raise RuntimeError("strategy API configuration errors: " + "; ".join(config_errors))

    report_path = output_dir / "02_strategy_report.json"
    code = strategy_module.run_pipeline(
        record_path=working_record,
        references_path=args.references,
        report_path=report_path,
        turn_id=turn_id,
        mode=args.strategy_mode,
        use_references=not args.no_references,
        cli_reference_ids=args.reference_ids,
        api_config=api_config,
    )
    report = read_json(report_path)
    report["_runner_status"] = stage_status(code)
    if code != 0:
        raise RuntimeError(f"strategy stage failed; see {report_path}")

    strategy_request = report.get("input", {}).get("strategy_decision_request")
    strategy_card = report.get("output", {}).get("strategy_decision_card")
    if not isinstance(strategy_request, dict) or not isinstance(strategy_card, dict) or not strategy_card:
        raise RuntimeError("strategy report did not contain a strategy_decision_card")

    record = read_json(working_record)
    turn_record = find_turn_record(record, turn_id)
    turn_record["strategy_decision_request"] = strategy_request
    turn_record["strategy_decision_card"] = strategy_card
    write_json(working_record, record)
    return report


def run_behavior_stage(args: argparse.Namespace, working_record: Path, output_dir: Path, turn_id: int) -> dict[str, Any]:
    behavior_module = load_module(
        "pure_jade_behavior_schema_aligned_v023",
        BEHAVIOR_V023_DIR / "behavior_generator_api_schema_aligned_v023.py",
        prepend_paths=[BEHAVIOR_V023_DIR, V023_DIR],
    )
    report_path = output_dir / "03_behavior_report.json"
    behavior_args = argparse.Namespace(
        source="record",
        record=working_record,
        turn_id=turn_id,
        max_recent_turns=args.max_recent_turns,
        cases=PROJECT_ROOT / "examples" / "test-cases-v0.1.json",
        case_id=None,
        mode=args.behavior_mode,
        report=report_path,
        env_file=args.env_file,
        api_key=getattr(args, "api_key", None),
        api_url=args.api_url,
        api_model=args.api_model,
        api_temperature=args.api_temperature,
        api_timeout=args.api_timeout,
        api_max_retries=args.api_max_retries,
    )
    code = behavior_module.run(behavior_args)
    report = read_json(report_path)
    report["_runner_status"] = stage_status(code)
    if code != 0:
        raise RuntimeError(f"behavior stage failed; see {report_path}")

    behavior_card = report.get("output", {}).get("behavior_response_card")
    if args.behavior_mode == "dry-run":
        return report
    if not isinstance(behavior_card, dict) or not behavior_card:
        raise RuntimeError("behavior report did not contain a behavior_response_card")

    record = read_json(working_record)
    turn_record = find_turn_record(record, turn_id)
    turn_record["behavior_response_request"] = report.get("input", {}).get("behavior_response_request")
    turn_record["behavior_response_card"] = behavior_card
    text_response = behavior_card.get("text_response")
    if isinstance(text_response, str):
        append_dialogue_entry(record, turn_id, "assistant", text_response)
        record["dialogue_log"] = sorted(
            record.get("dialogue_log", []),
            key=lambda item: (item.get("turn_id", 0), 0 if item.get("speaker") == "user" else 1),
        )
    write_json(working_record, record)
    return report


def dialogue_for_evaluation(record: dict[str, Any], turn_id: int) -> list[dict[str, Any]]:
    dialogue: list[dict[str, Any]] = []
    for item in record.get("dialogue_log", []):
        if not isinstance(item, dict):
            continue
        item_turn = item.get("turn_id")
        if isinstance(item_turn, int) and item_turn <= turn_id:
            speaker = item.get("speaker")
            content = item.get("content")
            if isinstance(speaker, str) and isinstance(content, str) and content.strip():
                dialogue.append({"speaker": speaker, "content": content})
    return dialogue


EVALUATION_REQUIRED_CARDS = ["user_state_card", "strategy_decision_card", "behavior_response_card"]


def missing_evaluation_cards(turn_record: dict[str, Any]) -> list[str]:
    return [name for name in EVALUATION_REQUIRED_CARDS if not isinstance(turn_record.get(name), dict)]


def build_evaluation_case(record: dict[str, Any], turn_record: dict[str, Any], turn_id: int) -> dict[str, Any]:
    missing = missing_evaluation_cards(turn_record)
    if missing:
        raise RuntimeError("cannot build evaluation case; missing " + ", ".join(missing))
    return {
        "conversation_id": record.get("conversation_id"),
        "turn_id": turn_id,
        "schema_version": "0.2.1",
        "dialogue": dialogue_for_evaluation(record, turn_id),
        "user_state_card": turn_record["user_state_card"],
        "strategy_decision_card": turn_record["strategy_decision_card"],
        "behavior_response_card": turn_record["behavior_response_card"],
    }


def build_evaluation_cases(working_record: Path, output_dir: Path, turn_id: int) -> Path:
    record = read_json(working_record)
    turn_record = find_turn_record(record, turn_id)
    case = build_evaluation_case(record, turn_record, turn_id)
    cases_path = output_dir / "04_evaluation_cases.json"
    write_json(
        cases_path,
        {
            "schema_version": "0.2.1",
            "purpose": "full_chain_v023_current_turn_evaluation_input",
            "source_record": str(working_record),
            "eval_scope": "current_turn",
            "cases": [case],
        },
    )
    return cases_path


def build_all_turn_evaluation_cases(working_record: Path, output_dir: Path) -> Path:
    record = read_json(working_record)
    cases: list[dict[str, Any]] = []
    skipped_turns: list[dict[str, Any]] = []
    turn_records = record.get("turn_records", [])
    for item in sorted(turn_records, key=lambda value: value.get("turn_id", 0) if isinstance(value, dict) else 0):
        if not isinstance(item, dict):
            continue
        turn_id = item.get("turn_id")
        if not isinstance(turn_id, int):
            continue
        missing = missing_evaluation_cards(item)
        if missing:
            skipped_turns.append({"turn_id": turn_id, "missing_cards": missing})
            continue
        cases.append(build_evaluation_case(record, item, turn_id))
    if not cases:
        raise RuntimeError("cannot build all-turn evaluation cases; no completed turns with all required cards")

    cases_path = output_dir / "06_all_turn_evaluation_cases.json"
    write_json(
        cases_path,
        {
            "schema_version": "0.2.1",
            "purpose": "full_chain_v023_all_turns_evaluation_input",
            "source_record": str(working_record),
            "eval_scope": "all_turns",
            "skipped_turns": skipped_turns,
            "cases": cases,
        },
    )
    return cases_path


def run_evaluation_stage(
    args: argparse.Namespace,
    cases_path: Path,
    output_dir: Path,
    report_name: str = "05_evaluation_report.json",
    eval_scope: str = "current_turn",
) -> dict[str, Any]:
    report_path = output_dir / report_name
    command = [
        sys.executable,
        str(FORTH_V023_DIR / "run_full_evaluation.py"),
        "--cases",
        str(cases_path),
        "--dimensions",
        str(args.dimensions),
        "--eval-stage",
        args.eval_stage,
        "--eval-mode",
        args.eval_mode,
        "--env-file",
        str(args.env_file),
        "--output",
        str(report_path),
    ]
    if args.api_url:
        command.extend(["--api-url", args.api_url])
    if args.api_model:
        command.extend(["--api-model", args.api_model])
    if args.api_temperature is not None:
        command.extend(["--api-temperature", str(args.api_temperature)])
    if args.api_timeout is not None:
        command.extend(["--api-timeout", str(args.api_timeout)])
    if args.api_max_retries is not None:
        command.extend(["--api-max-retries", str(args.api_max_retries)])

    started = time.time()
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    elapsed = round(time.time() - started, 3)
    if result.returncode != 0:
        raise RuntimeError(
            "evaluation stage failed\n"
            + result.stdout
            + ("\n" + result.stderr if result.stderr else "")
        )
    report = read_json(report_path)
    report["_runner_status"] = "pass"
    report["_runner_elapsed_seconds"] = elapsed
    report["_runner_eval_scope"] = eval_scope
    report["_runner_stdout"] = result.stdout
    if result.stderr:
        report["_runner_stderr"] = result.stderr
    write_json(report_path, report)
    print(result.stdout.rstrip())
    return report


def score_value(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def evaluation_cards_by_turn(report: dict[str, Any] | None) -> dict[int, dict[str, Any]]:
    if not isinstance(report, dict):
        return {}
    cards = report.get("evaluation_cards")
    if not isinstance(cards, list):
        return {}
    result: dict[int, dict[str, Any]] = {}
    for card in cards:
        if isinstance(card, dict) and isinstance(card.get("turn_id"), int):
            result[card["turn_id"]] = card
    return result


def summarize_scores(cards: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [score for score in (score_value(card.get("overall_score")) for card in cards) if score is not None]
    if not scores:
        return {"count": 0, "mean_overall_score": None, "min_overall_score": None, "max_overall_score": None}
    return {
        "count": len(scores),
        "mean_overall_score": round(sum(scores) / len(scores), 3),
        "min_overall_score": min(scores),
        "max_overall_score": max(scores),
    }


def sorted_turn_records(record: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in sorted(
            record.get("turn_records", []),
            key=lambda value: value.get("turn_id", 0) if isinstance(value, dict) else 0,
        )
        if isinstance(item, dict)
    ]


def first_present_string(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def extract_strategy_name(strategy_card: dict[str, Any]) -> str | None:
    if strategy_card.get("safety_override") is True or strategy_card.get("support_intention") == "safety_support":
        return "Safety Guidance"
    return first_present_string(
        strategy_card.get("strategy"),
        strategy_card.get("strategy_name"),
        strategy_card.get("primary_strategy"),
        strategy_card.get("selected_strategy"),
    )


def write_conversation_summary_report(
    working_record: Path,
    output_dir: Path,
    current_eval_report: dict[str, Any] | None,
    all_turn_eval_report: dict[str, Any] | None,
) -> Path:
    record = complete_dialogue_log_from_turn_records(read_json(working_record))
    all_turn_eval_cards = evaluation_cards_by_turn(all_turn_eval_report)
    current_eval_cards = evaluation_cards_by_turn(current_eval_report)
    turn_summaries: list[dict[str, Any]] = []
    strategy_counts: dict[str, int] = {}
    missing_turns: list[dict[str, Any]] = []
    risk_levels: list[str] = []
    support_stages: list[str] = []

    for item in sorted_turn_records(record):
        turn_id = item.get("turn_id")
        if not isinstance(turn_id, int):
            continue
        state_card = item.get("user_state_card") if isinstance(item.get("user_state_card"), dict) else {}
        strategy_card = item.get("strategy_decision_card") if isinstance(item.get("strategy_decision_card"), dict) else {}
        behavior_card = item.get("behavior_response_card") if isinstance(item.get("behavior_response_card"), dict) else {}
        missing = missing_evaluation_cards(item)
        if missing:
            missing_turns.append({"turn_id": turn_id, "missing_cards": missing})

        risk_level = first_present_string(state_card.get("risk_level"))
        support_stage = first_present_string(state_card.get("support_stage"))
        strategy_name = extract_strategy_name(strategy_card) or "unknown"
        if strategy_name != "unknown":
            strategy_counts[strategy_name] = strategy_counts.get(strategy_name, 0) + 1
        if risk_level:
            risk_levels.append(risk_level)
        if support_stage:
            support_stages.append(support_stage)

        eval_card = all_turn_eval_cards.get(turn_id) or current_eval_cards.get(turn_id)
        violations = eval_card.get("violations") if isinstance(eval_card, dict) else None
        turn_summaries.append(
            {
                "turn_id": turn_id,
                "risk_level": risk_level,
                "support_stage": support_stage,
                "strategy": strategy_name,
                "assistant_text": behavior_card.get("text_response") if isinstance(behavior_card, dict) else None,
                "overall_score": eval_card.get("overall_score") if isinstance(eval_card, dict) else None,
                "review_needed": eval_card.get("review_needed") if isinstance(eval_card, dict) else None,
                "violations_count": len(violations) if isinstance(violations, list) else None,
                "missing_cards": missing,
            }
        )

    evaluated_cards = list(all_turn_eval_cards.values()) or list(current_eval_cards.values())
    low_score_turns = [
        {"turn_id": card.get("turn_id"), "overall_score": card.get("overall_score")}
        for card in evaluated_cards
        if (score_value(card.get("overall_score")) is not None and score_value(card.get("overall_score")) < 4)
    ]
    review_needed_turns = [
        {"turn_id": card.get("turn_id"), "review_notes": card.get("review_notes")}
        for card in evaluated_cards
        if card.get("review_needed")
    ]
    safety_turns = [item["turn_id"] for item in turn_summaries if item.get("risk_level") in {"medium", "high"}]

    summary = {
        "report_type": "pure_jade_v023_conversation_summary",
        "schema_version": "0.2.1",
        "conversation_id": record.get("conversation_id"),
        "current_turn_id": record.get("current_turn_id"),
        "dialogue_entry_count": len(record.get("dialogue_log", [])) if isinstance(record.get("dialogue_log"), list) else 0,
        "completed_turn_count": len([item for item in turn_summaries if not item.get("missing_cards")]),
        "risk_trajectory": risk_levels,
        "support_stage_trajectory": support_stages,
        "strategy_counts": strategy_counts,
        "score_summary": summarize_scores(evaluated_cards),
        "safety_turns": safety_turns,
        "review_needed_turns": review_needed_turns,
        "low_score_turns": low_score_turns,
        "missing_turns": missing_turns,
        "turn_summaries": turn_summaries,
        "runner_assessment": {
            "overall": "ready_for_manual_review" if review_needed_turns or missing_turns or low_score_turns else "no_blocking_issue_detected",
            "notes": [
                "This summary is deterministic and uses existing cards/evaluation reports only.",
                "Use 05_evaluation_report.json for current-turn card evaluation and 07_all_turn_evaluation_report.json for all-turn card evaluation.",
            ],
        },
    }
    report_path = output_dir / "08_conversation_summary_report.json"
    write_json(report_path, summary)
    write_json(working_record, record)
    return report_path


def score_label(score_summary: dict[str, Any]) -> str:
    mean_score = score_summary.get("mean_overall_score")
    if mean_score is None:
        return "not_evaluated"
    try:
        value = float(mean_score)
    except (TypeError, ValueError):
        return "unknown"
    if value >= 4.5:
        return "strong"
    if value >= 4:
        return "acceptable"
    if value >= 3:
        return "needs_review"
    return "weak"


def write_dialogue_review_report(
    working_record: Path,
    output_dir: Path,
    conversation_summary_path: Path,
    current_eval_report: dict[str, Any] | None,
    all_turn_eval_report: dict[str, Any] | None,
) -> Path:
    """Write a local full-dialogue review without making extra API calls."""
    record = complete_dialogue_log_from_turn_records(read_json(working_record))
    conversation_summary = read_json(conversation_summary_path)
    evaluated_cards = list(evaluation_cards_by_turn(all_turn_eval_report).values()) or list(
        evaluation_cards_by_turn(current_eval_report).values()
    )

    turn_records = sorted_turn_records(record)
    completed_turns = [
        item
        for item in turn_records
        if isinstance(item.get("turn_id"), int) and not missing_evaluation_cards(item)
    ]
    strategy_counts = conversation_summary.get("strategy_counts", {})
    score_summary = conversation_summary.get("score_summary", {})
    risk_trajectory = conversation_summary.get("risk_trajectory", [])
    support_stage_trajectory = conversation_summary.get("support_stage_trajectory", [])
    review_needed_turns = conversation_summary.get("review_needed_turns", [])
    low_score_turns = conversation_summary.get("low_score_turns", [])
    missing_turns = conversation_summary.get("missing_turns", [])

    strengths: list[str] = []
    risks_or_gaps: list[str] = []
    manual_review_focus: list[str] = []

    if completed_turns:
        strengths.append(f"已形成 {len(completed_turns)} 轮包含状态卡、策略卡和行为卡的完整记录。")
    if isinstance(strategy_counts, dict) and len(strategy_counts) >= 2:
        strengths.append(f"策略选择具有一定变化，已覆盖 {len(strategy_counts)} 类主要策略。")
    if isinstance(score_summary, dict) and score_label(score_summary) in {"strong", "acceptable"}:
        strengths.append(f"卡片评估均分处于可接受区间：{score_summary.get('mean_overall_score')}。")
    if isinstance(risk_trajectory, list) and risk_trajectory:
        strengths.append("每轮状态卡均保留了风险等级轨迹，便于后续复核。")

    if missing_turns:
        risks_or_gaps.append("部分轮次缺少完整卡片，不能进入严格卡片评估。")
        manual_review_focus.append("先检查 missing_turns 中对应轮次的状态卡、策略卡或行为卡是否生成失败。")
    if low_score_turns:
        risks_or_gaps.append("存在低分轮次，需要人工检查回复是否偏离用户需求或策略约束。")
        manual_review_focus.append("逐条查看 low_score_turns 对应的行为回应卡和评估理由。")
    if review_needed_turns:
        risks_or_gaps.append("评估卡标记了需要人工复核的轮次。")
        manual_review_focus.append("优先复核 review_needed_turns，确认是否有安全、说教或策略不一致问题。")
    if isinstance(strategy_counts, dict) and len(strategy_counts) <= 1 and len(completed_turns) >= 3:
        risks_or_gaps.append("多轮中策略变化较少，可能没有充分利用对话进展。")
        manual_review_focus.append("检查第二部分是否根据 support_stage 和用户新信息调整策略。")
    if "high" in risk_trajectory:
        risks_or_gaps.append("对话中出现 high 风险标记，应检查安全覆盖流程是否触发。")
        manual_review_focus.append("核对 high 风险轮次是否设置 safety_override，并避免危险细节、诊断和承诺。")
    if not evaluated_cards:
        risks_or_gaps.append("本次未产生第四部分卡片评估结果。")
        manual_review_focus.append("如果这是最终展示结果，建议至少对最后一轮运行卡片评估。")

    if not strengths:
        strengths.append("本报告已整理对话记录、卡片轨迹和 runner 输出，可作为人工复核入口。")
    if not risks_or_gaps:
        risks_or_gaps.append("未从结构化报告中发现阻塞性问题，仍建议人工抽查语气、连贯性和安全边界。")
    if not manual_review_focus:
        manual_review_focus.append("人工复核时重点看用户情绪是否被承接、策略是否落地、回复是否自然且不过度承诺。")

    review = {
        "report_type": "pure_jade_v023_dialogue_review",
        "schema_version": "0.2.1",
        "review_type": "local_full_dialogue_review",
        "extra_api_calls": 0,
        "source_note": "This report is generated by the runner from local cards, dialogue_log, and evaluation reports. It does not modify forth or call an extra evaluator.",
        "conversation_id": record.get("conversation_id"),
        "current_turn_id": record.get("current_turn_id"),
        "turn_count": len(turn_records),
        "completed_turn_count": len(completed_turns),
        "dialogue_entry_count": len(record.get("dialogue_log", [])) if isinstance(record.get("dialogue_log"), list) else 0,
        "evaluation_extensions": {
            "current_turn_card_evaluation": "05_evaluation_report.json" if current_eval_report else None,
            "all_turn_card_evaluation": "07_all_turn_evaluation_report.json" if all_turn_eval_report else None,
            "full_dialogue_review": "09_dialogue_review_report.json",
        },
        "trajectory": {
            "risk_levels": risk_trajectory,
            "support_stages": support_stage_trajectory,
            "strategy_counts": strategy_counts,
            "score_summary": score_summary,
            "score_label": score_label(score_summary if isinstance(score_summary, dict) else {}),
        },
        "review": {
            "strengths": strengths,
            "risks_or_gaps": risks_or_gaps,
            "manual_review_focus": manual_review_focus,
        },
    }
    report_path = output_dir / "09_dialogue_review_report.json"
    write_json(report_path, review)
    return report_path


def update_conversation_latest_artifacts(output_dir: Path, working_record: Path, summary_path: Path) -> None:
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
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
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
    stages: dict[str, dict[str, Any]],
    evaluation_cases: Path | None,
    all_turn_evaluation_cases: Path | None,
    conversation_summary_path: Path | None,
    dialogue_review_path: Path | None,
) -> Path:
    summary = {
        "status": "pass",
        "chain": [
            "full_chain_v023/first",
            "full_chain_v023/strategy/run_strategy_pipeline_v023.py",
            "full_chain_v023/behavior/behavior_generator_api_schema_aligned_v023.py",
            "full_chain_v023/forth/run_full_evaluation.py",
        ],
        "modes": {
            "strategy_mode": args.strategy_mode,
            "behavior_mode": args.behavior_mode,
            "evaluation_skipped": args.skip_evaluation,
            "eval_mode": None if args.skip_evaluation else args.eval_mode,
            "eval_stage": None if args.skip_evaluation else args.eval_stage,
            "eval_scope": None if args.skip_evaluation else args.eval_scope,
        },
        "paths": {
            "output_dir": str(output_dir),
            "conversation_dir": str(conversation_dir_from_output(output_dir)),
            "working_record": str(working_record),
            "evaluation_cases": str(evaluation_cases) if evaluation_cases else None,
            "current_turn_evaluation_report": str(output_dir / "05_evaluation_report.json")
            if evaluation_cases
            else None,
            "all_turn_evaluation_cases": str(all_turn_evaluation_cases) if all_turn_evaluation_cases else None,
            "all_turn_evaluation_report": str(output_dir / "07_all_turn_evaluation_report.json")
            if all_turn_evaluation_cases
            else None,
            "conversation_summary_report": str(conversation_summary_path) if conversation_summary_path else None,
            "dialogue_review_report": str(dialogue_review_path) if dialogue_review_path else None,
            "continue_record": str(args.continue_record) if args.continue_record else None,
        },
        "stages": stages,
    }
    path = output_dir / "full_chain_summary.json"
    write_json(path, summary)
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--message", help="Current user message for first-stage state-card generation.")
    input_group.add_argument("--record", type=Path, help="Existing v0.2.1 conversation_record; skips first stage.")
    parser.add_argument(
        "--continue-record",
        type=Path,
        help="Existing conversation_record to continue with --message. The next turn is appended before strategy/behavior.",
    )
    parser.add_argument("--conversation-id", help="Conversation id for --message mode. Defaults to a timestamp id.")
    parser.add_argument("--turn-id", type=int, help="Target turn id. Defaults to 1 for --message or current_turn_id for --record.")
    parser.add_argument("--run-id", help="Output folder name under --output-dir.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_ROOT)

    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--api-key", help="Temporarily override PURE_JADE_API_KEY without editing .env.")
    parser.add_argument("--api-url")
    parser.add_argument("--api-model")
    parser.add_argument("--api-temperature", type=float)
    parser.add_argument("--api-timeout", type=int)
    parser.add_argument("--api-max-retries", type=int)

    parser.add_argument("--references", type=Path, default=DEFAULT_REFERENCES)
    parser.add_argument("--strategy-mode", choices=("rules", "mock", "api"), default="api")
    parser.add_argument("--no-references", action="store_true")
    parser.add_argument("--reference-id", action="append", dest="reference_ids")

    parser.add_argument("--behavior-mode", choices=("dry-run", "mock", "api"), default="api")
    parser.add_argument("--max-recent-turns", type=int, default=3)

    parser.add_argument("--skip-evaluation", action="store_true")
    parser.add_argument(
        "--dimensions",
        type=Path,
        default=DEFAULT_DIMENSIONS,
        help="Pass-through dimensions file for full_chain_v023/forth/run_full_evaluation.py.",
    )
    parser.add_argument(
        "--eval-mode",
        choices=("fast", "full"),
        default="fast",
        help="fast calls the v0.2.2 diagnostic evaluator once per case; full uses the old per-dimension judge.",
    )
    parser.add_argument(
        "--eval-stage",
        choices=("scenario_understanding", "empathetic_planning", "empathetic_actions", "multi_turn_state_update"),
        default="empathetic_actions",
    )
    parser.add_argument(
        "--eval-scope",
        choices=("current-turn", "all-turns", "both"),
        default="current-turn",
        help="Evaluate only the target turn, all completed turns, or both. --skip-evaluation disables both.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.env_file = args.env_file.resolve()
    args.references = args.references.resolve()
    args.dimensions = args.dimensions.resolve()

    if args.behavior_mode == "dry-run" and not args.skip_evaluation:
        raise SystemExit("--behavior-mode dry-run cannot be evaluated; pass --skip-evaluation")
    if args.max_recent_turns < 1:
        raise SystemExit("--max-recent-turns must be at least 1")
    if args.continue_record and not args.message:
        raise SystemExit("--continue-record must be used together with --message")

    load_env_file(args.env_file)
    apply_api_overrides(args)

    if args.record:
        source_record = args.record.resolve()
        initial_record = read_json(source_record)
        conversation_id = str(initial_record.get("conversation_id", "unknown_conversation"))
        target_turn_id = get_record_turn_id(initial_record, args.turn_id)
        args.turn_id = target_turn_id
    elif args.continue_record:
        args.continue_record = args.continue_record.resolve()
        initial_record = complete_dialogue_log_from_turn_records(read_json(args.continue_record))
        conversation_id = args.conversation_id or str(initial_record.get("conversation_id", "unknown_conversation"))
        args.conversation_id = conversation_id
        target_turn_id = get_next_turn_id(initial_record, args.turn_id)
        args.turn_id = target_turn_id
    else:
        conversation_id = args.conversation_id or default_conversation_id()
        args.conversation_id = conversation_id
        target_turn_id = args.turn_id or 1
        args.turn_id = target_turn_id

    output_dir = build_output_dir(args, conversation_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    stages: dict[str, dict[str, Any]] = {}
    evaluation_cases: Path | None = None
    all_turn_evaluation_cases: Path | None = None
    conversation_summary_path: Path | None = None
    dialogue_review_path: Path | None = None
    current_eval_report: dict[str, Any] | None = None
    all_turn_eval_report: dict[str, Any] | None = None

    try:
        if args.record:
            stages["first"] = {"status": "skipped", "reason": "--record was provided"}
            source_record = args.record.resolve()
        else:
            source_record, stages["first"] = run_first_stage(args, output_dir)

        working_record = prepare_working_record(source_record, output_dir)
        record = read_json(working_record)
        target_turn_id = get_record_turn_id(record, args.turn_id or target_turn_id)

        stages["strategy"] = run_strategy_stage(args, working_record, output_dir, target_turn_id)
        stages["behavior"] = run_behavior_stage(args, working_record, output_dir, target_turn_id)

        if not args.skip_evaluation:
            if args.eval_scope in {"current-turn", "both"}:
                evaluation_cases = build_evaluation_cases(working_record, output_dir, target_turn_id)
                current_eval_report = run_evaluation_stage(
                    args,
                    evaluation_cases,
                    output_dir,
                    report_name="05_evaluation_report.json",
                    eval_scope="current_turn",
                )
                stages["evaluation"] = current_eval_report
            else:
                stages["evaluation"] = {"status": "skipped", "reason": "--eval-scope all-turns was provided"}

            if args.eval_scope in {"all-turns", "both"}:
                all_turn_evaluation_cases = build_all_turn_evaluation_cases(working_record, output_dir)
                all_turn_eval_report = run_evaluation_stage(
                    args,
                    all_turn_evaluation_cases,
                    output_dir,
                    report_name="07_all_turn_evaluation_report.json",
                    eval_scope="all_turns",
                )
                stages["evaluation_all_turns"] = all_turn_eval_report
        else:
            stages["evaluation"] = {"status": "skipped", "reason": "--skip-evaluation was provided"}

        conversation_summary_path = write_conversation_summary_report(
            working_record,
            output_dir,
            current_eval_report,
            all_turn_eval_report,
        )
        stages["conversation_summary"] = {"status": "pass", "path": str(conversation_summary_path)}
        dialogue_review_path = write_dialogue_review_report(
            working_record,
            output_dir,
            conversation_summary_path,
            current_eval_report,
            all_turn_eval_report,
        )
        stages["dialogue_review"] = {"status": "pass", "path": str(dialogue_review_path)}
        summary_path = write_summary(
            output_dir,
            working_record,
            args,
            stages,
            evaluation_cases,
            all_turn_evaluation_cases,
            conversation_summary_path,
            dialogue_review_path,
        )
        update_conversation_latest_artifacts(output_dir, working_record, summary_path)
    except Exception as error:  # noqa: BLE001 - CLI should surface stage failures.
        failure_path = output_dir / "full_chain_summary.json"
        write_json(
            failure_path,
            {
                "status": "fail",
                "error": str(error),
                "stages": stages,
                "output_dir": str(output_dir),
            },
        )
        print(f"status=fail")
        print(f"error={error}")
        print(f"summary={failure_path}")
        return 1

    print("status=pass")
    print(f"conversation_id={conversation_id} turn_id={target_turn_id}")
    print(f"record={working_record}")
    print(f"summary={summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


