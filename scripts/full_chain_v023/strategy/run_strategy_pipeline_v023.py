"""Run the PURE-JADE strategy-decision pipeline for Schema v0.2.1.

This script is still only research content 2:

    latest_user_state_card + current_user_message + strategy_references
    -> strategy_decision_card

The difference from run_strategy_pipeline.py is the input format. This script
reads a v0.2.1 conversation_record, extracts the target turn's latest
user_state_card, builds a strategy_decision_request, and then produces a v0.2
strategy_decision_card. It does not pass the full conversation_record to the
strategy model.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import time
from pathlib import Path
from typing import Any

import pure_jade_api as api_client
import run_strategy_pipeline as base


DEFAULT_RECORD = Path("examples/conversation-record-v0.2.1.json")
DEFAULT_REFERENCES = Path("examples/strategy-references-v0.1.json")
DEFAULT_ENV_FILE = Path(".env")

REQUEST_SCHEMA_VERSION = "0.2.1"
CARD_SCHEMA_VERSION = "0.2"
PIPELINE_SCOPE = "research_content_2_strategy_decision_multiturn_v023"
PIPELINE_VERSION = "strategy_pipeline_v0.2.3"

REQUIRED_STRATEGY_FIELDS_V021 = base.REQUIRED_STRATEGY_FIELDS | {
    "state_basis_turn_id",
    "state_change_summary",
}

REQUIRED_LATEST_STATE_FIELDS = {
    "turn_id",
    "dialogue_summary",
    "support_stage",
    "risk_level",
    "risk_memory",
}
CONVERSATION_RECORD_LEVEL_FIELDS = {"dialogue_log", "turn_records", "current_state"}

URGENT_EVENT_ACTION_TERMS = (
    "考试",
    "期末",
    "补考",
    "缓考",
    "教务",
    "老师",
    "辅导员",
    "截止",
    "ddl",
    "deadline",
    "报名",
    "缴费",
    "答辩",
    "面试",
    "预约",
    "航班",
    "火车",
)

URGENT_EVENT_PROBLEM_TERMS = (
    "错过",
    "漏掉",
    "忘了",
    "没赶上",
    "迟到",
    "过了",
    "来不及",
    "要炸",
    "崩了",
)

PRACTICAL_STRATEGIES = {"Providing Suggestions", "Information"}
PRACTICAL_INTENTIONS = {"advise", "inform"}


class RunCheck:
    def __init__(self, conversation_id: str, turn_id: int) -> None:
        self.conversation_id = conversation_id
        self.turn_id = turn_id
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.mismatches: list[str] = []

    @property
    def status(self) -> str:
        return "pass" if not self.errors and not self.mismatches else "fail"

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def mismatch(self, message: str) -> None:
        self.mismatches.append(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "turn_id": self.turn_id,
            "status": self.status,
            "errors": self.errors,
            "warnings": self.warnings,
            "mismatches": self.mismatches,
        }


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def default_report_path(mode: str, turn_id: int) -> Path:
    if mode == "api":
        return Path(f"reports/final/api/strategy_pipeline_v021_api_turn{turn_id}_report.json")
    return Path(f"reports/final/local/strategy_pipeline_v021_{mode}_turn{turn_id}_report.json")


def compact_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def get_target_turn_id(record: dict[str, Any], requested_turn_id: int | None) -> int:
    if requested_turn_id is not None:
        return requested_turn_id
    current_turn_id = record.get("current_turn_id")
    if isinstance(current_turn_id, int):
        return current_turn_id
    return 1


def find_turn_record(record: dict[str, Any], turn_id: int) -> dict[str, Any] | None:
    turn_records = record.get("turn_records")
    if not isinstance(turn_records, list):
        return None
    for item in turn_records:
        if isinstance(item, dict) and item.get("turn_id") == turn_id:
            return item
    return None


def current_user_message(record: dict[str, Any], turn_id: int) -> str:
    dialogue_log = record.get("dialogue_log")
    if not isinstance(dialogue_log, list):
        return ""
    messages = [
        item.get("content")
        for item in dialogue_log
        if isinstance(item, dict) and item.get("turn_id") == turn_id and item.get("speaker") == "user"
    ]
    for message in reversed(messages):
        if isinstance(message, str) and message.strip():
            return message
    return ""


def declared_reference_ids(
    record: dict[str, Any],
    turn_record: dict[str, Any],
    cli_reference_ids: list[str] | None,
) -> list[str]:
    if cli_reference_ids:
        return cli_reference_ids[:3]

    candidates = turn_record.get("strategy_reference_ids")
    if candidates is None:
        strategy_request = turn_record.get("strategy_decision_request")
        if isinstance(strategy_request, dict):
            candidates = strategy_request.get("strategy_reference_ids")
    if candidates is None:
        candidates = record.get("strategy_reference_ids")

    return [ref_id for ref_id in base.as_list(candidates) if isinstance(ref_id, str)][:3]


def select_reference_ids(
    declared_ids: list[str],
    reference_index: dict[str, dict[str, Any]],
    use_references: bool,
    check: RunCheck,
) -> list[str]:
    if not use_references:
        return []
    selected: list[str] = []
    for ref_id in declared_ids[:3]:
        if ref_id in reference_index:
            selected.append(ref_id)
        else:
            check.warn(f"declared strategy reference id was not found: {ref_id}")
    return selected


def build_strategy_decision_request(
    record: dict[str, Any],
    turn_record: dict[str, Any],
    turn_id: int,
    strategy_references: list[dict[str, Any]],
) -> dict[str, Any]:
    user_state_card = turn_record.get("user_state_card")
    if not isinstance(user_state_card, dict):
        user_state_card = {}

    return {
        "conversation_id": record.get("conversation_id"),
        "turn_id": turn_id,
        "schema_version": REQUEST_SCHEMA_VERSION,
        "current_user_message": current_user_message(record, turn_id),
        "latest_user_state_card": user_state_card,
        "strategy_references": strategy_references,
    }


def validate_latest_user_state_card(check: RunCheck, user_state: dict[str, Any]) -> None:
    """Ensure the strategy request receives a state card, not the full local record."""
    missing = sorted(REQUIRED_LATEST_STATE_FIELDS - set(user_state))
    if missing:
        check.error(f"latest_user_state_card missing required state fields: {missing}")

    leaked_fields = sorted(CONVERSATION_RECORD_LEVEL_FIELDS & set(user_state))
    if leaked_fields:
        check.error(f"latest_user_state_card must not contain conversation_record-level fields: {leaked_fields}")


def describe_revisions(user_state: dict[str, Any]) -> list[str]:
    descriptions: list[str] = []
    for item in base.as_list(user_state.get("revised_fields")):
        if not isinstance(item, dict):
            continue
        field = item.get("field")
        previous_value = item.get("previous_value")
        current_value = item.get("current_value")
        if isinstance(field, str):
            descriptions.append(f"{field} 从 {previous_value!r} 调整为 {current_value!r}")
    return descriptions


def state_change_summary(user_state: dict[str, Any]) -> str:
    revisions = describe_revisions(user_state)
    new_evidence = [item for item in base.as_list(user_state.get("new_evidence")) if isinstance(item, str)]
    problem_summary = user_state.get("problem_summary")
    dialogue_summary = user_state.get("dialogue_summary")

    if revisions:
        summary = "本轮根据新增信息更新了用户状态：" + "；".join(revisions)
        if new_evidence:
            summary += "；新增证据：" + "、".join(new_evidence[:3])
        return summary + "。"

    if user_state.get("state_update_type") == "initial":
        if isinstance(problem_summary, str) and problem_summary:
            return f"首轮状态建立：{problem_summary}。"
        return "首轮状态建立。"

    if isinstance(dialogue_summary, str) and dialogue_summary:
        return f"状态延续：{dialogue_summary}"
    return "状态延续，未检测到需要修正的核心字段。"


def reason_from_user_state(
    user_state: dict[str, Any],
    selected_ids: list[str],
) -> str:
    parts = [
        f"最新用户状态卡标记 support_stage={user_state.get('support_stage')!r}",
        f"need={user_state.get('need')!r}",
        f"risk_level={user_state.get('risk_level')!r}",
    ]

    revisions = describe_revisions(user_state)
    if revisions:
        parts.append("本轮状态修正为：" + "；".join(revisions))

    new_evidence = [item for item in base.as_list(user_state.get("new_evidence")) if isinstance(item, str)]
    if new_evidence:
        parts.append("新增证据包括：" + "、".join(new_evidence[:3]))

    if selected_ids:
        parts.append(f"参考策略摘要案例 {', '.join(selected_ids)} 的策略模式")

    return "；".join(parts) + "。"


def rule_strategy_decision_card(
    strategy_request: dict[str, Any],
    selected_ids: list[str],
) -> dict[str, Any]:
    user_state = strategy_request.get("latest_user_state_card")
    if not isinstance(user_state, dict):
        user_state = {}

    decision = base.decision_from_user_state(user_state)
    timing = decision["response_timing"]
    safety_override = decision["support_intention"] == "safety_support"
    if safety_override:
        selected_ids = []

    state_turn_id = user_state.get("turn_id")
    if not isinstance(state_turn_id, int):
        state_turn_id = strategy_request.get("turn_id")

    return {
        "conversation_id": strategy_request.get("conversation_id"),
        "turn_id": strategy_request.get("turn_id"),
        "schema_version": CARD_SCHEMA_VERSION,
        "state_basis_turn_id": state_turn_id,
        "state_change_summary": state_change_summary(user_state),
        "support_intention": decision["support_intention"],
        "primary_strategy": decision["primary_strategy"],
        "secondary_strategy": decision["secondary_strategy"],
        "response_timing": timing,
        "response_intensity": base.response_intensity(user_state, timing),
        "response_goal": base.response_goal(decision),
        "reason": reason_from_user_state(user_state, selected_ids),
        "esconv_example_ids": selected_ids,
        "constraints": base.strategy_constraints(decision),
        "prohibited_actions": base.prohibited_actions(decision),
        "safety_override": safety_override,
    }


def mock_strategy_decision_card(turn_record: dict[str, Any]) -> dict[str, Any]:
    expected = turn_record.get("strategy_decision_card")
    return copy.deepcopy(expected) if isinstance(expected, dict) else {}


def strategy_system_prompt_v023() -> str:
    return """你是 PURE-JADE 项目的共情策略决策模块。
你的任务是根据当前用户输入、最新用户状态卡和可选 ESConv 策略参考案例摘要，输出一张共情策略决策卡。

你只负责第二部分策略决策，不生成最终回复，不重新总结完整历史。
必须遵守以下规则：
1. 只输出一个合法 JSON 对象，不要输出 Markdown、解释文字或代码块。
2. 输出字段必须符合 Schema v0.2 的 strategy_decision_card。
3. schema_version 必须输出 "0.2"。
4. state_basis_turn_id 必须等于 latest_user_state_card.turn_id。
5. state_change_summary 要基于 latest_user_state_card.dialogue_summary、new_evidence 和 revised_fields。
6. 所有枚举值必须从给定枚举中选择，禁止自创标签。
7. primary_strategy 和 secondary_strategy 必须使用 ESConv 8 类策略；但当 safety_override 为 true 时，二者必须为 null。
8. 如果用户状态卡的 risk_level 是 high，必须进入安全覆盖流程。
9. 如果没有提供 ESConv 参考案例，esconv_example_ids 必须输出空数组。
10. reason 必须基于当前用户输入和最新用户状态卡，不要补充没有依据的事实。
11. ESConv 参考案例只用于学习策略选择逻辑，不得复制或改写数据集原始回复。

策略选择原则：
1. risk_level 为 high 或 support_stage 为 safety_override 时，必须输出 safety_support，primary_strategy 和 secondary_strategy 均为 null；但安全支持仍要根据具体风险类型写 constraints，不要默认套用自伤模板。
2. Question 不是默认动作。只有当一个澄清问题会实质改变下一步帮助时，才把 Question 作为 primary_strategy 或 secondary_strategy。
3. 如果用户已经给出足够信息，或明显正在请求帮助、话术、行动、安顿方式，即使 support_stage 仍是 exploration，也可以选择 advise、inform、affirm 或 comfort 来推进。
4. comforting 阶段不等于反复复述。优先判断用户此刻需要被接住、被肯定、被正常化，还是需要一点低负担行动。
5. action 阶段不仅限于用户显式说“怎么办”。当用户处在现实压力、冲突、拖延、学习失控、社交退缩等场景且已有足够上下文时，可以主动给少量可执行下一步。
6. safety_support 时，response_timing 必须为 safety_override，response_intensity 必须为 directive；constraints 应允许一个必要的安全确认问题，但禁止追问危险方法、工具、具体计划或刺激性细节。
7. response_timing 应服务于当轮需要：需要立即支持就 respond_now，需要行动就 offer_next_step，只有信息确实不足时才 ask_clarification。
8. 如果用户遇到现实后果正在发生的事件，例如错过考试/期末、ddl、报名缴费、面试、预约、航班等，不能只做情绪认可。应选择 advise 或 inform，primary/secondary 至少包含 Providing Suggestions 或 Information，response_timing 使用 offer_next_step；目标是“先稳住情绪，再给一个低负担现实下一步”。

表达约束：
1. response_goal 不要写“先复述用户处境”“先表达听到”这类会导致下游机械复读的目标。
2. constraints 不要强制使用固定开头，不要要求“我听到/听起来/确实很难受”等模板句。
3. 如果选择 Restatement or Paraphrasing，只要求一句自然短承接；不要列举用户原话细节，也不要阻止下游给出有帮助的下一步。
4. 多轮对话中优先回应当前轮新信息，并明确是否要推进：安抚、肯定、建议、资源、安全确认或陪伴。
5. 对现实紧急/行政后果事件，不要在 prohibited_actions 或 constraints 中禁止“具体行动建议”“补考/缓考/教务/老师/辅导员”等现实帮助。可以限制为“只给一个下一步，避免吓人和过度承诺”。"""


def strategy_user_prompt_v023(strategy_request: dict[str, Any]) -> str:
    references = strategy_request.get("strategy_references")
    allowed_reference_ids = [
        item.get("example_id") for item in references if isinstance(item, dict) and item.get("example_id")
    ]
    return f"""请根据以下 strategy_decision_request 生成共情策略决策卡。

[strategy_decision_request]
{compact_json(strategy_request)}

[输出字段]
- conversation_id
- turn_id
- schema_version
- state_basis_turn_id
- state_change_summary
- support_intention
- primary_strategy
- secondary_strategy
- response_timing
- response_intensity
- response_goal
- reason
- esconv_example_ids
- constraints
- prohibited_actions
- safety_override

[枚举约束]
support_intention:
clarify, comfort, affirm, normalize, advise, inform, safety_support, fallback_review

primary_strategy / secondary_strategy:
Question, Restatement or Paraphrasing, Reflection of feelings, Self-disclosure, Affirmation and Reassurance, Providing Suggestions, Information, Others, null

response_timing:
ask_clarification, respond_now, offer_next_step, safety_override

response_intensity:
light, gentle, moderate, directive

[ESConv 引用约束]
esconv_example_ids 只能从以下 id 中选择，最多 3 个：
{compact_json(allowed_reference_ids)}

如果上面的 id 列表为空，必须输出 []。
"""


def validate_string_list(check: RunCheck, field_name: str, values: Any, min_items: int, max_items: int) -> None:
    if not isinstance(values, list):
        check.error(f"{field_name} must be a list")
        return
    if len(values) < min_items or len(values) > max_items:
        check.error(f"{field_name} must contain {min_items}-{max_items} items")
    for value in values:
        if not isinstance(value, str) or not value.strip():
            check.error(f"{field_name} contains an empty or non-string value")


def current_message_text(strategy_request: dict[str, Any]) -> str:
    value = strategy_request.get("current_user_message")
    return value.strip() if isinstance(value, str) else ""


def is_urgent_real_world_event(strategy_request: dict[str, Any]) -> bool:
    """Detect concrete, time-sensitive events where support must include next-step help."""
    message = current_message_text(strategy_request)
    if not message:
        return False
    lower_message = message.lower()
    has_event = any(term in message or term in lower_message for term in URGENT_EVENT_ACTION_TERMS)
    has_problem = any(term in message or term in lower_message for term in URGENT_EVENT_PROBLEM_TERMS)
    if has_event and has_problem:
        return True
    return bool(re.search(r"(错过|没赶上|忘了).{0,8}(考试|期末|面试|截止|ddl|deadline)", lower_message))


def contains_banned_practical_block(card: dict[str, Any]) -> bool:
    text = "；".join(
        str(item)
        for field in ("constraints", "prohibited_actions", "response_goal")
        for item in (card.get(field) if isinstance(card.get(field), list) else [card.get(field)])
        if item
    )
    patterns = (
        r"不能.*(具体|行动|解决|补考|教务|老师|辅导员).*建议",
        r"禁止.*(具体|行动|解决|补考|教务|老师|辅导员).*建议",
        r"避免.*(解决方案|具体行动|下一步)",
        r"只.*(情绪|认可|安慰)",
        r"先专注情绪认可",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def validate_urgent_real_world_strategy(
    check: RunCheck,
    card: dict[str, Any],
    strategy_request: dict[str, Any],
) -> None:
    if not is_urgent_real_world_event(strategy_request):
        return

    strategies = {card.get("primary_strategy"), card.get("secondary_strategy")}
    has_practical_strategy = bool(strategies & PRACTICAL_STRATEGIES)
    has_practical_intention = card.get("support_intention") in PRACTICAL_INTENTIONS
    if not has_practical_strategy and not has_practical_intention:
        check.error(
            "urgent real-world consequence cases must include a practical next-step strategy "
            "(Providing Suggestions or Information) instead of pure comfort/reflection"
        )

    if card.get("response_timing") == "respond_now" and card.get("support_intention") == "comfort":
        check.error(
            "urgent real-world consequence cases should not be framed as comfort-only/respond_now; "
            "use offer_next_step after brief emotional validation"
        )

    if contains_banned_practical_block(card):
        check.error(
            "urgent real-world consequence cases must not prohibit realistic next-step help; "
            "do not ban contacting teacher/academic office/counselor, checking makeup/deferred exam policy, "
            "or gathering evidence"
        )


def validate_strategy_card(
    check: RunCheck,
    card: dict[str, Any],
    strategy_request: dict[str, Any],
    reference_ids: set[str],
    use_references: bool,
    allowed_reference_ids: set[str],
) -> None:
    missing = sorted(REQUIRED_STRATEGY_FIELDS_V021 - set(card))
    if missing:
        check.error(f"strategy card missing required keys: {missing}")
        return

    conversation_id = strategy_request.get("conversation_id")
    turn_id = strategy_request.get("turn_id")
    user_state = strategy_request.get("latest_user_state_card")
    if not isinstance(user_state, dict):
        user_state = {}

    if card.get("conversation_id") != conversation_id:
        check.error("conversation_id must equal strategy_decision_request.conversation_id")
    if card.get("turn_id") != turn_id:
        check.error("turn_id must equal strategy_decision_request.turn_id")
    if card.get("schema_version") != CARD_SCHEMA_VERSION:
        check.error(f"schema_version must be {CARD_SCHEMA_VERSION}")
    if card.get("state_basis_turn_id") != user_state.get("turn_id"):
        check.error("state_basis_turn_id must equal latest_user_state_card.turn_id")
    if not isinstance(card.get("state_change_summary"), str) or not card.get("state_change_summary").strip():
        check.error("state_change_summary must be a non-empty string")

    if card.get("support_intention") not in base.ALLOWED_SUPPORT_INTENTIONS:
        check.error(f"invalid support_intention: {card.get('support_intention')!r}")
    for field_name in ("primary_strategy", "secondary_strategy"):
        value = card.get(field_name)
        if value is not None and value not in base.ALLOWED_ESCONV_STRATEGIES:
            check.error(f"invalid {field_name}: {value!r}")
    if card.get("response_timing") not in base.ALLOWED_RESPONSE_TIMINGS:
        check.error(f"invalid response_timing: {card.get('response_timing')!r}")
    if card.get("response_intensity") not in base.ALLOWED_RESPONSE_INTENSITIES:
        check.error(f"invalid response_intensity: {card.get('response_intensity')!r}")
    if not isinstance(card.get("safety_override"), bool):
        check.error("safety_override must be boolean")

    validate_string_list(check, "constraints", card.get("constraints"), 1, 8)
    validate_string_list(check, "prohibited_actions", card.get("prohibited_actions"), 0, 8)

    esconv_ids = card.get("esconv_example_ids")
    if not isinstance(esconv_ids, list):
        check.error("esconv_example_ids must be a list")
    else:
        if len(esconv_ids) > 3:
            check.error("esconv_example_ids must contain at most 3 items")
        if not use_references and esconv_ids:
            check.error("esconv_example_ids must be empty when --no-references is used")
        for ref_id in esconv_ids:
            if ref_id not in reference_ids:
                check.error(f"unknown ESConv reference id: {ref_id}")
            if ref_id not in allowed_reference_ids:
                check.error(f"ESConv reference id was not provided to this run: {ref_id}")

    if user_state.get("risk_level") == "high":
        if card.get("safety_override") is not True:
            check.error("high risk cases must set safety_override=true")
        if card.get("primary_strategy") is not None or card.get("secondary_strategy") is not None:
            check.error("safety override cases must not use ESConv strategies")
        if card.get("esconv_example_ids"):
            check.error("safety override cases must not use ESConv references")
    else:
        if card.get("safety_override") is not False:
            check.error("non-high-risk cases should set safety_override=false")
        if card.get("primary_strategy") is None:
            check.error("non-safety cases must include a primary_strategy")

    validate_urgent_real_world_strategy(check, card, strategy_request)


def api_strategy_decision_card(
    strategy_request: dict[str, Any],
    selected_ids: list[str],
    reference_index: dict[str, dict[str, Any]],
    config: api_client.ApiConfig,
    use_references: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    messages = [
        {"role": "system", "content": strategy_system_prompt_v023()},
        {"role": "user", "content": strategy_user_prompt_v023(strategy_request)},
    ]
    attempts: list[dict[str, Any]] = []
    latest_card: dict[str, Any] = {}

    conversation_id = str(strategy_request.get("conversation_id", "unknown_conversation"))
    turn_id = strategy_request.get("turn_id") if isinstance(strategy_request.get("turn_id"), int) else 1

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
        check = RunCheck(conversation_id, turn_id)
        validate_strategy_card(
            check,
            latest_card,
            strategy_request,
            set(reference_index),
            use_references,
            allowed_reference_ids=set(selected_ids),
        )
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


def compare_to_expected(
    check: RunCheck,
    actual: dict[str, Any],
    expected: dict[str, Any],
    compare_reference_ids: bool,
) -> None:
    fields = base.CORE_MATCH_FIELDS + (["esconv_example_ids"] if compare_reference_ids else [])
    for field_name in fields:
        if actual.get(field_name) != expected.get(field_name):
            check.mismatch(f"{field_name}: expected {expected.get(field_name)!r}, got {actual.get(field_name)!r}")

    if actual.get("state_basis_turn_id") != expected.get("state_basis_turn_id"):
        check.mismatch(
            "state_basis_turn_id: "
            f"expected {expected.get('state_basis_turn_id')!r}, got {actual.get('state_basis_turn_id')!r}"
        )


def run_pipeline(
    record_path: Path,
    references_path: Path,
    report_path: Path | None,
    turn_id: int | None,
    mode: str,
    use_references: bool,
    cli_reference_ids: list[str] | None,
    api_config: api_client.ApiConfig | None,
) -> int:
    record = load_json(record_path)
    if not isinstance(record, dict):
        print("conversation record must be a JSON object")
        return 1

    reference_doc = load_json(references_path)
    reference_index, reference_errors = base.build_reference_index(reference_doc)

    target_turn_id = get_target_turn_id(record, turn_id)
    if report_path is None:
        report_path = default_report_path(mode, target_turn_id)

    conversation_id = str(record.get("conversation_id", "unknown_conversation"))
    check = RunCheck(conversation_id, target_turn_id)

    turn_record = find_turn_record(record, target_turn_id)
    if turn_record is None:
        check.error(f"turn_records does not contain turn_id={target_turn_id}")
        turn_record = {}

    user_state_card = turn_record.get("user_state_card")
    if not isinstance(user_state_card, dict) or not user_state_card:
        check.error("target turn must contain a non-empty user_state_card")
    else:
        validate_latest_user_state_card(check, user_state_card)

    message = current_user_message(record, target_turn_id)
    if not message:
        check.error("dialogue_log must contain the current user message for target turn")

    for error in reference_errors:
        check.error(error)

    declared_ids = declared_reference_ids(record, turn_record, cli_reference_ids)
    selected_ids = select_reference_ids(declared_ids, reference_index, use_references, check)
    strategy_references = base.selected_references(selected_ids, reference_index)
    strategy_request = build_strategy_decision_request(record, turn_record, target_turn_id, strategy_references)

    api_meta: dict[str, Any] | None = None
    if check.errors:
        strategy_card: dict[str, Any] = {}
    elif mode == "mock":
        strategy_card = mock_strategy_decision_card(turn_record)
        if not use_references and isinstance(strategy_card, dict):
            strategy_card["esconv_example_ids"] = []
    elif mode == "api":
        if api_config is None:
            strategy_card = {}
            api_meta = {"status": "failed", "error": "api_config is required for api mode"}
        else:
            strategy_card, api_meta = api_strategy_decision_card(
                strategy_request=strategy_request,
                selected_ids=selected_ids,
                reference_index=reference_index,
                config=api_config,
                use_references=use_references,
            )
    else:
        strategy_card = rule_strategy_decision_card(strategy_request, selected_ids)

    if api_meta and api_meta.get("status") != "valid":
        check.error("api mode did not produce a valid strategy card")

    if strategy_card:
        validate_strategy_card(
            check,
            strategy_card,
            strategy_request,
            set(reference_index),
            use_references,
            allowed_reference_ids=set(selected_ids),
        )

    expected = turn_record.get("strategy_decision_card")
    expected_core = None
    if isinstance(expected, dict) and strategy_card:
        compare_to_expected(check, strategy_card, expected, use_references and mode != "api")
        expected_core = {
            field_name: expected.get(field_name)
            for field_name in base.CORE_MATCH_FIELDS + ["state_basis_turn_id"]
        }
    elif not isinstance(expected, dict):
        check.warn("target turn has no strategy_decision_card for golden comparison")

    report = {
        "status": check.status,
        "pipeline_scope": PIPELINE_SCOPE,
        "pipeline_version": PIPELINE_VERSION,
        "mode": mode,
        "conversation_record_path": str(record_path),
        "references_path": str(references_path),
        "turn_id": target_turn_id,
        "uses_strategy_references": use_references,
        "selected_reference_ids": selected_ids,
        "input": {
            "strategy_decision_request": strategy_request,
        },
        "output": {
            "strategy_decision_card": strategy_card,
        },
        "api": api_meta,
        "expected_core": expected_core,
        "compared_exact_reference_ids": use_references and mode != "api",
        "validation": check.to_dict(),
    }
    write_json(report_path, report)

    print(f"scope={PIPELINE_SCOPE}")
    print(f"mode={mode} use_references={use_references}")
    print(f"conversation_id={conversation_id} turn_id={target_turn_id}")
    print(f"status={check.status}")
    for error in check.errors:
        print(f"  ERROR {error}")
    for mismatch in check.mismatches:
        print(f"  MISMATCH {mismatch}")
    for warning in check.warnings:
        print(f"  WARN {warning}")
    print(f"report={report_path}")

    return 0 if check.status == "pass" else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, default=DEFAULT_RECORD)
    parser.add_argument("--references", type=Path, default=DEFAULT_REFERENCES)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--turn-id", type=int)
    parser.add_argument("--mode", choices=("rules", "mock", "api"), default="rules")
    parser.add_argument("--no-references", action="store_true")
    parser.add_argument("--reference-id", action="append", dest="reference_ids")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--api-url")
    parser.add_argument("--api-model")
    parser.add_argument("--api-temperature", type=float)
    parser.add_argument("--api-timeout", type=int)
    parser.add_argument("--api-max-retries", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_config = None
    if args.mode == "api":
        api_config, config_errors = api_client.load_api_config(args)
        if config_errors:
            print("API configuration is incomplete:")
            for error in config_errors:
                print(f"  - {error}")
            print("Create .env from .env.example or pass --api-model / --api-url.")
            return 2

    return run_pipeline(
        record_path=args.record,
        references_path=args.references,
        report_path=args.report,
        turn_id=args.turn_id,
        mode=args.mode,
        use_references=not args.no_references,
        cli_reference_ids=args.reference_ids,
        api_config=api_config,
    )


if __name__ == "__main__":
    raise SystemExit(main())

