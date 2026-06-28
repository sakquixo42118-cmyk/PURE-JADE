"""Run the PURE-JADE strategy-decision-only pipeline.

This is the local prototype for research content 2:

    dialogue + user_state_card + strategy_references -> strategy_decision_card

It intentionally does not generate the behavior response card or evaluation
card. The default mode uses deterministic rules so the module boundary can be
tested before an LLM API is connected. Mock mode replays the golden strategy
cards exactly. API mode calls an OpenAI-compatible chat-completions endpoint.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_CASES = Path("examples/test-cases-v0.1.json")
DEFAULT_REFERENCES = Path("examples/strategy-references-v0.1.json")
DEFAULT_ENV_FILE = Path(".env")
DEFAULT_API_URL = "https://api.openai.com/v1/chat/completions"

CARD_SCHEMA_VERSION = "0.1"
PIPELINE_SCOPE = "research_content_2_strategy_decision_only"
PIPELINE_VERSION = "strategy_pipeline_v0.1"

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
ALLOWED_RESPONSE_TIMINGS = {
    "ask_clarification",
    "respond_now",
    "offer_next_step",
    "safety_override",
}
ALLOWED_RESPONSE_INTENSITIES = {"light", "gentle", "moderate", "directive"}

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

CORE_MATCH_FIELDS = [
    "support_intention",
    "primary_strategy",
    "secondary_strategy",
    "response_timing",
    "response_intensity",
    "safety_override",
]


@dataclass
class ApiConfig:
    url: str
    api_key: str
    model: str
    temperature: float
    timeout_seconds: int
    max_retries: int
    json_mode: bool


class CaseResult:
    def __init__(self, case_id: str) -> None:
        self.case_id = case_id
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
            "case_id": self.case_id,
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


def read_bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def read_int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def read_float_env(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def normalize_chat_completions_url(url: str) -> str:
    normalized = url.strip().rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def load_api_config(args: argparse.Namespace) -> tuple[ApiConfig | None, list[str]]:
    load_env_file(args.env_file)
    errors: list[str] = []

    url = normalize_chat_completions_url(args.api_url or os.environ.get("PURE_JADE_API_URL") or DEFAULT_API_URL)
    api_key = os.environ.get("PURE_JADE_API_KEY", "")
    model = args.api_model or os.environ.get("PURE_JADE_API_MODEL", "")
    temperature = (
        args.api_temperature
        if args.api_temperature is not None
        else read_float_env("PURE_JADE_API_TEMPERATURE", 0.2)
    )
    timeout_seconds = (
        args.api_timeout
        if args.api_timeout is not None
        else read_int_env("PURE_JADE_API_TIMEOUT_SECONDS", 60)
    )
    max_retries = (
        args.api_max_retries
        if args.api_max_retries is not None
        else read_int_env("PURE_JADE_API_MAX_RETRIES", 1)
    )
    json_mode = read_bool_env("PURE_JADE_API_JSON_MODE", True)

    if not api_key:
        errors.append("missing PURE_JADE_API_KEY")
    if not model:
        errors.append("missing PURE_JADE_API_MODEL")
    if not url:
        errors.append("missing PURE_JADE_API_URL")
    if timeout_seconds <= 0:
        errors.append("PURE_JADE_API_TIMEOUT_SECONDS must be positive")
    if max_retries < 0:
        errors.append("PURE_JADE_API_MAX_RETRIES must be 0 or greater")

    if errors:
        return None, errors
    return (
        ApiConfig(
            url=url,
            api_key=api_key,
            model=model,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            json_mode=json_mode,
        ),
        [],
    )


def default_report_path(mode: str, cases_path: Path, use_references: bool) -> Path:
    is_expanded = cases_path.name == "strategy-test-cases-expanded-v0.1.json"
    no_refs = not use_references

    if mode == "api":
        if is_expanded and no_refs:
            return Path("reports/final/api/strategy_pipeline_api_expanded_no_references_report.json")
        if is_expanded:
            return Path("reports/final/api/strategy_pipeline_api_expanded_report.json")
        if no_refs:
            return Path("reports/final/api/strategy_pipeline_api_no_references_report.json")
        return Path("reports/final/api/strategy_pipeline_api_report.json")

    if mode == "mock":
        if is_expanded and no_refs:
            return Path("reports/final/local/strategy_pipeline_mock_expanded_no_references_report.json")
        if is_expanded:
            return Path("reports/final/local/strategy_pipeline_mock_expanded_report.json")
        if no_refs:
            return Path("reports/final/local/strategy_pipeline_mock_no_references_report.json")
        return Path("reports/final/local/strategy_pipeline_mock_report.json")

    if is_expanded and no_refs:
        return Path("reports/final/local/strategy_pipeline_rules_expanded_no_references_report.json")
    if is_expanded:
        return Path("reports/final/local/strategy_pipeline_rules_expanded_report.json")
    if no_refs:
        return Path("reports/final/local/strategy_pipeline_no_references_report.json")
    return Path("reports/final/local/strategy_pipeline_report.json")


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def contains_any(values: Any, targets: set[str]) -> bool:
    return any(value in targets for value in as_list(values))


def build_reference_index(reference_doc: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    index: dict[str, dict[str, Any]] = {}
    examples = reference_doc.get("examples")
    if not isinstance(examples, list):
        return index, ["references.examples must be a list"]

    for item_index, example in enumerate(examples):
        if not isinstance(example, dict):
            errors.append(f"references.examples[{item_index}] must be an object")
            continue
        example_id = example.get("example_id")
        if not isinstance(example_id, str) or not example_id:
            errors.append(f"references.examples[{item_index}].example_id is missing")
            continue
        if example_id in index:
            errors.append(f"duplicate reference example_id: {example_id}")
        if "supporter_response" in example:
            errors.append(f"reference {example_id} must not include original supporter_response")
        index[example_id] = example
    return index, errors


def selected_reference_ids(case: dict[str, Any], reference_ids: set[str], use_references: bool) -> list[str]:
    if not use_references:
        return []
    ids = [ref_id for ref_id in as_list(case.get("strategy_reference_ids")) if isinstance(ref_id, str)]
    return [ref_id for ref_id in ids[:3] if ref_id in reference_ids]


def selected_references(
    selected_ids: list[str],
    reference_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [reference_index[ref_id] for ref_id in selected_ids if ref_id in reference_index]


def compact_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def strategy_system_prompt() -> str:
    return """你是 PURE-JADE 项目的共情策略决策模块。
你的任务是根据原始对话、用户状态卡和可选 ESConv 策略参考案例摘要，输出一张共情策略决策卡。

你只负责策略决策，不生成最终回复。
必须遵守以下规则：
1. 只输出一个合法 JSON 对象，不要输出 Markdown、解释文字或代码块。
2. 输出字段必须符合 Schema v0.1 的 strategy_decision_card。
3. 所有枚举值必须从给定枚举中选择，禁止自创标签。
4. primary_strategy 和 secondary_strategy 必须使用 ESConv 8 类策略；但当 safety_override 为 true 时，二者必须为 null。
5. 如果用户状态卡的 risk_level 是 high，必须进入安全覆盖流程，不走普通 ESConv 策略。
6. 不进行医学或心理诊断，不编造成员、导师要求、实验结果或数据结论。
7. 如果没有提供 ESConv 参考案例，esconv_example_ids 必须输出空数组。
8. reason 必须基于用户原话和用户状态卡，不要补充没有依据的事实。
9. ESConv 参考案例只用于学习策略选择逻辑，不得复制或改写数据集原始回复。

策略选择优先级：
1. risk_level 为 high 或 support_stage 为 safety_override 时，必须输出 safety_support，primary_strategy 和 secondary_strategy 均为 null。
2. support_stage 为 exploration 时，优先澄清和整理处境；常用 primary_strategy 为 Restatement or Paraphrasing，secondary_strategy 为 Question。
3. support_stage 为 comforting 时，优先承接情绪；常用 primary_strategy 为 Reflection of feelings。
4. support_stage 为 comforting 且 need 包含“被肯定”，或用户出现自我怀疑、自我否定、孤独、多余、努力无用等表达时，secondary_strategy 优先使用 Affirmation and Reassurance。
5. support_stage 为 action 且用户主动询问办法时，才优先使用 Providing Suggestions。
6. 用户询问事实、规则、资源或流程时，才优先使用 Information。
7. “下游回复最多提出一个问题”只是 constraints，不等于必须把 Question 选为 secondary_strategy。
8. 除非 support_intention 是 clarify，或者 support_stage 是 exploration，否则不要因为想追问一个问题就把 secondary_strategy 设为 Question。
9. support_stage 为 action 且 support_intention 为 advise 时，primary_strategy 必须为 Providing Suggestions；如果 unknowns 仍有关键缺口，secondary_strategy 优先为 Question。
10. support_intention 为 inform 时，primary_strategy 必须为 Information，secondary_strategy 优先为 Providing Suggestions，用于给出下一步核实或资源查询方向。
11. support_stage 为 comforting 且 need 只有“被肯定”或主要需求是“被肯定”时，primary_strategy 优先为 Affirmation and Reassurance，而不是 Reflection of feelings。
12. support_intention 为 affirm 且 primary_strategy 为 Affirmation and Reassurance 时，secondary_strategy 优先为 Reflection of feelings；不要用 Restatement or Paraphrasing 替代情绪反映。

支持意图与主策略必须对齐：
1. primary_strategy 为 Reflection of feelings 时，support_intention 应优先为 comfort。
2. primary_strategy 为 Affirmation and Reassurance 时，support_intention 才优先为 affirm。
3. 如果 Affirmation and Reassurance 只是 secondary_strategy，不要仅因此把 support_intention 改成 affirm。
4. 用户同时需要“被理解”和“被肯定”时，如果当前阶段是 comforting，优先输出 support_intention=comfort。
5. 用户主要需求只有“被肯定”时，support_intention 优先为 affirm。

回应强度规则：
1. risk_level 为 high 时，response_intensity 必须为 directive。
2. emotion_intensity 为 0 时，response_intensity 优先为 light。
3. emotion_intensity 为 1 时，若 support_stage 为 exploration 且 response_timing 为 ask_clarification，可为 light；其他情况下优先为 gentle。
4. emotion_intensity 为 2 时，response_intensity 优先为 gentle。
5. emotion_intensity 为 3 且 risk_level 不是 high 时，response_intensity 才优先为 moderate。

回应时机规则：
1. support_intention 为 clarify 时，response_timing 必须为 ask_clarification。
2. support_stage 为 exploration 且策略包含 Question 时，response_timing 必须为 ask_clarification。
3. support_intention 为 comfort、affirm 或 normalize 时，response_timing 优先为 respond_now。
4. support_intention 为 advise 或 inform 时，response_timing 优先为 offer_next_step。
5. safety_support 时，response_timing 必须为 safety_override。
"""


def strategy_user_prompt(
    dialogue: Any,
    user_state_card: Any,
    strategy_references: list[dict[str, Any]],
) -> str:
    allowed_reference_ids = [item.get("example_id") for item in strategy_references]
    return f"""请根据以下信息生成共情策略决策卡。

[原始对话]
{compact_json(dialogue)}

[用户状态卡]
{compact_json(user_state_card)}

[可选 ESConv 策略参考案例摘要]
{compact_json(strategy_references)}

[输出字段]
- conversation_id
- turn_id
- schema_version
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


def retry_user_prompt(validation_errors: list[str], raw_output: str) -> str:
    return f"""上一轮输出无法通过 JSON 或 Schema 校验。
请只输出一个修正后的合法 JSON 对象，不要输出 Markdown 或解释文字。

[校验错误]
{compact_json(validation_errors)}

[上一轮原始输出]
{raw_output}
"""


def request_chat_completion(messages: list[dict[str, str]], config: ApiConfig) -> tuple[str, dict[str, Any]]:
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "temperature": config.temperature,
    }
    if config.json_mode:
        payload["response_format"] = {"type": "json_object"}

    request = urllib.request.Request(
        config.url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API HTTP {error.code}: {error_body}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"API connection failed: {error}") from error

    response_json = json.loads(body)
    return extract_chat_content(response_json), response_json


def extract_chat_content(response_json: dict[str, Any]) -> str:
    choices = response_json.get("choices")
    if isinstance(choices, list) and choices:
        first_choice = choices[0]
        if isinstance(first_choice, dict):
            message = first_choice.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    text_parts = []
                    for part in content:
                        if isinstance(part, dict) and isinstance(part.get("text"), str):
                            text_parts.append(part["text"])
                    if text_parts:
                        return "".join(text_parts)
            if isinstance(first_choice.get("text"), str):
                return first_choice["text"]

    output_text = response_json.get("output_text")
    if isinstance(output_text, str):
        return output_text

    raise RuntimeError("API response did not contain a supported text field")


def extract_json_object(raw_output: str) -> tuple[dict[str, Any] | None, str | None]:
    text = raw_output.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return parsed, None
    if parsed is not None:
        return None, "model output must be a JSON object"

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None, "model output did not contain a JSON object"

    candidate = text[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as error:
        return None, f"model output is not valid JSON: {error}"
    if not isinstance(parsed, dict):
        return None, "model output must be a JSON object"
    return parsed, None


def response_intensity(user_state: dict[str, Any], timing: str) -> str:
    if timing == "safety_override":
        return "directive"
    intensity = user_state.get("emotion_intensity")
    if not isinstance(intensity, int):
        intensity = 1
    if intensity >= 3:
        return "moderate"
    if intensity <= 1 and timing == "ask_clarification":
        return "light"
    return "gentle"


def decision_from_user_state(user_state: dict[str, Any]) -> dict[str, Any]:
    risk_level = user_state.get("risk_level")
    support_stage = user_state.get("support_stage")
    needs = user_state.get("need")
    emotions = user_state.get("emotion")

    if risk_level == "high" or support_stage == "safety_override":
        return {
            "support_intention": "safety_support",
            "primary_strategy": None,
            "secondary_strategy": None,
            "response_timing": "safety_override",
        }

    if support_stage == "exploration":
        if contains_any(needs, {"被理解", "信息澄清", "表达空间"}):
            return {
                "support_intention": "clarify",
                "primary_strategy": "Restatement or Paraphrasing",
                "secondary_strategy": "Question",
                "response_timing": "ask_clarification",
            }
        return {
            "support_intention": "clarify",
            "primary_strategy": "Question",
            "secondary_strategy": "Restatement or Paraphrasing",
            "response_timing": "ask_clarification",
        }

    if support_stage == "action":
        if contains_any(needs, {"事实资源"}):
            return {
                "support_intention": "inform",
                "primary_strategy": "Information",
                "secondary_strategy": "Providing Suggestions",
                "response_timing": "offer_next_step",
            }
        return {
            "support_intention": "advise",
            "primary_strategy": "Providing Suggestions",
            "secondary_strategy": "Question",
            "response_timing": "offer_next_step",
        }

    if support_stage == "comforting":
        if contains_any(needs, {"被肯定"}) and not contains_any(needs, {"被理解", "情绪陪伴"}):
            return {
                "support_intention": "affirm",
                "primary_strategy": "Affirmation and Reassurance",
                "secondary_strategy": "Reflection of feelings",
                "response_timing": "respond_now",
            }
        if contains_any(needs, {"被理解", "情绪陪伴"}) or contains_any(
            emotions,
            {"疲惫", "焦虑", "沮丧", "孤独", "无助", "压力"},
        ):
            return {
                "support_intention": "comfort",
                "primary_strategy": "Reflection of feelings",
                "secondary_strategy": "Affirmation and Reassurance",
                "response_timing": "respond_now",
            }
        if contains_any(emotions, {"孤独"}):
            return {
                "support_intention": "normalize",
                "primary_strategy": "Reflection of feelings",
                "secondary_strategy": "Self-disclosure",
                "response_timing": "respond_now",
            }

    return {
        "support_intention": "fallback_review",
        "primary_strategy": "Others",
        "secondary_strategy": "Question",
        "response_timing": "ask_clarification",
    }


def response_goal(decision: dict[str, Any]) -> str:
    intention = decision["support_intention"]
    if intention == "safety_support":
        return "优先处理现实安全风险，引导用户联系现实支持或当地紧急服务。"
    if intention == "clarify":
        return "先整理用户已经表达的处境，再澄清一个最关键的不确定点。"
    if intention == "comfort":
        return "先承接用户的主要情绪，再给出具体、克制的肯定。"
    if intention == "affirm":
        return "肯定用户已经付出的努力或正在尝试的行动，降低自我否定。"
    if intention == "normalize":
        return "降低用户的孤立感，同时避免把话题转向支持者自身。"
    if intention == "advise":
        return "在承接情绪后提供少量、低负担、可选择的下一步。"
    if intention == "inform":
        return "提供可核实的一般性信息或资源方向，不编造事实。"
    return "标记为需要复核，并提出一个轻量澄清问题。"


def strategy_constraints(decision: dict[str, Any]) -> list[str]:
    constraints = [
        "只输出策略决策，不生成最终回复",
        "reason 必须基于用户原话和用户状态卡",
        "下游回复最多提出一个问题",
    ]
    primary = decision.get("primary_strategy")
    secondary = decision.get("secondary_strategy")
    strategies = {primary, secondary}

    if decision["support_intention"] == "safety_support":
        return [
            "优先鼓励用户联系现实中的可信任人员",
            "如存在即时危险，引导联系当地紧急服务",
            "不提供危险方法、工具或步骤",
            "不承诺保密或保证结果",
        ]
    if "Reflection of feelings" in strategies:
        constraints.append("先承接情绪，不急于给建议")
    if "Affirmation and Reassurance" in strategies:
        constraints.append("肯定必须具体，避免空泛夸奖")
    if "Restatement or Paraphrasing" in strategies:
        constraints.append("先复述处境，不替用户下结论")
    if "Question" in strategies:
        constraints.append("只提出一个核心澄清问题")
    if "Providing Suggestions" in strategies:
        constraints.append("建议数量要少，并保持可选择")
    if "Information" in strategies:
        constraints.append("只提供可核实的一般性信息或资源方向")
    if "Self-disclosure" in strategies:
        constraints.append("自我披露必须简短，并回到用户处境")
    return constraints[:8]


def prohibited_actions(decision: dict[str, Any]) -> list[str]:
    actions = [
        "不要进行医学或心理诊断",
        "不要复制 ESConv 原始回复",
        "不要编造用户没有提供的事实",
    ]
    intention = decision["support_intention"]
    if intention in {"comfort", "affirm", "normalize"}:
        actions.append("不要用说教或比较来压低用户感受")
    if intention in {"advise", "inform"}:
        actions.append("不要把建议说成唯一正确方案")
    if intention == "clarify":
        actions.append("不要连续追问多个问题")
    if intention == "safety_support":
        actions.extend(
            [
                "不要提供危险方法细节",
                "不要把高风险表达当作普通情绪困扰处理",
            ]
        )
    return actions[:8]


def rule_strategy_decision_card(
    case: dict[str, Any],
    selected_ids: list[str],
) -> dict[str, Any]:
    case_id = str(case.get("case_id", "unknown_case"))
    user_state = case.get("expected_user_state_card") or {}
    turn_id = user_state.get("turn_id") if isinstance(user_state.get("turn_id"), int) else 1
    decision = decision_from_user_state(user_state)
    timing = decision["response_timing"]
    safety_override = decision["support_intention"] == "safety_support"
    if safety_override:
        selected_ids = []

    reason_parts = [
        f"用户状态卡标记 support_stage={user_state.get('support_stage')!r}",
        f"need={user_state.get('need')!r}",
        f"risk_level={user_state.get('risk_level')!r}",
    ]
    if selected_ids:
        reason_parts.append(f"参考策略摘要案例 {', '.join(selected_ids)} 的策略模式")

    return {
        "conversation_id": case_id,
        "turn_id": turn_id,
        "schema_version": CARD_SCHEMA_VERSION,
        "support_intention": decision["support_intention"],
        "primary_strategy": decision["primary_strategy"],
        "secondary_strategy": decision["secondary_strategy"],
        "response_timing": timing,
        "response_intensity": response_intensity(user_state, timing),
        "response_goal": response_goal(decision),
        "reason": "；".join(reason_parts) + "。",
        "esconv_example_ids": selected_ids,
        "constraints": strategy_constraints(decision),
        "prohibited_actions": prohibited_actions(decision),
        "safety_override": safety_override,
    }


def mock_strategy_decision_card(case: dict[str, Any]) -> dict[str, Any]:
    expected = case.get("expected_strategy_decision_card")
    return copy.deepcopy(expected) if isinstance(expected, dict) else {}


def validate_string_list(result: CaseResult, field_name: str, values: Any, min_items: int, max_items: int) -> None:
    if not isinstance(values, list):
        result.error(f"{field_name} must be a list")
        return
    if len(values) < min_items or len(values) > max_items:
        result.error(f"{field_name} must contain {min_items}-{max_items} items")
    for value in values:
        if not isinstance(value, str) or not value.strip():
            result.error(f"{field_name} contains an empty or non-string value")


def validate_strategy_card(
    result: CaseResult,
    card: dict[str, Any],
    case: dict[str, Any],
    reference_ids: set[str],
    use_references: bool,
    allowed_reference_ids: set[str] | None = None,
) -> None:
    missing = sorted(REQUIRED_STRATEGY_FIELDS - set(card))
    if missing:
        result.error(f"strategy card missing required keys: {missing}")
        return

    case_id = str(case.get("case_id", "unknown_case"))
    if card.get("conversation_id") != case_id:
        result.error("conversation_id must equal case_id")
    if card.get("turn_id") != 1:
        result.error("turn_id must be 1")
    if card.get("schema_version") != CARD_SCHEMA_VERSION:
        result.error(f"schema_version must be {CARD_SCHEMA_VERSION}")

    if card.get("support_intention") not in ALLOWED_SUPPORT_INTENTIONS:
        result.error(f"invalid support_intention: {card.get('support_intention')!r}")
    for field_name in ("primary_strategy", "secondary_strategy"):
        value = card.get(field_name)
        if value is not None and value not in ALLOWED_ESCONV_STRATEGIES:
            result.error(f"invalid {field_name}: {value!r}")
    if card.get("response_timing") not in ALLOWED_RESPONSE_TIMINGS:
        result.error(f"invalid response_timing: {card.get('response_timing')!r}")
    if card.get("response_intensity") not in ALLOWED_RESPONSE_INTENSITIES:
        result.error(f"invalid response_intensity: {card.get('response_intensity')!r}")
    if not isinstance(card.get("safety_override"), bool):
        result.error("safety_override must be boolean")

    validate_string_list(result, "constraints", card.get("constraints"), 1, 8)
    validate_string_list(result, "prohibited_actions", card.get("prohibited_actions"), 0, 8)

    esconv_ids = card.get("esconv_example_ids")
    if not isinstance(esconv_ids, list):
        result.error("esconv_example_ids must be a list")
    else:
        if len(esconv_ids) > 3:
            result.error("esconv_example_ids must contain at most 3 items")
        if not use_references and esconv_ids:
            result.error("esconv_example_ids must be empty when --no-references is used")
        for ref_id in esconv_ids:
            if ref_id not in reference_ids:
                result.error(f"unknown ESConv reference id: {ref_id}")
            if allowed_reference_ids is not None and ref_id not in allowed_reference_ids:
                result.error(f"ESConv reference id was not provided to this run: {ref_id}")

    user_state = case.get("expected_user_state_card") or {}
    if user_state.get("risk_level") == "high":
        if card.get("safety_override") is not True:
            result.error("high risk cases must set safety_override=true")
        if card.get("primary_strategy") is not None or card.get("secondary_strategy") is not None:
            result.error("safety override cases must not use ESConv strategies")
        if card.get("esconv_example_ids"):
            result.error("safety override cases must not use ESConv references")
    else:
        if card.get("safety_override") is not False:
            result.error("non-high-risk cases should set safety_override=false")
        if card.get("primary_strategy") is None:
            result.error("non-safety cases must include a primary_strategy")


def api_strategy_decision_card(
    case: dict[str, Any],
    selected_ids: list[str],
    reference_index: dict[str, dict[str, Any]],
    config: ApiConfig,
    use_references: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    case_id = str(case.get("case_id", "unknown_case"))
    strategy_references = selected_references(selected_ids, reference_index)
    messages = [
        {"role": "system", "content": strategy_system_prompt()},
        {
            "role": "user",
            "content": strategy_user_prompt(
                dialogue=case.get("dialogue"),
                user_state_card=case.get("expected_user_state_card"),
                strategy_references=strategy_references,
            ),
        },
    ]
    attempts: list[dict[str, Any]] = []
    latest_card: dict[str, Any] = {}

    for attempt_number in range(config.max_retries + 1):
        started = time.time()
        raw_output = ""
        try:
            raw_output, response_json = request_chat_completion(messages, config)
            parsed_card, parse_error = extract_json_object(raw_output)
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
                    {"role": "user", "content": retry_user_prompt([parse_error], raw_output)},
                ]
            )
            continue

        latest_card = parsed_card or {}
        check = CaseResult(case_id)
        validate_strategy_card(
            check,
            latest_card,
            case,
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
                {"role": "user", "content": retry_user_prompt(check.errors, raw_output)},
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
    result: CaseResult,
    actual: dict[str, Any],
    expected: dict[str, Any],
    compare_reference_ids: bool,
) -> None:
    fields = CORE_MATCH_FIELDS + (["esconv_example_ids"] if compare_reference_ids else [])
    for field_name in fields:
        if actual.get(field_name) != expected.get(field_name):
            result.mismatch(
                f"{field_name}: expected {expected.get(field_name)!r}, got {actual.get(field_name)!r}"
            )


def run_case(
    case: dict[str, Any],
    reference_index: dict[str, dict[str, Any]],
    mode: str,
    use_references: bool,
    api_config: ApiConfig | None,
) -> tuple[CaseResult, dict[str, Any]]:
    case_id = str(case.get("case_id", "unknown_case"))
    result = CaseResult(case_id)
    api_meta: dict[str, Any] | None = None

    selected_ids = selected_reference_ids(case, set(reference_index), use_references)
    declared_ids = [ref_id for ref_id in as_list(case.get("strategy_reference_ids")) if isinstance(ref_id, str)]
    if use_references and len(selected_ids) != min(len(declared_ids), 3):
        result.warn("some declared strategy_reference_ids were not found in the reference library")

    if mode == "mock":
        strategy_card = mock_strategy_decision_card(case)
        if not use_references and isinstance(strategy_card, dict):
            strategy_card["esconv_example_ids"] = []
    elif mode == "api":
        if api_config is None:
            strategy_card = {}
            api_meta = {"status": "failed", "error": "api_config is required for api mode"}
        else:
            strategy_card, api_meta = api_strategy_decision_card(
                case=case,
                selected_ids=selected_ids,
                reference_index=reference_index,
                config=api_config,
                use_references=use_references,
            )
    else:
        strategy_card = rule_strategy_decision_card(case, selected_ids)

    if not isinstance(strategy_card, dict):
        strategy_card = {}
        result.error("pipeline output must be an object")
    if api_meta and api_meta.get("status") != "valid":
        result.error("api mode did not produce a valid strategy card")

    validate_strategy_card(
        result,
        strategy_card,
        case,
        set(reference_index),
        use_references,
        allowed_reference_ids=set(selected_ids),
    )
    expected = case.get("expected_strategy_decision_card")
    if isinstance(expected, dict):
        compare_to_expected(result, strategy_card, expected, use_references and mode != "api")
    else:
        result.warn("case has no expected_strategy_decision_card for golden comparison")

    record = {
        "case_id": case_id,
        "title": case.get("title"),
        "pipeline_scope": PIPELINE_SCOPE,
        "input": {
            "dialogue": case.get("dialogue"),
            "user_state_card": case.get("expected_user_state_card"),
            "strategy_references": selected_references(selected_ids, reference_index),
        },
        "output": {
            "strategy_decision_card": strategy_card,
        },
        "api": api_meta,
        "expected_core": {
            field_name: expected.get(field_name) for field_name in CORE_MATCH_FIELDS
        }
        if isinstance(expected, dict)
        else None,
        "compared_exact_reference_ids": use_references and mode != "api",
        "validation": result.to_dict(),
    }
    return result, record


def run_pipeline(
    cases_path: Path,
    references_path: Path,
    report_path: Path,
    mode: str,
    use_references: bool,
    case_ids: set[str] | None,
    api_config: ApiConfig | None,
) -> int:
    case_doc = load_json(cases_path)
    reference_doc = load_json(references_path)
    reference_index, reference_errors = build_reference_index(reference_doc)

    cases = case_doc.get("cases")
    if not isinstance(cases, list):
        cases = []

    selected_cases = [
        case for case in cases if isinstance(case, dict) and (case_ids is None or case.get("case_id") in case_ids)
    ]
    if case_ids is not None:
        found_ids = {case.get("case_id") for case in selected_cases}
        for missing_id in sorted(case_ids - found_ids):
            missing_result = CaseResult(missing_id)
            missing_result.error("requested case_id was not found")
            selected_cases.append({"case_id": missing_id, "_precomputed_result": missing_result})

    results: list[CaseResult] = []
    records: list[dict[str, Any]] = []
    for case in selected_cases:
        precomputed = case.get("_precomputed_result")
        if isinstance(precomputed, CaseResult):
            results.append(precomputed)
            records.append({"case_id": precomputed.case_id, "validation": precomputed.to_dict()})
            continue
        result, record = run_case(case, reference_index, mode, use_references, api_config)
        results.append(result)
        records.append(record)

    if not results:
        empty_result = CaseResult("<top-level>")
        empty_result.error("no cases were selected")
        results.append(empty_result)
        records.append({"case_id": empty_result.case_id, "validation": empty_result.to_dict()})

    if reference_errors:
        reference_result = CaseResult("<references>")
        for error in reference_errors:
            reference_result.error(error)
        results.insert(0, reference_result)
        records.insert(0, {"case_id": reference_result.case_id, "validation": reference_result.to_dict()})

    passed = sum(1 for result in results if result.status == "pass")
    failed = len(results) - passed
    report = {
        "status": "pass" if failed == 0 else "fail",
        "pipeline_scope": PIPELINE_SCOPE,
        "pipeline_version": PIPELINE_VERSION,
        "mode": mode,
        "uses_strategy_references": use_references,
        "api": {
            "url": api_config.url,
            "model": api_config.model,
            "json_mode": api_config.json_mode,
            "max_retries": api_config.max_retries,
        }
        if api_config
        else None,
        "cases_path": str(cases_path),
        "references_path": str(references_path),
        "case_count": len(results),
        "passed": passed,
        "failed": failed,
        "core_match_fields": CORE_MATCH_FIELDS,
        "exact_reference_id_match_required": use_references and mode != "api",
        "records": records,
    }
    write_json(report_path, report)

    print(f"scope={PIPELINE_SCOPE}")
    print(f"mode={mode} use_references={use_references}")
    print(f"cases={len(results)} passed={passed} failed={failed}")
    for result in results:
        print(f"{result.status.upper()} {result.case_id}")
        for error in result.errors:
            print(f"  ERROR {error}")
        for mismatch in result.mismatches:
            print(f"  MISMATCH {mismatch}")
        for warning in result.warnings:
            print(f"  WARN {warning}")
    print(f"report={report_path}")

    return 0 if report["status"] == "pass" else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--references", type=Path, default=DEFAULT_REFERENCES)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--mode", choices=("rules", "mock", "api"), default="rules")
    parser.add_argument("--no-references", action="store_true")
    parser.add_argument("--case-id", action="append", dest="case_ids")
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
        api_config, config_errors = load_api_config(args)
        if config_errors:
            print("API configuration is incomplete:")
            for error in config_errors:
                print(f"  - {error}")
            print("Create .env from .env.example or pass --api-model / --api-url.")
            return 2

    case_ids = set(args.case_ids) if args.case_ids else None
    use_references = not args.no_references
    report_path = args.report or default_report_path(args.mode, args.cases, use_references)
    return run_pipeline(
        cases_path=args.cases,
        references_path=args.references,
        report_path=report_path,
        mode=args.mode,
        use_references=use_references,
        case_ids=case_ids,
        api_config=api_config,
    )


if __name__ == "__main__":
    raise SystemExit(main())
