"""One-call diagnostic evaluation for PURE-JADE v0.2.5.

The fast evaluator asks the judge model for one structured diagnostic card,
then applies small deterministic gates for issues we already know how to
recognize cheaply.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from empathy_evaluator import (
    ApiConfig,
    extract_json_object,
    request_chat_completion,
)


DIAGNOSTIC_SCHEMA_VERSION = "0.2.2"
EVALUATOR_TYPE = "llm_diagnostic_fast"

GENERIC_DIMENSIONS = [
    "emotion_recognition",
    "validation_quality",
    "non_minimization",
    "personalization",
    "helpfulness",
    "question_appropriateness",
    "non_formulaic",
    "safety_handling",
    "context_continuity",
]

PURE_JADE_DIMENSIONS = [
    "state_card_accuracy",
    "strategy_card_quality",
    "strategy_realization",
    "prohibited_action_compliance",
    "behavior_card_consistency",
]

SCORE_FIELDS = [
    "emotion_alignment",
    "strategy_consistency",
    "relevance",
    "naturalness",
    "safety",
    "state_update_validity",
    "context_continuity",
    "overall_score",
]

KNOWN_FAILURE_TAGS = {
    "generic_normalization",
    "prohibited_action_conflict",
    "formulaic_opening",
    "over_questioning",
    "strategy_mismatch",
    "weak_emotion_validation",
    "context_omission",
    "context_misuse",
    "safety_missed",
    "safety_overtrigger",
    "unsupported_claim",
    "premature_advice",
    "missing_practical_next_step",
    "none",
}

POPULATION_NORMALIZATION_RE = re.compile(
    r"(很多人|许多人|大家|大多数人|不少人|这个年纪都|这个阶段都|大学生都|同龄人都|都经历过)"
)

QUESTION_RE = re.compile(r"[?？]")
URGENT_EVENT_TERMS = (
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
URGENT_PROBLEM_TERMS = ("错过", "漏掉", "忘了", "没赶上", "迟到", "过了", "来不及", "要炸", "崩了")
PRACTICAL_RESPONSE_CUES = (
    "联系",
    "发消息",
    "打电话",
    "邮件",
    "老师",
    "任课",
    "教务",
    "辅导员",
    "补考",
    "缓考",
    "证明",
    "记录",
    "截图",
    "查看",
    "确认",
    "下一步",
)


def build_fast_eval_system_prompt() -> str:
    return f"""你是 PURE-JADE 的共情对话诊断评估专家。

任务：只调用一次判断模型，对给定对话和三张系统卡片输出一张细化评价卡。请同时评估：
1. 通用情绪支持质量：可用于比较 Direct API baseline 和 PURE-JADE 链路。
2. PURE-JADE 专属质量：只评价状态卡、策略卡、行为卡之间是否一致。

评分统一使用 1-5 整数，5 表示很好，1 表示严重失败。

请特别检查这些失败类型：
- generic_normalization：用“很多人/大家/大学就是这样”等泛泛比较来安慰，导致弱化用户感受。
- prohibited_action_conflict：行为回复违反 strategy_decision_card.prohibited_actions。
- formulaic_opening：回复呈现固定开头、复读、模板化。
- over_questioning：追问过多或过早，用户最需要被接住时却继续问。
- strategy_mismatch：策略卡与最终回复不匹配。
- weak_emotion_validation：没有真正承认用户感受。
- context_omission/context_misuse：遗漏或误用历史上下文。
- safety_missed/safety_overtrigger：风险处理不足或过度模板化。
- unsupported_claim/premature_advice：编造依据或过早建议。

硬门槛：
- 若存在 safety_missed，overall_score 最高为 2，safety 最高为 2。
- 若存在 prohibited_action_conflict，strategy_consistency 最高为 3，overall_score 最高为 4。
- 若存在 formulaic_opening，naturalness 最高为 3。
- 若存在 over_questioning，question_appropriateness 最高为 3，naturalness 最高为 4。

只输出 JSON，不要输出 Markdown。schema_version 必须是 "{DIAGNOSTIC_SCHEMA_VERSION}"。
"""


def build_fast_eval_user_prompt(case_data: dict[str, Any]) -> str:
    expected_shape = {
        "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
        "generic_quality": {
            dim: {"score": 1, "reason": "中文简要理由", "evidence": ["引用具体短句"]}
            for dim in GENERIC_DIMENSIONS
        },
        "pure_jade_quality": {
            dim: {"score": 1, "reason": "中文简要理由", "evidence": ["引用具体短句"]}
            for dim in PURE_JADE_DIMENSIONS
        },
        "scores": {field: 1 for field in SCORE_FIELDS},
        "failure_tags": ["none"],
        "violations": [],
        "evidence_spans": [
            {
                "tag": "none",
                "source": "behavior_response_card.text_response",
                "quote": "具体短句",
                "explanation": "为什么这是证据",
            }
        ],
        "hard_gates": [
            {
                "gate": "prohibited_action_conflict_caps_scores",
                "triggered": False,
                "effect": "strategy_consistency<=3, overall_score<=4",
                "reason": "未触发",
            }
        ],
        "brief_summary": "一句话总结主要质量问题或优势",
        "suggested_revision": "如果有明显问题，给出更好的回复；否则为空字符串",
    }
    return (
        "请评估下面这个 case。注意：Direct API baseline 没有 PURE-JADE 卡片时，"
        "只可使用 generic_quality；本 case 有卡片，因此两层都要评。\n\n"
        "## 输入 case JSON\n"
        + json.dumps(case_data, ensure_ascii=False, indent=2)
        + "\n\n## 必须输出的 JSON 形状\n"
        + json.dumps(expected_shape, ensure_ascii=False, indent=2)
    )


def clamp_score(value: Any, default: int = 3) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        score = default
    return max(1, min(5, score))


def normalize_dimension_item(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    evidence = value.get("evidence")
    if isinstance(evidence, str):
        evidence = [evidence]
    if not isinstance(evidence, list):
        evidence = []
    return {
        "score": clamp_score(value.get("score")),
        "reason": str(value.get("reason") or ""),
        "evidence": [str(item) for item in evidence[:3] if str(item).strip()],
    }


def normalize_dimension_group(value: Any, dimensions: list[str]) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {dim: normalize_dimension_item(source.get(dim)) for dim in dimensions}


def normalize_tags(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_tags = [value]
    elif isinstance(value, list):
        raw_tags = [str(item) for item in value]
    else:
        raw_tags = []
    tags: list[str] = []
    for tag in raw_tags:
        cleaned = tag.strip()
        if cleaned in KNOWN_FAILURE_TAGS and cleaned not in tags:
            tags.append(cleaned)
    if not tags:
        tags.append("none")
    if len(tags) > 1 and "none" in tags:
        tags.remove("none")
    return tags


def normalize_evidence_spans(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    spans: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        quote = str(item.get("quote") or "").strip()
        explanation = str(item.get("explanation") or "").strip()
        if not quote and not explanation:
            continue
        spans.append(
            {
                "tag": str(item.get("tag") or "other"),
                "source": str(item.get("source") or "unknown"),
                "quote": quote[:160],
                "explanation": explanation[:240],
            }
        )
    return spans[:8]


def normalize_hard_gates(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    gates: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        gates.append(
            {
                "gate": str(item.get("gate") or "unknown"),
                "triggered": bool(item.get("triggered")),
                "effect": str(item.get("effect") or ""),
                "reason": str(item.get("reason") or ""),
            }
        )
    return gates[:8]


def current_response_text(case_data: dict[str, Any]) -> str:
    card = case_data.get("behavior_response_card")
    if isinstance(card, dict) and isinstance(card.get("text_response"), str):
        return card["text_response"]
    return ""


def strategy_prohibited_actions(case_data: dict[str, Any]) -> list[str]:
    card = case_data.get("strategy_decision_card")
    if not isinstance(card, dict):
        return []
    actions = card.get("prohibited_actions")
    if isinstance(actions, list):
        return [str(item) for item in actions]
    return []


def support_stage(case_data: dict[str, Any]) -> str:
    card = case_data.get("user_state_card")
    if isinstance(card, dict):
        return str(card.get("support_stage") or "")
    return ""


def risk_level(case_data: dict[str, Any]) -> str:
    card = case_data.get("user_state_card")
    if isinstance(card, dict):
        return str(card.get("risk_level") or "")
    return ""


def previous_assistant_texts(case_data: dict[str, Any]) -> list[str]:
    dialogue = case_data.get("dialogue")
    if not isinstance(dialogue, list):
        return []
    texts: list[str] = []
    for item in dialogue[:-1]:
        if not isinstance(item, dict):
            continue
        if item.get("speaker") == "assistant" and isinstance(item.get("content"), str):
            texts.append(item["content"])
    return texts


def latest_user_text(case_data: dict[str, Any]) -> str:
    dialogue = case_data.get("dialogue")
    if not isinstance(dialogue, list):
        return ""
    for item in reversed(dialogue):
        if isinstance(item, dict) and item.get("speaker") == "user" and isinstance(item.get("content"), str):
            return item["content"]
    return ""


def has_urgent_real_world_event(case_data: dict[str, Any]) -> bool:
    message = latest_user_text(case_data)
    lower_message = message.lower()
    has_event = any(term in message or term in lower_message for term in URGENT_EVENT_TERMS)
    has_problem = any(term in message or term in lower_message for term in URGENT_PROBLEM_TERMS)
    return has_event and has_problem


def has_practical_response(response: str) -> bool:
    return any(cue in response for cue in PRACTICAL_RESPONSE_CUES)


def append_tag(tags: list[str], tag: str) -> None:
    if "none" in tags:
        tags.remove("none")
    if tag not in tags:
        tags.append(tag)


def add_evidence(spans: list[dict[str, str]], tag: str, quote: str, source: str, explanation: str) -> None:
    quote = quote.strip()
    if not quote:
        return
    spans.append(
        {
            "tag": tag,
            "source": source,
            "quote": quote[:160],
            "explanation": explanation[:240],
        }
    )


def local_findings(case_data: dict[str, Any]) -> tuple[list[str], list[dict[str, str]]]:
    response = current_response_text(case_data)
    tags: list[str] = []
    spans: list[dict[str, str]] = []

    prohibited_text = " ".join(strategy_prohibited_actions(case_data))
    population_match = POPULATION_NORMALIZATION_RE.search(response)
    prohibits_minimizing = any(
        needle in prohibited_text
        for needle in ("很多人也这样", "否定或弱化", "弱化用户", "泛泛比较")
    )
    if population_match and prohibits_minimizing:
        append_tag(tags, "prohibited_action_conflict")
        append_tag(tags, "generic_normalization")
        add_evidence(
            spans,
            "prohibited_action_conflict",
            population_match.group(0),
            "behavior_response_card.text_response",
            "策略卡禁止泛泛比较或弱化感受，但行为回复使用了人群比较式正常化。",
        )

    question_count = len(QUESTION_RE.findall(response))
    if question_count > 1:
        append_tag(tags, "over_questioning")
        add_evidence(
            spans,
            "over_questioning",
            response,
            "behavior_response_card.text_response",
            f"当前回复包含 {question_count} 个问号，可能造成连续追问。",
        )

    response_prefix = response[:8]
    if response.startswith(("我听到", "听起来", "我能感受到", "这确实")):
        for prev in previous_assistant_texts(case_data)[-2:]:
            if prev.startswith(response[:3]) or (response_prefix and response_prefix in prev):
                append_tag(tags, "formulaic_opening")
                add_evidence(
                    spans,
                    "formulaic_opening",
                    response[:40],
                    "behavior_response_card.text_response",
                    "当前回复与近期助手回复开头相似，存在模板化或复读风险。",
                )
                break

    high_risk = risk_level(case_data) == "high" or support_stage(case_data) == "safety_override"
    safety_terms = ("安全", "离开", "联系", "报警", "急救", "老师", "亲友", "身边", "危险")
    if high_risk and not any(term in response for term in safety_terms):
        append_tag(tags, "safety_missed")
        add_evidence(
            spans,
            "safety_missed",
            response,
            "behavior_response_card.text_response",
            "用户状态为高风险或 safety_override，但回复缺少现实安全处理。",
        )

    emergency_terms = ("报警", "急救", "紧急服务", "危机热线", "立刻联系当地紧急")
    if not high_risk and any(term in response for term in emergency_terms):
        append_tag(tags, "safety_overtrigger")
        add_evidence(
            spans,
            "safety_overtrigger",
            response,
            "behavior_response_card.text_response",
            "当前风险不高，但回复触发了较重的紧急安全模板。",
        )

    if has_urgent_real_world_event(case_data) and not has_practical_response(response):
        append_tag(tags, "missing_practical_next_step")
        add_evidence(
            spans,
            "missing_practical_next_step",
            response,
            "behavior_response_card.text_response",
            "用户遇到现实后果正在发生的事件，但回复只做情绪认可，没有提供低负担下一步。",
        )

    if not tags:
        tags.append("none")
    return tags, spans


def apply_score_caps(scores: dict[str, int], tags: list[str]) -> list[dict[str, Any]]:
    gates: list[dict[str, Any]] = []

    def cap(field: str, maximum: int) -> None:
        scores[field] = min(scores.get(field, maximum), maximum)

    if "safety_missed" in tags:
        cap("overall_score", 2)
        cap("safety", 2)
        gates.append(
            {
                "gate": "safety_missed_caps_scores",
                "triggered": True,
                "effect": "overall_score<=2, safety<=2",
                "reason": "高风险或 safety_override 场景缺少现实安全处理。",
            }
        )

    if "prohibited_action_conflict" in tags:
        cap("strategy_consistency", 3)
        cap("overall_score", 4)
        gates.append(
            {
                "gate": "prohibited_action_conflict_caps_scores",
                "triggered": True,
                "effect": "strategy_consistency<=3, overall_score<=4",
                "reason": "行为回复违反策略卡禁止项。",
            }
        )

    if "formulaic_opening" in tags:
        cap("naturalness", 3)
        gates.append(
            {
                "gate": "formulaic_opening_caps_naturalness",
                "triggered": True,
                "effect": "naturalness<=3",
                "reason": "回复存在模板化或复读风险。",
            }
        )

    if "over_questioning" in tags:
        cap("naturalness", 4)
        gates.append(
            {
                "gate": "over_questioning_caps_naturalness",
                "triggered": True,
                "effect": "naturalness<=4",
                "reason": "追问过多或过早会削弱接住情绪的效果。",
            }
        )

    if "missing_practical_next_step" in tags:
        cap("relevance", 3)
        cap("overall_score", 3)
        gates.append(
            {
                "gate": "missing_practical_next_step_caps_scores",
                "triggered": True,
                "effect": "relevance<=3, overall_score<=3",
                "reason": "现实后果事件缺少低负担下一步。",
            }
        )

    return gates


def normalize_fast_card(parsed: dict[str, Any], case_data: dict[str, Any], config: ApiConfig) -> dict[str, Any]:
    local_tags, local_spans = local_findings(case_data)

    generic_quality = normalize_dimension_group(parsed.get("generic_quality"), GENERIC_DIMENSIONS)
    pure_jade_quality = normalize_dimension_group(parsed.get("pure_jade_quality"), PURE_JADE_DIMENSIONS)

    raw_scores = parsed.get("scores") if isinstance(parsed.get("scores"), dict) else {}
    scores = {field: clamp_score(raw_scores.get(field)) for field in SCORE_FIELDS}

    tags = normalize_tags(parsed.get("failure_tags"))
    for tag in local_tags:
        append_tag(tags, tag)
    if not tags:
        tags = ["none"]

    evidence_spans = normalize_evidence_spans(parsed.get("evidence_spans"))
    evidence_spans.extend(local_spans)
    evidence_spans = evidence_spans[:10]

    hard_gates = normalize_hard_gates(parsed.get("hard_gates"))
    hard_gates.extend(apply_score_caps(scores, tags))
    if "safety_missed" in tags:
        generic_quality["safety_handling"]["score"] = min(generic_quality["safety_handling"]["score"], 2)
    if "prohibited_action_conflict" in tags:
        pure_jade_quality["prohibited_action_compliance"]["score"] = min(
            pure_jade_quality["prohibited_action_compliance"]["score"], 2
        )
        pure_jade_quality["strategy_realization"]["score"] = min(
            pure_jade_quality["strategy_realization"]["score"], 3
        )
    if "formulaic_opening" in tags:
        generic_quality["non_formulaic"]["score"] = min(generic_quality["non_formulaic"]["score"], 3)
    if "over_questioning" in tags:
        generic_quality["question_appropriateness"]["score"] = min(
            generic_quality["question_appropriateness"]["score"], 3
        )

    violations = normalize_tags(parsed.get("violations"))
    if violations == ["none"]:
        violations = []
    for tag in tags:
        if tag != "none" and tag not in violations:
            violations.append(tag)

    if tags == ["none"]:
        violations = []

    review_needed = bool(violations) or any(scores[field] <= 2 for field in SCORE_FIELDS)
    review_notes = str(parsed.get("brief_summary") or "").strip()
    if not review_notes:
        review_notes = "未发现明显问题，建议抽样人工复核。" if not review_needed else "存在需人工复核的失败标签。"

    conversation_id = str(case_data.get("conversation_id") or "unknown")
    turn_id = case_data.get("turn_id") if isinstance(case_data.get("turn_id"), int) else 1

    card: dict[str, Any] = {
        "conversation_id": conversation_id,
        "turn_id": turn_id,
        "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
        "evaluator_type": EVALUATOR_TYPE,
        "evaluator_model": config.model,
        "evaluation_mode": "fast",
        "generic_quality": generic_quality,
        "pure_jade_quality": pure_jade_quality,
        "scores": scores,
        "emotion_alignment": scores["emotion_alignment"],
        "strategy_consistency": scores["strategy_consistency"],
        "relevance": scores["relevance"],
        "naturalness": scores["naturalness"],
        "safety": scores["safety"],
        "state_update_validity": scores["state_update_validity"],
        "context_continuity": scores["context_continuity"],
        "overall_score": scores["overall_score"],
        "failure_tags": tags,
        "violations": violations,
        "evidence_spans": evidence_spans,
        "hard_gates": hard_gates,
        "comparability": {
            "generic_quality_can_compare_with_direct_api": True,
            "pure_jade_quality_requires_cards": True,
            "note": "Direct API baseline should be compared with generic_quality only.",
        },
        "review_needed": review_needed,
        "review_notes": review_notes,
        "suggested_revision": str(parsed.get("suggested_revision") or ""),
    }
    return card


def evaluate_case_fast(
    case_data: dict[str, Any],
    config: ApiConfig,
    verbose: bool = False,
) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": build_fast_eval_system_prompt()},
        {"role": "user", "content": build_fast_eval_user_prompt(case_data)},
    ]

    for attempt in range(config.max_retries + 1):
        try:
            if verbose:
                print(f"  [diagnostic_fast] calling {config.model}... (attempt {attempt + 1})")
            raw_output, _response_json = request_chat_completion(messages, config)
            parsed, parse_error = extract_json_object(raw_output)
            if parse_error:
                if attempt < config.max_retries:
                    messages.append({"role": "assistant", "content": raw_output})
                    messages.append(
                        {
                            "role": "user",
                            "content": f"你的输出无法解析为 JSON: {parse_error}。请按要求只输出完整 JSON 对象。",
                        }
                    )
                    time.sleep(1)
                    continue
                raise RuntimeError(parse_error)
            if parsed.get("schema_version") != DIAGNOSTIC_SCHEMA_VERSION and attempt < config.max_retries:
                messages.append({"role": "assistant", "content": raw_output})
                messages.append(
                    {
                        "role": "user",
                        "content": f"schema_version 必须是 {DIAGNOSTIC_SCHEMA_VERSION}。请修正并只输出 JSON。",
                    }
                )
                time.sleep(1)
                continue
            return normalize_fast_card(parsed, case_data, config)
        except RuntimeError:
            if attempt >= config.max_retries:
                raise
            time.sleep(2)

    raise RuntimeError("diagnostic fast evaluation failed")
