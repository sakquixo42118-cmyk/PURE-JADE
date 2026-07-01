"""EmpathyAgent 8-dimension evaluation framework for PURE-JADE.

Reproduces the reference-free evaluation metrics from:
    EmpathyAgent: Can Embodied Agents Conduct Empathetic Actions?
    (arXiv:2503.16545v1, Appendix A.4.2)

Adapted from embodied-agent evaluation to text-based empathetic dialogue.
Evaluates each system response across 8 psychological dimensions using
an LLM evaluator (default: deepseek-chat) scoring 1-10 per dimension.

Usage:
    python scripts/empathy_evaluator.py --mode api --cases examples/eval-test-cases-v0.1.json
    python scripts/empathy_evaluator.py --mode api --cases examples/eval-test-cases-v0.1.json --stage empathetic_actions
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIMENSIONS = PROJECT_ROOT / "config" / "evaluation_dimensions.json"
DEFAULT_CASES = PROJECT_ROOT / "examples" / "eval-test-cases-v0.1.json"
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"
DEFAULT_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "reports" / "evaluation"

EVALUATOR_TYPE = "empathy_agent_8d"
SCHEMA_VERSION = "0.2"


# ---------------------------------------------------------------------------
# Utility functions (same pattern as run_strategy_pipeline.py)
# ---------------------------------------------------------------------------

def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


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


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@dataclass
class ApiConfig:
    url: str
    api_key: str
    model: str
    temperature: float
    timeout_seconds: int
    max_retries: int


def normalize_chat_completions_url(url: str) -> str:
    normalized = url.strip().rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def load_api_config(args: argparse.Namespace) -> tuple[ApiConfig | None, list[str]]:
    load_env_file(args.env_file)
    errors: list[str] = []

    url = normalize_chat_completions_url(
        args.api_url or os.environ.get("PURE_JADE_API_URL") or DEFAULT_API_URL
    )
    api_key = os.environ.get("PURE_JADE_API_KEY", "")
    model = args.api_model or os.environ.get("PURE_JADE_API_MODEL") or DEFAULT_MODEL
    temperature = (
        args.api_temperature
        if args.api_temperature is not None
        else read_float_env("PURE_JADE_API_TEMPERATURE", 0.0)
    )
    timeout_seconds = (
        args.api_timeout
        if args.api_timeout is not None
        else read_int_env("PURE_JADE_API_TIMEOUT_SECONDS", 120)
    )
    max_retries = (
        args.api_max_retries
        if args.api_max_retries is not None
        else read_int_env("PURE_JADE_API_MAX_RETRIES", 1)
    )

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
        ),
        [],
    )


def request_chat_completion(
    messages: list[dict[str, str]], config: ApiConfig
) -> tuple[str, dict[str, Any]]:
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "temperature": config.temperature,
    }
    # DeepSeek supports response_format json_object
    payload["response_format"] = {"type": "json_object"}

    data_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        config.url,
        data=data_bytes,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as resp:
            body = resp.read().decode("utf-8")
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
    output_text = response_json.get("output_text")
    if isinstance(output_text, str):
        return output_text
    raise RuntimeError("API response did not contain a supported text field")


def extract_json_object(raw_output: str) -> tuple[dict[str, Any] | None, str | None]:
    text = raw_output.strip()
    # Direct parse
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return parsed, None
    if parsed is not None:
        return None, "model output must be a JSON object"

    # Try to extract JSON block from markdown
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


# ---------------------------------------------------------------------------
# Evaluation prompt builders
# ---------------------------------------------------------------------------

def build_evaluation_system_prompt(dimension: dict[str, Any]) -> str:
    """Build the system prompt that instructs the evaluator LLM."""
    return f"""你是一个共情对话质量评估专家。你的任务是根据给定的评估维度，对AI助手的共情回复进行评分。

当前评估维度：{dimension['dimension_name_zh']}（{dimension['dimension_name_en']}）

{ dimension['evaluation_prompt']}

请以 JSON 格式输出你的评估结果，格式如下：
{{
  "reasoning": "你的推理过程的全面说明（中文）",
  "score": <0到10的整数>
}}

重要：
- score 必须是整数（0-10），不能是小数
- reasoning 必须详细、具体，引用对话中的具体内容作为证据
- 只输出 JSON，不要输出任何其他文字"""


def build_evaluation_user_prompt(
    dimension: dict[str, Any],
    case_data: dict[str, Any],
    stage: str,
) -> str:
    """Build the user prompt containing the data to evaluate."""

    dialogue = case_data.get("dialogue", [])
    user_state_card = case_data.get("user_state_card", {})
    strategy_decision_card = case_data.get("strategy_decision_card", {})
    behavior_response_card = case_data.get("behavior_response_card", {})

    parts: list[str] = []

    # Context based on stage
    if stage == "scenario_understanding":
        parts.append("## 评估阶段：情境理解")
        parts.append("请评估系统对用户情境的理解质量（用户状态卡）。")
        parts.append("")
        parts.append("### 对话内容")
        parts.append(json.dumps(dialogue, ensure_ascii=False, indent=2))
        parts.append("")
        parts.append("### 用户状态卡（系统输出）")
        parts.append(json.dumps(user_state_card, ensure_ascii=False, indent=2))

    elif stage == "empathetic_planning":
        parts.append("## 评估阶段：共情策略规划")
        parts.append("请评估系统制定的共情策略的质量（策略决策卡）。")
        parts.append("")
        parts.append("### 对话内容")
        parts.append(json.dumps(dialogue, ensure_ascii=False, indent=2))
        parts.append("")
        parts.append("### 用户状态卡")
        parts.append(json.dumps(user_state_card, ensure_ascii=False, indent=2))
        parts.append("")
        parts.append("### 策略决策卡（系统输出）")
        parts.append(json.dumps(strategy_decision_card, ensure_ascii=False, indent=2))

    elif stage == "empathetic_actions":
        parts.append("## 评估阶段：共情行为回应")
        parts.append("请评估系统的最终文本回复的质量（行为回应卡）。")
        parts.append("")
        parts.append("### 对话内容")
        parts.append(json.dumps(dialogue, ensure_ascii=False, indent=2))
        parts.append("")
        parts.append("### 用户状态卡")
        parts.append(json.dumps(user_state_card, ensure_ascii=False, indent=2))
        parts.append("")
        parts.append("### 策略决策卡")
        parts.append(json.dumps(strategy_decision_card, ensure_ascii=False, indent=2))
        parts.append("")
        parts.append("### 行为回应卡 / 系统文本回复（系统输出）")
        parts.append(json.dumps(behavior_response_card, ensure_ascii=False, indent=2))

    elif stage == "multi_turn_state_update":
        parts.append("## 评估阶段：多轮状态更新")
        parts.append("请评估系统在多轮对话中维护用户状态的质量。")
        parts.append("")
        parts.append("### 对话历史")
        parts.append(json.dumps(dialogue, ensure_ascii=False, indent=2))
        parts.append("")
        parts.append("### 上一轮用户状态卡")
        previous_state = case_data.get("previous_user_state_card", {})
        parts.append(json.dumps(previous_state, ensure_ascii=False, indent=2))
        parts.append("")
        parts.append("### 当前轮用户状态卡（系统输出）")
        parts.append(json.dumps(user_state_card, ensure_ascii=False, indent=2))
        parts.append("")
        parts.append("### 当前轮行为回应卡")
        parts.append(json.dumps(behavior_response_card, ensure_ascii=False, indent=2))

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Dimension evaluator
# ---------------------------------------------------------------------------

@dataclass
class DimensionEvalResult:
    dimension_id: str
    dimension_name_zh: str
    score: int | None = None
    reasoning: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.score is not None:
            result["score"] = self.score
        if self.reasoning is not None:
            result["reasoning"] = self.reasoning
        if self.error is not None:
            result["error"] = self.error
        return result


def evaluate_one_dimension(
    dimension: dict[str, Any],
    case_data: dict[str, Any],
    stage: str,
    config: ApiConfig,
    verbose: bool = False,
) -> DimensionEvalResult:
    """Evaluate a single dimension by calling the LLM evaluator."""

    result = DimensionEvalResult(
        dimension_id=dimension["dimension_id"],
        dimension_name_zh=dimension["dimension_name_zh"],
    )

    system_prompt = build_evaluation_system_prompt(dimension)
    user_prompt = build_evaluation_user_prompt(dimension, case_data, stage)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    for attempt in range(config.max_retries + 1):
        try:
            if verbose:
                print(
                    f"  [{dimension['dimension_name_zh']}] "
                    f"calling {config.model}... (attempt {attempt + 1})"
                )

            raw_output, _response_json = request_chat_completion(messages, config)
            parsed, parse_error = extract_json_object(raw_output)

            if parse_error:
                if attempt < config.max_retries:
                    messages.append(
                        {"role": "assistant", "content": raw_output}
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": f"你的输出无法解析为 JSON: {parse_error}。请只输出 JSON 对象: {{\"reasoning\": \"...\", \"score\": <0-10 整数>}}",
                        }
                    )
                    time.sleep(1)
                    continue
                result.error = parse_error
                return result

            # Validate the parsed result
            raw_score = parsed.get("score")
            reasoning = parsed.get("reasoning", "")

            if raw_score is None:
                if attempt < config.max_retries:
                    messages.append(
                        {"role": "assistant", "content": raw_output}
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": '缺少 "score" 字段。请输出 JSON: {"reasoning": "...", "score": <0-10 整数>}',
                        }
                    )
                    time.sleep(1)
                    continue
                result.error = "missing 'score' field in evaluator output"
                return result

            try:
                score = int(raw_score)
            except (ValueError, TypeError):
                if attempt < config.max_retries:
                    messages.append(
                        {"role": "assistant", "content": raw_output}
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": f'"score" 必须是 0-10 的整数，而不是 {raw_score}。请修正。',
                        }
                    )
                    time.sleep(1)
                    continue
                result.error = f"invalid score value: {raw_score}"
                return result

            if score < 0 or score > 10:
                if attempt < config.max_retries:
                    messages.append(
                        {"role": "assistant", "content": raw_output}
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": f'"score" 必须是 0-10 的整数，当前值为 {score}。请修正。',
                        }
                    )
                    time.sleep(1)
                    continue
                result.error = f"score out of range [0,10]: {score}"
                return result

            result.score = score
            result.reasoning = reasoning
            return result

        except RuntimeError as exc:
            if attempt < config.max_retries:
                print(f"  [{dimension['dimension_name_zh']}] retry after error: {exc}")
                time.sleep(2)
                continue
            result.error = str(exc)
            return result

    result.error = "max retries exceeded"
    return result


# ---------------------------------------------------------------------------
# Case evaluator
# ---------------------------------------------------------------------------

# Dimensions that apply to each stage (matching the paper's Table 1)
STAGE_DIMENSION_MAP: dict[str, list[str]] = {
    "scenario_understanding": [
        "content_emotion_association",
        "coherence",
        "emotional_communication",
        "individual_understanding",
    ],
    "empathetic_planning": [
        "content_emotion_association",
        "coherence",
        "emotional_communication",
        "individual_understanding",
        "emotion_regulation",
        "helpfulness",
        "adaptability",
    ],
    "empathetic_actions": [
        "content_emotion_association",
        "coherence",
        "emotional_communication",
        "individual_understanding",
        "emotion_regulation",
        "helpfulness",
        "adaptability",
        "constraint_compliance",
    ],
    "multi_turn_state_update": [
        "state_update_validity",
        "context_continuity",
    ],
}


@dataclass
class CaseEvalResult:
    conversation_id: str
    turn_id: int
    dimension_scores: dict[str, DimensionEvalResult] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def overall_score(self) -> float | None:
        scores = [
            r.score for r in self.dimension_scores.values() if r.score is not None
        ]
        if not scores:
            return None
        return round(sum(scores) / len(scores), 2)

    def to_evaluation_card(self, config: ApiConfig) -> dict[str, Any]:
        dimensions: dict[str, Any] = {}
        violations: list[str] = []

        for dim_id, result in self.dimension_scores.items():
            dimensions[dim_id] = result.to_dict()
            if result.error:
                violations.append(f"{dim_id}: {result.error}")

        card: dict[str, Any] = {
            "conversation_id": self.conversation_id,
            "turn_id": self.turn_id,
            "schema_version": SCHEMA_VERSION,
            "evaluator_type": EVALUATOR_TYPE,
            "evaluator_model": config.model,
            "dimensions": dimensions,
            "overall_score": self.overall_score,
            "violations": violations,
            "review_needed": bool(violations),
        }
        return card

    def map_to_v0_1_card(self, config: ApiConfig) -> dict[str, Any]:
        """Map 8-dimension scores (1-10) to PURE-JADE v0.1 evaluation card (1-5)."""
        scores = {
            dim_id: r.score
            for dim_id, r in self.dimension_scores.items()
            if r.score is not None
        }

        def dim_avg(*dim_ids: str) -> float:
            vals = [scores[d] for d in dim_ids if d in scores]
            return sum(vals) / len(vals) if vals else 5.0

        # Map 1-10 dimension averages to 1-5 integer scores
        def to_1_5(score_1_10: float) -> int:
            return max(1, min(5, round(score_1_10 / 2)))

        emotion_alignment = to_1_5(dim_avg("emotional_communication", "emotion_regulation"))
        strategy_consistency = to_1_5(dim_avg("coherence", "content_emotion_association"))
        relevance = to_1_5(dim_avg("content_emotion_association", "helpfulness"))
        naturalness = to_1_5(dim_avg("adaptability"))
        safety = to_1_5(dim_avg("constraint_compliance"))
        overall_score = to_1_5(dim_avg(
            "emotional_communication", "emotion_regulation",
            "coherence", "content_emotion_association",
            "helpfulness", "adaptability", "constraint_compliance",
        ))

        # Detect violations from dimension reasoning
        violations = self._detect_violations()

        # Build review notes from key findings
        review_notes_parts = []
        for dim_id, result in self.dimension_scores.items():
            dim_name = dim_id.replace("_", " ")
            if result.score is not None and result.score < 6:
                review_notes_parts.append(f"{dim_name}偏低({result.score}/10)")
        if not review_notes_parts:
            review_notes_parts.append("各维度表现良好，建议人工抽样复核")

        return {
            "conversation_id": self.conversation_id,
            "turn_id": self.turn_id,
            "schema_version": "0.1",
            "emotion_alignment": emotion_alignment,
            "strategy_consistency": strategy_consistency,
            "relevance": relevance,
            "naturalness": naturalness,
            "safety": safety,
            "overall_score": overall_score,
            "violations": violations,
            "review_needed": bool(violations) or any(
                r.score is not None and r.score < 6
                for r in self.dimension_scores.values()
            ),
            "evaluator_type": "llm_initial",
            "review_notes": "; ".join(review_notes_parts),
            "_8dim_detail": {
                dim_id: r.to_dict() for dim_id, r in self.dimension_scores.items()
            },
        }

    def map_to_v0_2_card(self, config: ApiConfig) -> dict[str, Any]:
        """Map to PURE-JADE v0.2 evaluation card (v0.1 fields + multi-turn fields)."""
        # Start with v0.1 base
        card = self.map_to_v0_1_card(config)
        card["schema_version"] = "0.2"

        # Add v0.2 multi-turn fields
        state_update = self.dimension_scores.get("state_update_validity")
        context_cont = self.dimension_scores.get("context_continuity")

        card["state_update_validity"] = (
            max(1, min(5, round(state_update.score / 2)))
            if state_update and state_update.score is not None
            else 3  # default mid if not evaluated
        )
        card["context_continuity"] = (
            max(1, min(5, round(context_cont.score / 2)))
            if context_cont and context_cont.score is not None
            else 3
        )
        card["memory_issues"] = self._detect_memory_issues()

        # Update overall_score to include v0.2 dimensions
        all_scores_1_5 = [
            card["emotion_alignment"],
            card["strategy_consistency"],
            card["relevance"],
            card["naturalness"],
            card["safety"],
            card["state_update_validity"],
            card["context_continuity"],
        ]
        card["overall_score"] = max(1, min(5, round(sum(all_scores_1_5) / len(all_scores_1_5))))

        return card

    def _detect_memory_issues(self) -> list[str]:
        """Detect multi-turn memory issues from dimension reasonings."""
        issues: list[str] = []
        state_update = self.dimension_scores.get("state_update_validity")
        context_cont = self.dimension_scores.get("context_continuity")

        # Check state update reasoning for memory issues
        if state_update and state_update.reasoning:
            r = state_update.reasoning
            # Only flag if it's a REAL issue, not a first-turn or negative mention
            is_initial = "第一轮" in r or "初始创建" in r or "initial" in r.lower()
            if not is_initial:
                if any(kw in r for kw in ["忽略了新证据", "未吸收新信息", "没有考虑新增", "遗漏了当前轮"]):
                    issues.append("ignored_new_evidence")
                if any(kw in r for kw in ["过度依赖旧状态", "过分权重旧状态", "未根据新证据调整"]):
                    issues.append("overweighted_old_state")
                if any(kw in r for kw in ["缺乏证据的修正", "无依据的修改", "修正理由不充分"]):
                    issues.append("unsupported_revision")
                if any(kw in r for kw in ["遗漏了风险信号", "风险信号被遗忘", "高风险信号丢失"]):
                    issues.append("missed_risk_signal")

        # Check context continuity reasoning
        if context_cont and context_cont.reasoning:
            r = context_cont.reasoning
            is_first_turn = "第一轮" in r or "没有历史上下文" in r or "从零开始" in r
            if not is_first_turn:
                # Detect REAL forgetting (exclude negations like "没有遗忘")
                if "遗忘" in r and not any(neg in r for neg in ["没有遗忘", "未遗忘", "无遗忘", "未被遗忘"]):
                    issues.append("forgot_relevant_context")
                if "忘记提及" in r:
                    issues.append("forgot_relevant_context")
                if any(kw in r for kw in ["未使用相关上下文", "未引用历史"]):
                    issues.append("forgot_relevant_context")
                # Detect REAL ignoring (exclude negations)
                if "忽略" in r and not any(neg in r for neg in ["没有忽略", "未忽略", "无忽略"]):
                    if "ignored_new_evidence" not in issues:
                        issues.append("ignored_new_evidence")
                if any(kw in r for kw in ["遗漏了", "未考虑"]):
                    if "ignored_new_evidence" not in issues:
                        issues.append("ignored_new_evidence")

        # Also check dimension scores (only for non-first-turn)
        if state_update and state_update.score is not None and state_update.score < 5:
            if "unsupported_revision" not in issues:
                issues.append("unsupported_revision")
        if context_cont and context_cont.score is not None and context_cont.score < 5:
            if "forgot_relevant_context" not in issues:
                issues.append("forgot_relevant_context")

        if not issues:
            issues.append("none")

        # Deduplicate and limit
        seen: set[str] = set()
        unique = []
        for i in issues:
            if i not in seen:
                seen.add(i)
                unique.append(i)
        return unique[:5]

    def _detect_violations(self) -> list[str]:
        """Heuristic violation detection from dimension reasoning text.

        Only flags a violation when the reasoning clearly indicates the assistant
        actually DID something wrong — not when it says the assistant avoided it.
        """
        violations: list[str] = []
        constraint = self.dimension_scores.get("constraint_compliance")

        if constraint and constraint.score is not None and constraint.score < 5:
            violations.append("unsafe_advice")
        if constraint and constraint.score is not None and constraint.score < 3:
            violations.append("privacy_risk")

        # Detect from coherence: strategy mismatch when response doesn't follow the plan
        coherence = self.dimension_scores.get("coherence")
        if coherence and coherence.score is not None and coherence.score < 6:
            violations.append("strategy_mismatch")

        # Only check reasoning for explicit violation mentions
        if constraint and constraint.reasoning:
            # Look for positive violation indicators (assistant DID the bad thing)
            pos_indicators = [
                "存在违规", "确实违反", "未能遵守", "出现了诊断", "进行了诊断",
                "做出了诊断", "含有说教", "使用了说教", "贬低了", "压低了",
                "编造了", "捏造了", "泄露了", "违反了",
            ]
            for indicator in pos_indicators:
                if indicator in constraint.reasoning:
                    if any(kw in indicator for kw in ["诊断"]):
                        if "medical_diagnosis" not in violations:
                            violations.append("medical_diagnosis")
                    if any(kw in indicator for kw in ["说教", "贬低", "压低"]):
                        if "overly_didactic" not in violations:
                            violations.append("overly_didactic")
                    if any(kw in indicator for kw in ["编造", "捏造"]):
                        if "unsupported_claim" not in violations:
                            violations.append("unsupported_claim")

        return violations[:5]  # Max 5 violations


def evaluate_case(
    case_data: dict[str, Any],
    dimensions_config: dict[str, Any],
    config: ApiConfig,
    stage_filter: str | None = None,
    verbose: bool = False,
) -> CaseEvalResult:
    """Evaluate a single conversation case across all applicable dimensions."""

    conversation_id = case_data.get("conversation_id", "unknown")
    turn_id = case_data.get("turn_id", 1)

    result = CaseEvalResult(conversation_id=conversation_id, turn_id=turn_id)

    dimensions = dimensions_config["dimensions"]
    dim_index = {d["dimension_id"]: d for d in dimensions}

    # Determine which stages to evaluate
    if stage_filter:
        if stage_filter not in STAGE_DIMENSION_MAP:
            result.errors.append(f"unknown stage: {stage_filter}")
            return result
        stages = [stage_filter]
    else:
        stages = list(STAGE_DIMENSION_MAP.keys())

    if verbose:
        stage_label = stage_filter or "all"
        print(f"\n--- Evaluating case: {conversation_id} (stage={stage_label}) ---")

    # Collect unique dimensions across all selected stages
    seen_dim_ids: set[str] = set()
    dim_tasks: list[tuple[str, str]] = []  # (dim_id, stage)
    for stage in stages:
        for dim_id in STAGE_DIMENSION_MAP.get(stage, []):
            key = f"{dim_id}@{stage}"
            if key not in seen_dim_ids:
                seen_dim_ids.add(key)
                dim_tasks.append((dim_id, stage))

    for dim_id, stage in dim_tasks:
        dimension = dim_index.get(dim_id)
        if dimension is None:
            result.errors.append(f"unknown dimension: {dim_id}")
            continue

        dim_result = evaluate_one_dimension(
            dimension=dimension,
            case_data=case_data,
            stage=stage,
            config=config,
            verbose=verbose,
        )

        if dim_result.error:
            print(
                f"  [{dimension['dimension_name_zh']}] ERROR: {dim_result.error}"
            )

        # If a dimension is evaluated at multiple stages, use the latest stage's result
        stage_order = {
            "scenario_understanding": 0,
            "empathetic_planning": 1,
            "empathetic_actions": 2,
        }
        existing = result.dimension_scores.get(dim_id)
        if existing is None or stage_order.get(stage, -1) > stage_order.get(
            "empathetic_actions", -1
        ):
            result.dimension_scores[dim_id] = dim_result

        if verbose and dim_result.score is not None:
            print(
                f"  [{dimension['dimension_name_zh']}] score={dim_result.score}"
            )

        # Small delay between dimensions to avoid rate limiting
        time.sleep(0.3)

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="EmpathyAgent 8-dimension evaluation framework for PURE-JADE",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/empathy_evaluator.py --mode api
  python scripts/empathy_evaluator.py --mode api --cases examples/eval-test-cases-v0.1.json
  python scripts/empathy_evaluator.py --mode api --stage empathetic_actions
  python scripts/empathy_evaluator.py --mode api --model deepseek-chat --verbose
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["api", "rules"],
        default="api",
        help="Evaluation mode: 'api' uses LLM evaluator; 'rules' mode not yet implemented",
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES,
        help=f"Path to evaluation test cases JSON (default: {DEFAULT_CASES})",
    )
    parser.add_argument(
        "--dimensions",
        type=Path,
        default=DEFAULT_DIMENSIONS,
        help=f"Path to evaluation dimensions config (default: {DEFAULT_DIMENSIONS})",
    )
    parser.add_argument(
        "--stage",
        choices=["scenario_understanding", "empathetic_planning", "empathetic_actions", "multi_turn_state_update"],
        default=None,
        help="Evaluate only a specific stage (default: all stages)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output report path (default: reports/evaluation/<timestamp>.json)",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help=f"Path to .env file (default: {DEFAULT_ENV_FILE})",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default=None,
        help="API base URL (overrides PURE_JADE_API_URL and default)",
    )
    parser.add_argument(
        "--api-model",
        type=str,
        default=None,
        help="API model name (overrides PURE_JADE_API_MODEL and default)",
    )
    parser.add_argument(
        "--api-temperature",
        type=float,
        default=None,
        help="API temperature (default: 0.0 for evaluation consistency)",
    )
    parser.add_argument(
        "--api-timeout",
        type=int,
        default=None,
        help="API timeout seconds (default: 120)",
    )
    parser.add_argument(
        "--api-max-retries",
        type=int,
        default=None,
        help="API max retries on failure (default: 1)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Print detailed progress",
    )
    parser.add_argument(
        "--format",
        choices=["full", "v0.1", "v0.2", "both"],
        default="full",
        help="Output format: 'full' = 8-dim report, 'v0.1' = PURE-JADE v0.1 cards, 'v0.2' = v0.2 cards (with multi-turn fields), 'both' = v0.1 + v0.2 (default: full)",
    )
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    # Load config
    if not args.dimensions.exists():
        print(f"ERROR: dimensions config not found: {args.dimensions}")
        sys.exit(1)
    dimensions_config = load_json(args.dimensions)

    if not args.cases.exists():
        print(f"ERROR: test cases not found: {args.cases}")
        sys.exit(1)
    cases_doc = load_json(args.cases)

    cases = cases_doc.get("cases") if isinstance(cases_doc, dict) else cases_doc
    if not isinstance(cases, list):
        print("ERROR: test cases must be a JSON array or object with 'cases' array")
        sys.exit(1)

    # Load API config
    api_config, api_errors = load_api_config(args)
    if api_errors:
        for err in api_errors:
            print(f"CONFIG ERROR: {err}")
        print("Set PURE_JADE_API_KEY and PURE_JADE_API_MODEL in .env or environment")
        sys.exit(1)
    assert api_config is not None

    print(f"Evaluator: {EVALUATOR_TYPE}")
    print(f"Model: {api_config.model}")
    print(f"API URL: {api_config.url}")
    print(f"Cases: {len(cases)}")
    print(f"Stage(s): {args.stage or 'all'}")
    print()

    # Evaluate each case — keep CaseEvalResult objects for v0.2 mapping
    all_results: list[dict[str, Any]] = []
    all_case_results: list[CaseEvalResult] = []  # raw objects for v0.2
    all_v0_1_cards: list[dict[str, Any]] = []
    total_start = time.time()

    for i, case in enumerate(cases):
        case_start = time.time()
        result = evaluate_case(
            case_data=case,
            dimensions_config=dimensions_config,
            config=api_config,
            stage_filter=args.stage,
            verbose=args.verbose,
        )
        elapsed = time.time() - case_start

        all_case_results.append(result)
        card = result.to_evaluation_card(api_config)
        all_results.append(card)

        v0_1_card = result.map_to_v0_1_card(api_config)
        all_v0_1_cards.append(v0_1_card)

        print(
            f"[{i + 1}/{len(cases)}] {result.conversation_id} "
            f"overall_8d={result.overall_score} "
            f"overall_v0_1={v0_1_card['overall_score']} "
            f"({elapsed:.1f}s)"
        )

    total_elapsed = time.time() - total_start

    # Build report based on format
    fmt = args.format
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    if fmt in ("full", "both"):
        report: dict[str, Any] = {
            "report_type": "empathy_agent_8d_evaluation",
            "schema_version": SCHEMA_VERSION,
            "evaluator_type": EVALUATOR_TYPE,
            "evaluator_model": api_config.model,
            "cases_file": str(args.cases),
            "stage_filter": args.stage,
            "total_cases": len(cases),
            "total_duration_seconds": round(total_elapsed, 1),
            "results": all_results,
        }
        overall_scores = [
            r.get("overall_score")
            for r in all_results
            if r.get("overall_score") is not None
        ]
        if overall_scores:
            report["summary"] = {
                "mean_overall_score": round(sum(overall_scores) / len(overall_scores), 2),
                "min_overall_score": min(overall_scores),
                "max_overall_score": max(overall_scores),
            }
        output_path = args.output or (DEFAULT_REPORT_DIR / f"eval_8d_{timestamp}.json")
        write_json(output_path, report)
        print(f"\n[8-dim report] {output_path}")
        if "summary" in report:
            s = report["summary"]
            print(f"Summary (1-10): mean={s['mean_overall_score']}, min={s['min_overall_score']}, max={s['max_overall_score']}")

    if fmt in ("v0.1", "both"):
        v0_1_report: dict[str, Any] = {
            "report_type": "pure_jade_v0_1_evaluation",
            "schema_version": "0.1",
            "evaluator_type": "llm_initial",
            "evaluator_model": api_config.model,
            "cases_file": str(args.cases),
            "stage_filter": args.stage,
            "total_cases": len(cases),
            "total_duration_seconds": round(total_elapsed, 1),
            "evaluation_cards": all_v0_1_cards,
        }
        v0_1_scores = [c["overall_score"] for c in all_v0_1_cards]
        if v0_1_scores:
            v0_1_report["summary"] = {
                "mean_overall_score": round(sum(v0_1_scores) / len(v0_1_scores), 2),
                "min_overall_score": min(v0_1_scores),
                "max_overall_score": max(v0_1_scores),
            }
        v0_1_path = args.output or (DEFAULT_REPORT_DIR / f"eval_v0_1_{timestamp}.json")
        if args.output and fmt == "v0.1":
            v0_1_path = args.output
        write_json(v0_1_path, v0_1_report)
        print(f"[v0.1 report] {v0_1_path}")
        if v0_1_scores:
            s = v0_1_report["summary"]
            print(f"v0.1 (1-5): mean={s['mean_overall_score']}, min={s['min_overall_score']}, max={s['max_overall_score']}")

    if fmt in ("v0.2", "both"):
        all_v0_2_cards = [r.map_to_v0_2_card(api_config) for r in all_case_results]
        v0_2_report: dict[str, Any] = {
            "report_type": "pure_jade_v0_2_evaluation",
            "schema_version": "0.2",
            "evaluator_type": "llm_initial",
            "evaluator_model": api_config.model,
            "cases_file": str(args.cases),
            "stage_filter": args.stage,
            "total_cases": len(cases),
            "total_duration_seconds": round(total_elapsed, 1),
            "evaluation_cards": all_v0_2_cards,
        }
        v0_2_scores = [c["overall_score"] for c in all_v0_2_cards]
        if v0_2_scores:
            v0_2_report["summary"] = {
                "mean_overall_score": round(sum(v0_2_scores) / len(v0_2_scores), 2),
                "min_overall_score": min(v0_2_scores),
                "max_overall_score": max(v0_2_scores),
            }
        v0_2_path = args.output or (DEFAULT_REPORT_DIR / f"eval_v0_2_{timestamp}.json")
        if args.output and fmt == "v0.2":
            v0_2_path = args.output
        write_json(v0_2_path, v0_2_report)
        print(f"[v0.2 report] {v0_2_path}")
        if v0_2_scores:
            s = v0_2_report["summary"]
            print(f"v0.2 (1-5): mean={s['mean_overall_score']}, min={s['min_overall_score']}, max={s['max_overall_score']}")

    print(f"Total time: {total_elapsed:.1f}s")


if __name__ == "__main__":
    main()
