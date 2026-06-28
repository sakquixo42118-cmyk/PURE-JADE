"""Replay and validate PURE-JADE golden test cases.

This script does not call an LLM API. It checks that manually curated
test cases can be used as stable replay fixtures for the future pipeline.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_CASES = Path("examples/test-cases-v0.1.json")
DEFAULT_REFERENCES = Path("examples/strategy-references-v0.1.json")
DEFAULT_REPORT = Path("reports/final/local/replay_report.json")

CARD_SCHEMA_VERSION = "0.1"

ALLOWED_EMOTIONS = {
    "平静",
    "焦虑",
    "沮丧",
    "愤怒",
    "羞耻",
    "孤独",
    "疲惫",
    "自我怀疑",
    "无助",
    "困惑",
    "压力",
    "其他",
}
ALLOWED_NEEDS = {
    "被理解",
    "被肯定",
    "情绪陪伴",
    "信息澄清",
    "解决方案",
    "事实资源",
    "安全支持",
    "表达空间",
    "其他",
}
ALLOWED_SUPPORT_STAGES = {"exploration", "comforting", "action", "safety_override"}
ALLOWED_RISK_LEVELS = {"low", "medium", "high"}
ALLOWED_SUPPORT_INTENTIONS = {
    "clarify",
    "comfort",
    "affirm",
    "normalize",
    "advise",
    "inform",
    "safety_support",
    "fallback_review",
}
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
ALLOWED_RESPONSE_TIMINGS = {
    "ask_clarification",
    "respond_now",
    "offer_next_step",
    "safety_override",
}
ALLOWED_RESPONSE_INTENSITIES = {"light", "gentle", "moderate", "directive"}
ALLOWED_TONES = {
    "warm_and_calm",
    "validating",
    "exploratory",
    "practical",
    "safety_directive",
}
ALLOWED_ACTIONS = {"none", "pause", "offer_resource", None}
ALLOWED_FACIAL_EXPRESSIONS = {"neutral", "soft_smile", "concerned", None}
ALLOWED_EVALUATOR_TYPES = {"llm_initial", "human_review", "teacher_review"}
ALLOWED_VIOLATIONS = {
    "medical_diagnosis",
    "unsafe_advice",
    "strategy_mismatch",
    "unsupported_claim",
    "overly_didactic",
    "copied_esconv_response",
    "too_many_questions",
    "privacy_risk",
    "other",
}

REQUIRED_USER_STATE = {
    "conversation_id",
    "turn_id",
    "schema_version",
    "problem_summary",
    "emotion",
    "emotion_intensity",
    "need",
    "support_stage",
    "risk_level",
    "evidence",
    "unknowns",
    "confidence",
}
REQUIRED_STRATEGY = {
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
REQUIRED_BEHAVIOR = {
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
REQUIRED_EVALUATION = {
    "conversation_id",
    "turn_id",
    "schema_version",
    "emotion_alignment",
    "strategy_consistency",
    "relevance",
    "naturalness",
    "safety",
    "overall_score",
    "violations",
    "review_needed",
    "evaluator_type",
    "review_notes",
}


class CaseCheck:
    def __init__(self, case_id: str) -> None:
        self.case_id = case_id
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
            "case_id": self.case_id,
            "status": self.status,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def required_keys(check: CaseCheck, card_name: str, card: dict[str, Any], required: set[str]) -> None:
    missing = sorted(required - set(card))
    if missing:
        check.error(f"{card_name} missing required keys: {missing}")


def expect_card_identity(
    check: CaseCheck,
    card_name: str,
    card: dict[str, Any],
    case_id: str,
    turn_id: int = 1,
) -> None:
    if card.get("conversation_id") != case_id:
        check.error(f"{card_name}.conversation_id must equal case_id")
    if card.get("turn_id") != turn_id:
        check.error(f"{card_name}.turn_id must be {turn_id}")
    if card.get("schema_version") != CARD_SCHEMA_VERSION:
        check.error(f"{card_name}.schema_version must be {CARD_SCHEMA_VERSION}")


def validate_list_values(
    check: CaseCheck,
    field_name: str,
    values: Any,
    allowed: set[Any],
    min_items: int,
    max_items: int,
) -> None:
    if not isinstance(values, list):
        check.error(f"{field_name} must be a list")
        return
    if len(values) < min_items or len(values) > max_items:
        check.error(f"{field_name} must contain {min_items}-{max_items} items")
    if len(values) != len(set(values)):
        check.error(f"{field_name} must not contain duplicate values")
    for value in values:
        if value not in allowed:
            check.error(f"{field_name} has invalid value: {value!r}")


def validate_string_list(
    check: CaseCheck,
    field_name: str,
    values: Any,
    min_items: int,
    max_items: int,
) -> None:
    if not isinstance(values, list):
        check.error(f"{field_name} must be a list")
        return
    if len(values) < min_items or len(values) > max_items:
        check.error(f"{field_name} must contain {min_items}-{max_items} items")
    for value in values:
        if not isinstance(value, str) or not value.strip():
            check.error(f"{field_name} contains an empty or non-string value")


def validate_score(check: CaseCheck, field_name: str, value: Any) -> None:
    if not isinstance(value, int) or not (1 <= value <= 5):
        check.error(f"{field_name} must be an integer from 1 to 5")


def count_questions(text: str) -> int:
    return text.count("?") + text.count("？")


def validate_user_state(check: CaseCheck, card: dict[str, Any], case_id: str) -> None:
    required_keys(check, "user_state", card, REQUIRED_USER_STATE)
    expect_card_identity(check, "user_state", card, case_id)

    validate_list_values(check, "user_state.emotion", card.get("emotion"), ALLOWED_EMOTIONS, 1, 4)
    validate_list_values(check, "user_state.need", card.get("need"), ALLOWED_NEEDS, 1, 4)

    intensity = card.get("emotion_intensity")
    if not isinstance(intensity, int) or not (0 <= intensity <= 3):
        check.error("user_state.emotion_intensity must be an integer from 0 to 3")
    if card.get("support_stage") not in ALLOWED_SUPPORT_STAGES:
        check.error(f"user_state.support_stage is invalid: {card.get('support_stage')!r}")
    if card.get("risk_level") not in ALLOWED_RISK_LEVELS:
        check.error(f"user_state.risk_level is invalid: {card.get('risk_level')!r}")
    validate_string_list(check, "user_state.evidence", card.get("evidence"), 1, 5)
    validate_string_list(check, "user_state.unknowns", card.get("unknowns"), 0, 5)
    validate_string_list(check, "user_state.risk_signals", card.get("risk_signals", []), 0, 5)

    confidence = card.get("confidence")
    if not isinstance(confidence, (int, float)) or not (0 <= confidence <= 1):
        check.error("user_state.confidence must be a number from 0 to 1")

    if card.get("risk_level") == "high":
        if card.get("support_stage") != "safety_override":
            check.error("high risk cases must use support_stage=safety_override")
        if "安全支持" not in (card.get("need") or []):
            check.error("high risk cases must include need=安全支持")


def validate_strategy(
    check: CaseCheck,
    card: dict[str, Any],
    case_id: str,
    reference_ids: set[str],
    declared_case_refs: list[str],
    user_state: dict[str, Any],
) -> None:
    required_keys(check, "strategy", card, REQUIRED_STRATEGY)
    expect_card_identity(check, "strategy", card, case_id)

    if card.get("support_intention") not in ALLOWED_SUPPORT_INTENTIONS:
        check.error(f"strategy.support_intention is invalid: {card.get('support_intention')!r}")
    for field in ("primary_strategy", "secondary_strategy"):
        value = card.get(field)
        if value is not None and value not in ALLOWED_ESCONV_STRATEGIES:
            check.error(f"strategy.{field} is invalid: {value!r}")
    if card.get("response_timing") not in ALLOWED_RESPONSE_TIMINGS:
        check.error(f"strategy.response_timing is invalid: {card.get('response_timing')!r}")
    if card.get("response_intensity") not in ALLOWED_RESPONSE_INTENSITIES:
        check.error(f"strategy.response_intensity is invalid: {card.get('response_intensity')!r}")

    validate_string_list(check, "strategy.constraints", card.get("constraints"), 1, 8)
    validate_string_list(check, "strategy.prohibited_actions", card.get("prohibited_actions"), 0, 8)

    esconv_ids = card.get("esconv_example_ids")
    if not isinstance(esconv_ids, list):
        check.error("strategy.esconv_example_ids must be a list")
    else:
        if len(esconv_ids) > 3:
            check.error("strategy.esconv_example_ids must contain at most 3 items")
        if set(esconv_ids) != set(declared_case_refs):
            check.error("strategy.esconv_example_ids must match case.strategy_reference_ids")
        for ref_id in esconv_ids:
            if ref_id not in reference_ids:
                check.error(f"unknown ESConv reference id: {ref_id}")

    if user_state.get("risk_level") == "high":
        if card.get("safety_override") is not True:
            check.error("high risk cases must set strategy.safety_override=true")
        if card.get("primary_strategy") is not None or card.get("secondary_strategy") is not None:
            check.error("safety override cases must not use ESConv strategies")
        if card.get("esconv_example_ids") not in ([], None):
            check.error("safety override cases must not use ESConv references")
    else:
        if card.get("safety_override") is not False:
            check.error("non-high-risk golden cases should set safety_override=false")
        if card.get("primary_strategy") is None:
            check.error("non-safety cases must include a primary_strategy")


def validate_behavior(
    check: CaseCheck,
    card: dict[str, Any],
    case_id: str,
    strategy: dict[str, Any],
) -> None:
    required_keys(check, "behavior", card, REQUIRED_BEHAVIOR)
    expect_card_identity(check, "behavior", card, case_id)

    response = card.get("text_response")
    if not isinstance(response, str) or not response.strip():
        check.error("behavior.text_response must be a non-empty string")
        response = ""
    elif len(response) > 360:
        check.error("behavior.text_response must be at most 360 characters")

    if card.get("tone_style") not in ALLOWED_TONES:
        check.error(f"behavior.tone_style is invalid: {card.get('tone_style')!r}")
    if card.get("facial_expression") not in ALLOWED_FACIAL_EXPRESSIONS:
        check.error(f"behavior.facial_expression is invalid: {card.get('facial_expression')!r}")
    if card.get("action") not in ALLOWED_ACTIONS:
        check.error(f"behavior.action is invalid: {card.get('action')!r}")
    if not isinstance(card.get("safety_message_used"), bool):
        check.error("behavior.safety_message_used must be boolean")

    follow_up_count = card.get("follow_up_question_count")
    if not isinstance(follow_up_count, int) or not (0 <= follow_up_count <= 1):
        check.error("behavior.follow_up_question_count must be 0 or 1")
    question_count = count_questions(response)
    if question_count > 1:
        check.error(f"behavior.text_response contains too many questions: {question_count}")
    if isinstance(follow_up_count, int) and question_count != follow_up_count:
        check.warn(
            "behavior.follow_up_question_count does not match literal question marks "
            f"({follow_up_count} declared, {question_count} found)"
        )

    realization = card.get("strategy_realization")
    if not isinstance(realization, list) or not (1 <= len(realization) <= 4):
        check.error("behavior.strategy_realization must contain 1-4 items")
        return

    realized = set()
    for index, item in enumerate(realization):
        if not isinstance(item, dict):
            check.error(f"behavior.strategy_realization[{index}] must be an object")
            continue
        item_strategy = item.get("strategy")
        text_span = item.get("text_span")
        if item_strategy not in ALLOWED_REALIZED_STRATEGIES:
            check.error(f"behavior.strategy_realization[{index}].strategy is invalid: {item_strategy!r}")
        else:
            realized.add(item_strategy)
        if not isinstance(text_span, str) or not text_span.strip():
            check.error(f"behavior.strategy_realization[{index}].text_span must be non-empty")
        elif text_span not in response:
            check.error(f"behavior.strategy_realization[{index}].text_span is not in text_response")

    for required_strategy in (strategy.get("primary_strategy"), strategy.get("secondary_strategy")):
        if required_strategy is not None and required_strategy not in realized:
            check.error(f"behavior does not realize strategy: {required_strategy}")

    if strategy.get("safety_override") and not card.get("safety_message_used"):
        check.error("safety override behavior must set safety_message_used=true")


def validate_evaluation(check: CaseCheck, card: dict[str, Any], case_id: str) -> None:
    required_keys(check, "evaluation", card, REQUIRED_EVALUATION)
    expect_card_identity(check, "evaluation", card, case_id)

    for field in (
        "emotion_alignment",
        "strategy_consistency",
        "relevance",
        "naturalness",
        "safety",
        "overall_score",
    ):
        validate_score(check, f"evaluation.{field}", card.get(field))

    violations = card.get("violations")
    if not isinstance(violations, list):
        check.error("evaluation.violations must be a list")
    else:
        for value in violations:
            if value not in ALLOWED_VIOLATIONS:
                check.error(f"evaluation.violations has invalid value: {value!r}")
    if not isinstance(card.get("review_needed"), bool):
        check.error("evaluation.review_needed must be boolean")
    if card.get("evaluator_type") not in ALLOWED_EVALUATOR_TYPES:
        check.error(f"evaluation.evaluator_type is invalid: {card.get('evaluator_type')!r}")
    if not isinstance(card.get("review_notes"), str):
        check.error("evaluation.review_notes must be a string")


def validate_case(case: dict[str, Any], reference_ids: set[str]) -> CaseCheck:
    case_id = str(case.get("case_id", "<missing-case-id>"))
    check = CaseCheck(case_id)

    if not case.get("dialogue"):
        check.error("case.dialogue must contain at least one user input")

    strategy_reference_ids = case.get("strategy_reference_ids")
    if not isinstance(strategy_reference_ids, list):
        check.error("case.strategy_reference_ids must be a list")
        strategy_reference_ids = []
    elif len(strategy_reference_ids) > 3:
        check.error("case.strategy_reference_ids must contain at most 3 items")
    for ref_id in strategy_reference_ids:
        if ref_id not in reference_ids:
            check.error(f"case.strategy_reference_ids has unknown id: {ref_id}")

    user_state = case.get("expected_user_state_card") or {}
    strategy = case.get("expected_strategy_decision_card") or {}
    behavior = case.get("expected_behavior_response_card") or {}
    evaluation = case.get("expected_evaluation_card") or {}

    if not isinstance(user_state, dict):
        check.error("expected_user_state_card must be an object")
        user_state = {}
    if not isinstance(strategy, dict):
        check.error("expected_strategy_decision_card must be an object")
        strategy = {}
    if not isinstance(behavior, dict):
        check.error("expected_behavior_response_card must be an object")
        behavior = {}
    if not isinstance(evaluation, dict):
        check.error("expected_evaluation_card must be an object")
        evaluation = {}

    validate_user_state(check, user_state, case_id)
    validate_strategy(check, strategy, case_id, reference_ids, strategy_reference_ids, user_state)
    validate_behavior(check, behavior, case_id, strategy)
    validate_evaluation(check, evaluation, case_id)

    return check


def validate_references(reference_doc: dict[str, Any]) -> tuple[set[str], list[str]]:
    errors: list[str] = []
    examples = reference_doc.get("examples")
    if not isinstance(examples, list):
        return set(), ["references.examples must be a list"]

    ids: set[str] = set()
    for index, example in enumerate(examples):
        if not isinstance(example, dict):
            errors.append(f"references.examples[{index}] must be an object")
            continue
        example_id = example.get("example_id")
        if not isinstance(example_id, str) or not example_id:
            errors.append(f"references.examples[{index}].example_id is missing")
            continue
        if example_id in ids:
            errors.append(f"duplicate reference example_id: {example_id}")
        ids.add(example_id)
        if "supporter_response" in example:
            errors.append(f"reference {example_id} must not include original supporter_response")
    return ids, errors


def replay(cases_path: Path, references_path: Path, report_path: Path) -> int:
    case_doc = load_json(cases_path)
    reference_doc = load_json(references_path)

    reference_ids, reference_errors = validate_references(reference_doc)
    case_results = [validate_case(case, reference_ids) for case in case_doc.get("cases", [])]

    if not isinstance(case_doc.get("cases"), list) or not case_results:
        empty_check = CaseCheck("<top-level>")
        empty_check.error("cases document must contain a non-empty cases list")
        case_results.append(empty_check)

    passed = sum(1 for result in case_results if result.status == "pass")
    failed = len(case_results) - passed

    report = {
        "status": "pass" if failed == 0 and not reference_errors else "fail",
        "cases_path": str(cases_path),
        "references_path": str(references_path),
        "case_count": len(case_results),
        "passed": passed,
        "failed": failed,
        "reference_errors": reference_errors,
        "results": [result.to_dict() for result in case_results],
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"cases={len(case_results)} passed={passed} failed={failed}")
    if reference_errors:
        print("reference_errors:")
        for error in reference_errors:
            print(f"  - {error}")
    for result in case_results:
        print(f"{result.status.upper()} {result.case_id}")
        for error in result.errors:
            print(f"  ERROR {error}")
        for warning in result.warnings:
            print(f"  WARN {warning}")
    print(f"report={report_path}")

    return 0 if report["status"] == "pass" else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--references", type=Path, default=DEFAULT_REFERENCES)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return replay(args.cases, args.references, args.report)


if __name__ == "__main__":
    raise SystemExit(main())
