"""Schema-aligned behavior response generator for PURE-JADE.

This is a revised third-part prototype that keeps the original
behavior_generator_api.py untouched.

Module boundary:
    dialogue / recent_dialogue_window + strategy_decision_card
    -> behavior_response_card

It intentionally does not read the first-part user_state_card. In v0.2.1
record mode, the script reads the target turn from conversation_record but
only extracts dialogue_log and strategy_decision_card for behavior generation.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import pure_jade_api as api_client  # noqa: E402


DEFAULT_RECORD = Path("examples/conversation-record-v0.2.1.json")
DEFAULT_CASES = Path("examples/test-cases-v0.1.json")
DEFAULT_ENV_FILE = Path(".env")

ALLOWED_ESCONV_STRATEGIES = {
    "Question",
    "Restatement or Paraphrasing",
    "Reflection of feelings",
    "Self-disclosure",
    "Affirmation and Reassurance",
    "Providing Suggestions",
    "Information",
    "Others",
}
ALLOWED_REALIZED_STRATEGIES = ALLOWED_ESCONV_STRATEGIES | {"Safety Guidance"}
ALLOWED_TONE_STYLES = {
    "warm_and_calm",
    "validating",
    "exploratory",
    "practical",
    "safety_directive",
}
ALLOWED_FACIAL_EXPRESSIONS = {"neutral", "soft_smile", "concerned", None}
ALLOWED_ACTIONS = {"none", "pause", "offer_resource", None}

REQUIRED_STRATEGY_FIELDS = {
    "conversation_id",
    "turn_id",
    "schema_version",
    "support_intention",
    "primary_strategy",
    "secondary_strategy",
    "response_timing",
    "response_intensity",
    "response_goal",
    "reason",
    "esconv_example_ids",
    "constraints",
    "prohibited_actions",
    "safety_override",
}

REQUIRED_BEHAVIOR_V01 = {
    "conversation_id",
    "turn_id",
    "schema_version",
    "text_response",
    "tone_style",
    "strategy_realization",
    "follow_up_question_count",
    "facial_expression",
    "action",
    "safety_message_used",
}
REQUIRED_BEHAVIOR_V02 = REQUIRED_BEHAVIOR_V01 | {
    "uses_previous_context",
    "context_used",
}

FIRST_PART_ONLY_FIELDS = {
    "user_state_card",
    "latest_user_state_card",
    "emotion",
    "emotion_intensity",
    "need",
    "support_stage",
    "risk_level",
    "evidence",
    "unknowns",
    "risk_memory",
}


class BehaviorCheck:
    def __init__(self, conversation_id: str, turn_id: int) -> None:
        self.conversation_id = conversation_id
        self.turn_id = turn_id
        self.errors: list[str] = []
        self.warnings: list[str] = []

    @property
    def status(self) -> str:
        return "pass" if not self.errors else "fail"

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "turn_id": self.turn_id,
            "status": self.status,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def compact_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def count_questions(text: str) -> int:
    return text.count("?") + text.count("？")


def default_report_path(mode: str, source_kind: str, turn_id: int | None, case_id: str | None) -> Path:
    if mode == "api":
        root = Path("reports/final/api")
    else:
        root = Path("reports/final/local")

    if source_kind == "record":
        suffix = f"turn{turn_id or 1}"
    else:
        suffix = case_id or "case"
    return root / f"behavior_generator_schema_aligned_{mode}_{suffix}_report.json"


def find_turn_record(record: dict[str, Any], turn_id: int) -> dict[str, Any] | None:
    for item in as_list(record.get("turn_records")):
        if isinstance(item, dict) and item.get("turn_id") == turn_id:
            return item
    return None


def get_target_turn_id(record: dict[str, Any], requested_turn_id: int | None) -> int:
    if requested_turn_id is not None:
        return requested_turn_id
    current_turn_id = record.get("current_turn_id")
    return current_turn_id if isinstance(current_turn_id, int) else 1


def recent_dialogue_window(record: dict[str, Any], turn_id: int, max_turns: int) -> list[dict[str, Any]]:
    dialogue_log = [item for item in as_list(record.get("dialogue_log")) if isinstance(item, dict)]
    min_turn = max(1, turn_id - max_turns + 1)
    window = [
        {
            "turn_id": item.get("turn_id"),
            "speaker": item.get("speaker"),
            "content": item.get("content"),
        }
        for item in dialogue_log
        if isinstance(item.get("turn_id"), int) and min_turn <= item.get("turn_id") <= turn_id
    ]
    return [item for item in window if item.get("speaker") and item.get("content")]


def find_case(case_doc: dict[str, Any], case_id: str | None) -> dict[str, Any]:
    cases = [item for item in as_list(case_doc.get("cases")) if isinstance(item, dict)]
    if not cases:
        raise ValueError("cases document must contain a non-empty cases list")
    if case_id is None:
        return cases[0]
    for case in cases:
        if case.get("case_id") == case_id:
            return case
    raise ValueError(f"case_id was not found: {case_id}")


def strategy_card_version(strategy_card: dict[str, Any]) -> str:
    version = strategy_card.get("schema_version")
    if version == "0.2":
        return "0.2"
    return "0.1"


def build_input_from_record(
    record_path: Path,
    turn_id: int | None,
    max_recent_turns: int,
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any]]:
    record = load_json(record_path)
    if not isinstance(record, dict):
        raise ValueError("conversation record must be a JSON object")

    target_turn_id = get_target_turn_id(record, turn_id)
    turn_record = find_turn_record(record, target_turn_id)
    if turn_record is None:
        raise ValueError(f"turn_records does not contain turn_id={target_turn_id}")

    strategy_card = turn_record.get("strategy_decision_card")
    if not isinstance(strategy_card, dict) or not strategy_card:
        raise ValueError("target turn must contain a non-empty strategy_decision_card")

    behavior_request = {
        "conversation_id": record.get("conversation_id"),
        "turn_id": target_turn_id,
        "request_schema_version": "0.2.1",
        "target_behavior_schema_version": strategy_card_version(strategy_card),
        "recent_dialogue_window": recent_dialogue_window(record, target_turn_id, max_recent_turns),
        "strategy_decision_card": strategy_card,
        "generation_policy": {
            "direct_upstream_only": True,
            "do_not_read_user_state_card": True,
            "max_follow_up_questions": 1,
        },
    }
    expected = turn_record.get("behavior_response_card")
    expected_behavior = expected if isinstance(expected, dict) else None
    source_meta = {
        "source_kind": "record",
        "record_path": str(record_path),
        "turn_id": target_turn_id,
        "ignored_first_part_card_present": isinstance(turn_record.get("user_state_card"), dict),
    }
    return behavior_request, expected_behavior, source_meta


def build_input_from_case(
    cases_path: Path,
    case_id: str | None,
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any]]:
    case_doc = load_json(cases_path)
    if not isinstance(case_doc, dict):
        raise ValueError("cases file must be a JSON object")
    case = find_case(case_doc, case_id)

    strategy_card = case.get("expected_strategy_decision_card")
    if not isinstance(strategy_card, dict) or not strategy_card:
        raise ValueError("case must contain expected_strategy_decision_card")

    behavior_request = {
        "conversation_id": case.get("case_id"),
        "turn_id": strategy_card.get("turn_id", 1),
        "request_schema_version": "0.1",
        "target_behavior_schema_version": "0.1",
        "dialogue": case.get("dialogue"),
        "strategy_decision_card": strategy_card,
        "generation_policy": {
            "direct_upstream_only": True,
            "do_not_read_user_state_card": True,
            "max_follow_up_questions": 1,
        },
    }
    expected = case.get("expected_behavior_response_card")
    expected_behavior = expected if isinstance(expected, dict) else None
    source_meta = {
        "source_kind": "case",
        "cases_path": str(cases_path),
        "case_id": case.get("case_id"),
        "ignored_first_part_card_present": isinstance(case.get("expected_user_state_card"), dict),
    }
    return behavior_request, expected_behavior, source_meta


def behavior_system_prompt() -> str:
    return """你是 PURE-JADE 项目的第三部分：行为回应生成模块。

你的模块边界非常严格：
1. 你只根据原始/近期对话和第二部分输出的 strategy_decision_card 生成 behavior_response_card。
2. 你不读取、不要求、也不重新推断第一部分 user_state_card。
3. 你不重新选择策略，不覆盖第二部分的 support_intention、primary_strategy、secondary_strategy。
4. strategy_decision_card 中的 response_goal、constraints、prohibited_actions 是你的生成约束。
5. 输出必须是一个合法 JSON 对象，不要输出 Markdown、解释文字或代码块。

Schema v0.1 行为回应卡必须包含：
conversation_id, turn_id, schema_version, text_response, tone_style,
strategy_realization, follow_up_question_count, facial_expression, action,
safety_message_used。

Schema v0.2 行为回应卡在 v0.1 基础上必须额外包含：
uses_previous_context, context_used。

生成规则：
1. conversation_id、turn_id、schema_version 必须与目标行为卡版本和策略卡一致。
2. text_response 只写要发给用户的话，最长 360 字。
3. strategy_realization 必须至少落实 primary_strategy；如果 secondary_strategy 不为 null，也应落实 secondary_strategy。
4. 每个 strategy_realization.text_span 必须是 text_response 中真实出现的片段。
5. follow_up_question_count 只能是 0 或 1，并且回复中最多只出现一个问号。
6. tone_style 只能选择 warm_and_calm, validating, exploratory, practical, safety_directive。
7. facial_expression 只能是 neutral, soft_smile, concerned 或 null。
8. action 只能是 none, pause, offer_resource 或 null。
9. 如果 safety_override 为 true，必须使用安全优先回应：strategy_realization 使用 Safety Guidance，safety_message_used 为 true，tone_style 为 safety_directive，避免诊断、责备、承诺和危险方法细节。
10. 如果目标版本是 v0.2，uses_previous_context 和 context_used 只能描述实际用到的历史对话信息，不要引用 user_state_card。
"""


def behavior_user_prompt(behavior_request: dict[str, Any]) -> str:
    target_version = behavior_request.get("target_behavior_schema_version", "0.1")
    extra_fields = ""
    if target_version == "0.2":
        extra_fields = "\n- uses_previous_context\n- context_used"

    return f"""请根据以下 behavior_response_request 生成行为回应卡。

[behavior_response_request]
{compact_json(behavior_request)}

[输出字段]
- conversation_id
- turn_id
- schema_version
- text_response
- tone_style
- strategy_realization
- follow_up_question_count
- facial_expression
- action
- safety_message_used{extra_fields}

[重要边界]
不要使用第一部分用户状态卡字段。即使请求来源是 conversation_record，也只能使用 recent_dialogue_window/dialogue 和 strategy_decision_card。
"""


def build_messages(behavior_request: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": behavior_system_prompt()},
        {"role": "user", "content": behavior_user_prompt(behavior_request)},
    ]


def validate_string_list(check: BehaviorCheck, field_name: str, values: Any, min_items: int, max_items: int) -> None:
    if not isinstance(values, list):
        check.error(f"{field_name} must be a list")
        return
    if len(values) < min_items or len(values) > max_items:
        check.error(f"{field_name} must contain {min_items}-{max_items} items")
    for value in values:
        if not isinstance(value, str) or not value.strip():
            check.error(f"{field_name} contains an empty or non-string value")


def validate_strategy_card(check: BehaviorCheck, strategy_card: dict[str, Any]) -> None:
    missing = sorted(REQUIRED_STRATEGY_FIELDS - set(strategy_card))
    if missing:
        check.error(f"strategy_decision_card missing required keys: {missing}")
        return
    for field_name in ("primary_strategy", "secondary_strategy"):
        value = strategy_card.get(field_name)
        if value is not None and value not in ALLOWED_ESCONV_STRATEGIES:
            check.error(f"invalid strategy_decision_card.{field_name}: {value!r}")
    if not isinstance(strategy_card.get("safety_override"), bool):
        check.error("strategy_decision_card.safety_override must be boolean")


def validate_behavior_card(
    check: BehaviorCheck,
    card: dict[str, Any],
    behavior_request: dict[str, Any],
) -> None:
    strategy_card = behavior_request.get("strategy_decision_card")
    if not isinstance(strategy_card, dict):
        check.error("behavior_request.strategy_decision_card must be an object")
        return

    target_version = behavior_request.get("target_behavior_schema_version", "0.1")
    required = REQUIRED_BEHAVIOR_V02 if target_version == "0.2" else REQUIRED_BEHAVIOR_V01
    allowed_fields = required

    missing = sorted(required - set(card))
    if missing:
        check.error(f"behavior_response_card missing required keys: {missing}")
        return

    extra = sorted(set(card) - allowed_fields)
    if extra:
        check.error(f"behavior_response_card has fields outside schema: {extra}")

    forbidden = sorted(FIRST_PART_ONLY_FIELDS & set(card))
    if forbidden:
        check.error(f"behavior_response_card must not include first-part fields: {forbidden}")

    if card.get("conversation_id") != strategy_card.get("conversation_id"):
        check.error("conversation_id must equal strategy_decision_card.conversation_id")
    if card.get("turn_id") != strategy_card.get("turn_id"):
        check.error("turn_id must equal strategy_decision_card.turn_id")
    if card.get("schema_version") != target_version:
        check.error(f"schema_version must be {target_version}")

    response = card.get("text_response")
    if not isinstance(response, str) or not response.strip():
        check.error("text_response must be a non-empty string")
        response = ""
    elif len(response) > 360:
        check.error("text_response must be at most 360 characters")

    if card.get("tone_style") not in ALLOWED_TONE_STYLES:
        check.error(f"invalid tone_style: {card.get('tone_style')!r}")
    if card.get("facial_expression") not in ALLOWED_FACIAL_EXPRESSIONS:
        check.error(f"invalid facial_expression: {card.get('facial_expression')!r}")
    if card.get("action") not in ALLOWED_ACTIONS:
        check.error(f"invalid action: {card.get('action')!r}")
    if not isinstance(card.get("safety_message_used"), bool):
        check.error("safety_message_used must be boolean")

    follow_up_count = card.get("follow_up_question_count")
    if not isinstance(follow_up_count, int) or not (0 <= follow_up_count <= 1):
        check.error("follow_up_question_count must be 0 or 1")
    question_count = count_questions(response)
    if question_count > 1:
        check.error(f"text_response contains too many questions: {question_count}")
    if isinstance(follow_up_count, int) and follow_up_count != question_count:
        check.warn(
            "follow_up_question_count does not match literal question marks "
            f"({follow_up_count} declared, {question_count} found)"
        )

    realization = card.get("strategy_realization")
    if not isinstance(realization, list) or not (1 <= len(realization) <= 4):
        check.error("strategy_realization must contain 1-4 items")
        realized: set[str] = set()
    else:
        realized = set()
        for index, item in enumerate(realization):
            if not isinstance(item, dict):
                check.error(f"strategy_realization[{index}] must be an object")
                continue
            item_strategy = item.get("strategy")
            text_span = item.get("text_span")
            if item_strategy not in ALLOWED_REALIZED_STRATEGIES:
                check.error(f"strategy_realization[{index}].strategy is invalid: {item_strategy!r}")
            else:
                realized.add(item_strategy)
            if not isinstance(text_span, str) or not text_span.strip():
                check.error(f"strategy_realization[{index}].text_span must be non-empty")
            elif text_span not in response:
                check.error(f"strategy_realization[{index}].text_span is not in text_response")

    safety_override = strategy_card.get("safety_override") is True
    if safety_override:
        if not card.get("safety_message_used"):
            check.error("safety_override behavior must set safety_message_used=true")
        if "Safety Guidance" not in realized:
            check.error("safety_override behavior must realize Safety Guidance")
    else:
        for required_strategy in (strategy_card.get("primary_strategy"), strategy_card.get("secondary_strategy")):
            if required_strategy is not None and required_strategy not in realized:
                check.error(f"behavior does not realize strategy: {required_strategy}")

    if target_version == "0.2":
        if not isinstance(card.get("uses_previous_context"), bool):
            check.error("uses_previous_context must be boolean")
        validate_string_list(check, "context_used", card.get("context_used"), 0, 6)
        if card.get("uses_previous_context") is False and card.get("context_used"):
            check.error("context_used must be empty when uses_previous_context=false")


def mock_behavior_card(expected_behavior: dict[str, Any] | None) -> dict[str, Any]:
    return json.loads(json.dumps(expected_behavior, ensure_ascii=False)) if expected_behavior else {}


def api_behavior_card(
    behavior_request: dict[str, Any],
    config: api_client.ApiConfig,
) -> tuple[dict[str, Any], dict[str, Any]]:
    messages = build_messages(behavior_request)
    attempts: list[dict[str, Any]] = []
    latest_card: dict[str, Any] = {}

    for attempt_number in range(config.max_retries + 1):
        started = time.time()
        raw_output = ""
        try:
            raw_output, response_json = api_client.request_chat_completion(messages, config)
            parsed_card, parse_error = api_client.extract_json_object(raw_output)
        except Exception as error:  # noqa: BLE001 - keep CLI errors readable.
            attempts.append(
                {
                    "attempt": attempt_number + 1,
                    "status": "api_error",
                    "error": str(error),
                    "elapsed_seconds": round(time.time() - started, 3),
                }
            )
            break

        attempt_record: dict[str, Any] = {
            "attempt": attempt_number + 1,
            "status": "received",
            "raw_output": raw_output,
            "elapsed_seconds": round(time.time() - started, 3),
            "response_id": response_json.get("id") if isinstance(response_json, dict) else None,
        }

        if parse_error:
            attempt_record["status"] = "parse_error"
            attempt_record["errors"] = [parse_error]
            attempts.append(attempt_record)
            messages.extend(
                [
                    {"role": "assistant", "content": raw_output},
                    {"role": "user", "content": api_client.retry_user_prompt([parse_error], raw_output)},
                ]
            )
            continue

        latest_card = parsed_card or {}
        strategy_card = behavior_request.get("strategy_decision_card") or {}
        check = BehaviorCheck(
            str(strategy_card.get("conversation_id", "unknown_conversation")),
            int(strategy_card.get("turn_id", 1)) if isinstance(strategy_card.get("turn_id"), int) else 1,
        )
        validate_behavior_card(check, latest_card, behavior_request)
        if not check.errors:
            attempt_record["status"] = "valid"
            attempts.append(attempt_record)
            return latest_card, {
                "status": "valid",
                "attempts": attempts,
                "model": config.model,
                "url": config.url,
                "json_mode": config.json_mode,
            }

        attempt_record["status"] = "validation_error"
        attempt_record["errors"] = check.errors
        attempts.append(attempt_record)
        messages.extend(
            [
                {"role": "assistant", "content": raw_output},
                {"role": "user", "content": api_client.retry_user_prompt(check.errors, raw_output)},
            ]
        )

    return latest_card, {
        "status": "failed",
        "attempts": attempts,
        "model": config.model,
        "url": config.url,
        "json_mode": config.json_mode,
    }


def run(args: argparse.Namespace) -> int:
    if args.source == "record":
        behavior_request, expected_behavior, source_meta = build_input_from_record(
            args.record,
            args.turn_id,
            args.max_recent_turns,
        )
        report_path = args.report or default_report_path(args.mode, "record", source_meta.get("turn_id"), None)
    else:
        behavior_request, expected_behavior, source_meta = build_input_from_case(args.cases, args.case_id)
        report_path = args.report or default_report_path(args.mode, "case", None, source_meta.get("case_id"))

    strategy_card = behavior_request.get("strategy_decision_card") or {}
    check = BehaviorCheck(
        str(strategy_card.get("conversation_id", "unknown_conversation")),
        int(strategy_card.get("turn_id", 1)) if isinstance(strategy_card.get("turn_id"), int) else 1,
    )
    validate_strategy_card(check, strategy_card if isinstance(strategy_card, dict) else {})

    api_meta: dict[str, Any] | None = None
    behavior_card: dict[str, Any] = {}

    if check.errors:
        pass
    elif args.mode == "dry-run":
        behavior_card = {}
    elif args.mode == "mock":
        behavior_card = mock_behavior_card(expected_behavior)
        validate_behavior_card(check, behavior_card, behavior_request)
    else:
        api_config, config_errors = api_client.load_api_config(args)
        if config_errors:
            for error in config_errors:
                check.error(error)
            api_meta = {"status": "failed", "errors": config_errors}
        elif api_config is not None:
            behavior_card, api_meta = api_behavior_card(behavior_request, api_config)
            if api_meta.get("status") != "valid":
                check.error("api mode did not produce a valid behavior response card")
            if behavior_card:
                validate_behavior_card(check, behavior_card, behavior_request)

    report = {
        "status": "dry_run" if args.mode == "dry-run" and check.status == "pass" else check.status,
        "module_scope": "research_content_3_behavior_response_schema_aligned",
        "mode": args.mode,
        "source": source_meta,
        "input_contract": {
            "uses_dialogue": True,
            "uses_strategy_decision_card": True,
            "uses_user_state_card": False,
            "ignored_first_part_card_present": source_meta.get("ignored_first_part_card_present"),
        },
        "messages": build_messages(behavior_request) if args.mode == "dry-run" else None,
        "input": {
            "behavior_response_request": behavior_request,
        },
        "output": {
            "behavior_response_card": behavior_card,
        },
        "api": api_meta,
        "expected_behavior_available": expected_behavior is not None,
        "validation": check.to_dict(),
    }
    write_json(report_path, report)

    print("scope=research_content_3_behavior_response_schema_aligned")
    print(f"mode={args.mode} source={args.source}")
    print(f"status={report['status']}")
    print("uses_user_state_card=False")
    for error in check.errors:
        print(f"  ERROR {error}")
    for warning in check.warnings:
        print(f"  WARN {warning}")
    print(f"report={report_path}")
    return 0 if report["status"] in {"pass", "dry_run"} else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("record", "case"), default="record")
    parser.add_argument("--record", type=Path, default=DEFAULT_RECORD)
    parser.add_argument("--turn-id", type=int)
    parser.add_argument("--max-recent-turns", type=int, default=3)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--case-id")
    parser.add_argument("--mode", choices=("dry-run", "mock", "api"), default="dry-run")
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
    if args.max_recent_turns < 1:
        raise ValueError("--max-recent-turns must be at least 1")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
