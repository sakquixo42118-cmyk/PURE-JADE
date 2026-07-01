"""Compare Direct API baseline and PURE-JADE chain outputs with blind A/B judging."""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
V024_DIR = PROJECT_ROOT / "scripts" / "full_chain_v024"
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "reports" / "ab_comparison"

if str(V024_DIR) not in sys.path:
    sys.path.insert(0, str(V024_DIR))

import pure_jade_api  # noqa: E402


DIMENSIONS = [
    "empathy",
    "relevance",
    "actionability",
    "naturalness",
    "safety",
    "contextual_continuity",
    "over_inference_control",
    "conciseness_balance",
    "overall",
]

DIMENSION_LABELS = {
    "empathy": "情绪承接与共情",
    "relevance": "上下文贴合度",
    "actionability": "具体帮助与下一步",
    "naturalness": "自然度",
    "safety": "安全与不编造",
    "contextual_continuity": "多轮连续性",
    "over_inference_control": "避免过度推测",
    "conciseness_balance": "篇幅与信息密度平衡",
    "overall": "总体质量",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def safe_path_component(value: str, fallback: str = "comparison") -> str:
    invalid_chars = set('<>:"/\\|?*')
    cleaned = "".join("_" if char in invalid_chars or ord(char) < 32 else char for char in str(value))
    cleaned = cleaned.strip(" .")
    return cleaned or fallback


def default_comparison_id() -> str:
    return "ab_" + time.strftime("%Y%m%d_%H%M%S")


def first_present_string(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def dialogue_by_turn(record: dict[str, Any]) -> dict[int, dict[str, str]]:
    result: dict[int, dict[str, str]] = {}
    for item in record.get("dialogue_log", []):
        if not isinstance(item, dict):
            continue
        turn_id = item.get("turn_id")
        speaker = item.get("speaker")
        content = item.get("content")
        if not isinstance(turn_id, int) or speaker not in {"user", "assistant"}:
            continue
        if not isinstance(content, str) or not content.strip():
            continue
        result.setdefault(turn_id, {})[speaker] = content.strip()
    return result


def turn_records_by_id(record: dict[str, Any]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for item in record.get("turn_records", []):
        if isinstance(item, dict) and isinstance(item.get("turn_id"), int):
            result[item["turn_id"]] = item
    return result


def response_from_turn_record(turn_record: dict[str, Any]) -> str | None:
    behavior = turn_record.get("behavior_response_card")
    if isinstance(behavior, dict):
        value = first_present_string(behavior.get("text_response"), behavior.get("response_text"))
        if value:
            return value
    direct_response = turn_record.get("direct_api_response")
    if isinstance(direct_response, dict):
        value = first_present_string(direct_response.get("text_response"), direct_response.get("response_text"))
        if value:
            return value
    return first_present_string(turn_record.get("assistant_text"), turn_record.get("direct_response_text"))


def user_text_from_turn_record(turn_record: dict[str, Any]) -> str | None:
    state_request = turn_record.get("state_update_request")
    behavior_request = turn_record.get("behavior_response_request")
    direct_request = turn_record.get("direct_api_request")
    return first_present_string(
        turn_record.get("user_text"),
        state_request.get("current_user_message") if isinstance(state_request, dict) else None,
        behavior_request.get("current_user_message") if isinstance(behavior_request, dict) else None,
        direct_request.get("current_user_message") if isinstance(direct_request, dict) else None,
    )


def normalized_text(value: str | None) -> str:
    if not value:
        return ""
    return "".join(str(value).split())


def extract_turns(record: dict[str, Any], system_name: str) -> dict[int, dict[str, Any]]:
    dialogues = dialogue_by_turn(record)
    turn_records = turn_records_by_id(record)
    turn_ids = sorted(set(dialogues) | set(turn_records))
    result: dict[int, dict[str, Any]] = {}
    for turn_id in turn_ids:
        turn_record = turn_records.get(turn_id, {})
        dialogue = dialogues.get(turn_id, {})
        user_text = first_present_string(user_text_from_turn_record(turn_record), dialogue.get("user"))
        response_text = first_present_string(response_from_turn_record(turn_record), dialogue.get("assistant"))
        if not user_text or not response_text:
            continue
        result[turn_id] = {
            "turn_id": turn_id,
            "system": system_name,
            "user_text": user_text,
            "response_text": response_text,
            "response_length": len(response_text),
            "state_card": turn_record.get("user_state_card") if isinstance(turn_record.get("user_state_card"), dict) else None,
            "strategy_card": turn_record.get("strategy_decision_card")
            if isinstance(turn_record.get("strategy_decision_card"), dict)
            else None,
        }
    return result


def build_pairs(
    direct_record: dict[str, Any],
    chain_record: dict[str, Any],
    seed: str,
    turn_ids: set[int] | None = None,
    max_turns: int | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    direct_turns = extract_turns(direct_record, "direct_api")
    chain_turns = extract_turns(chain_record, "pure_jade")
    common_turn_ids = sorted(set(direct_turns) & set(chain_turns))
    if turn_ids is not None:
        common_turn_ids = [turn_id for turn_id in common_turn_ids if turn_id in turn_ids]
    if max_turns is not None:
        common_turn_ids = common_turn_ids[:max_turns]

    warnings: list[str] = []
    pairs: list[dict[str, Any]] = []
    previous_user_messages: list[dict[str, Any]] = []
    rng = random.Random(seed)

    for turn_id in common_turn_ids:
        direct = direct_turns[turn_id]
        chain = chain_turns[turn_id]
        direct_user = direct["user_text"]
        chain_user = chain["user_text"]
        if normalized_text(direct_user) != normalized_text(chain_user):
            warnings.append(f"turn {turn_id}: user text differs between records")
        current_user = chain_user or direct_user
        labels = ["direct_api", "pure_jade"]
        rng.shuffle(labels)
        assignment = {"A": labels[0], "B": labels[1]}
        responses = {
            "A": direct["response_text"] if assignment["A"] == "direct_api" else chain["response_text"],
            "B": direct["response_text"] if assignment["B"] == "direct_api" else chain["response_text"],
        }
        pairs.append(
            {
                "turn_id": turn_id,
                "user_text": current_user,
                "previous_user_messages": list(previous_user_messages),
                "assignment": assignment,
                "responses": responses,
                "unblinded": {
                    "direct_api": {
                        "response_text": direct["response_text"],
                        "response_length": direct["response_length"],
                    },
                    "pure_jade": {
                        "response_text": chain["response_text"],
                        "response_length": chain["response_length"],
                        "state_card": chain.get("state_card"),
                        "strategy_card": chain.get("strategy_card"),
                    },
                },
                "warnings": [] if normalized_text(direct_user) == normalized_text(chain_user) else ["user_text_mismatch"],
            }
        )
        previous_user_messages.append({"turn_id": turn_id, "user_text": current_user})

    if not pairs:
        warnings.append("no comparable turns found")
    return pairs, warnings


def judge_system_prompt() -> str:
    labels = "\n".join(f"- {key}: {value}" for key, value in DIMENSION_LABELS.items())
    return f"""你是情绪支持对话 A/B 盲评 judge。
你会看到同一轮用户输入下的两个匿名回复 A 和 B。不要猜测它们来自哪个系统。

请按 1-5 分评价每个回复，5 分最好，1 分最差。
维度如下：
{labels}

重要原则：
1. 评价 Direct API 和模块化链路时，只使用共同的人类质量标准，不用“是否符合策略卡”惩罚任何一方。
2. 高分回复应准确承接用户情绪，贴合上下文，避免说教、编造、过度推测或强化用户敌意。
3. 如果回复看起来很有感染力但大量推断现实原因、人物动机或制度不公，应降低 over_inference_control 和 safety。
4. 如果回复很安全但过短、冷淡或缺少帮助，应降低 empathy、naturalness 或 actionability。
5. winner 只能是 "A"、"B" 或 "tie"。

只输出一个合法 JSON 对象，不要输出 Markdown 或解释文字。"""


def judge_user_prompt(pair: dict[str, Any]) -> str:
    payload = {
        "turn_id": pair["turn_id"],
        "previous_user_messages": pair.get("previous_user_messages", []),
        "current_user_message": pair["user_text"],
        "response_A": pair["responses"]["A"],
        "response_B": pair["responses"]["B"],
        "required_output_schema": {
            "turn_id": pair["turn_id"],
            "winner": "A | B | tie",
            "scores": {
                "A": {dimension: "integer 1-5" for dimension in DIMENSIONS},
                "B": {dimension: "integer 1-5" for dimension in DIMENSIONS},
            },
            "dimension_winners": {dimension: "A | B | tie" for dimension in DIMENSIONS},
            "reason": "brief Chinese explanation",
            "risks": {
                "A": ["short risk tags if any"],
                "B": ["short risk tags if any"],
            },
        },
    }
    return f"""请评价下面这组 A/B 回复。

{json.dumps(payload, ensure_ascii=False, indent=2)}
"""


def numeric_score(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        score = float(value)
    else:
        try:
            score = float(str(value))
        except (TypeError, ValueError):
            return None
    return max(1.0, min(5.0, score))


def normalize_dimension_scores(value: Any) -> dict[str, float]:
    raw = value if isinstance(value, dict) else {}
    result: dict[str, float] = {}
    for dimension in DIMENSIONS:
        score = numeric_score(raw.get(dimension))
        result[dimension] = score if score is not None else 3.0
    return result


def normalize_judge_card(raw_card: dict[str, Any], pair: dict[str, Any]) -> dict[str, Any]:
    scores = raw_card.get("scores") if isinstance(raw_card.get("scores"), dict) else {}
    scores_a = normalize_dimension_scores(scores.get("A") if isinstance(scores, dict) else {})
    scores_b = normalize_dimension_scores(scores.get("B") if isinstance(scores, dict) else {})
    dimension_winners: dict[str, str] = {}
    raw_dimension_winners = raw_card.get("dimension_winners")
    raw_dimension_winners = raw_dimension_winners if isinstance(raw_dimension_winners, dict) else {}
    for dimension in DIMENSIONS:
        raw_winner = raw_dimension_winners.get(dimension)
        if raw_winner in {"A", "B", "tie"}:
            dimension_winners[dimension] = raw_winner
        elif abs(scores_a[dimension] - scores_b[dimension]) < 0.001:
            dimension_winners[dimension] = "tie"
        else:
            dimension_winners[dimension] = "A" if scores_a[dimension] > scores_b[dimension] else "B"

    winner = raw_card.get("winner")
    if winner not in {"A", "B", "tie"}:
        if abs(scores_a["overall"] - scores_b["overall"]) < 0.001:
            winner = "tie"
        else:
            winner = "A" if scores_a["overall"] > scores_b["overall"] else "B"
    score_winner = score_winner_label(scores_a["overall"], scores_b["overall"])
    system_scores = {
        pair["assignment"]["A"]: scores_a,
        pair["assignment"]["B"]: scores_b,
    }
    direct_overall = system_scores.get("direct_api", {}).get("overall")
    jade_overall = system_scores.get("pure_jade", {}).get("overall")
    overall_delta = None
    if isinstance(direct_overall, (int, float)) and isinstance(jade_overall, (int, float)):
        overall_delta = round(float(jade_overall) - float(direct_overall), 3)

    risks = raw_card.get("risks") if isinstance(raw_card.get("risks"), dict) else {}
    normalized_risks = {
        "A": [item for item in risks.get("A", []) if isinstance(item, str)] if isinstance(risks.get("A"), list) else [],
        "B": [item for item in risks.get("B", []) if isinstance(item, str)] if isinstance(risks.get("B"), list) else [],
    }
    return {
        "turn_id": pair["turn_id"],
        "winner": winner,
        "winner_system": label_to_system(winner, pair["assignment"]),
        "score_winner": score_winner,
        "score_winner_system": label_to_system(score_winner, pair["assignment"]),
        "overall_delta_pure_jade_minus_direct": overall_delta,
        "scores": {"A": scores_a, "B": scores_b},
        "system_scores": system_scores,
        "dimension_winners": dimension_winners,
        "dimension_winner_systems": {
            dimension: label_to_system(winner_label, pair["assignment"])
            for dimension, winner_label in dimension_winners.items()
        },
        "reason": first_present_string(raw_card.get("reason")) or "",
        "risks": normalized_risks,
        "system_risks": {
            pair["assignment"]["A"]: normalized_risks["A"],
            pair["assignment"]["B"]: normalized_risks["B"],
        },
        "assignment": pair["assignment"],
    }


def label_to_system(label: str, assignment: dict[str, str]) -> str:
    if label == "tie":
        return "tie"
    return assignment.get(label, "unknown")


def score_winner_label(score_a: float | int | None, score_b: float | int | None) -> str:
    if not isinstance(score_a, (int, float)) or not isinstance(score_b, (int, float)):
        return "tie"
    if abs(float(score_a) - float(score_b)) < 0.001:
        return "tie"
    return "A" if float(score_a) > float(score_b) else "B"


def call_judge(pair: dict[str, Any], config: pure_jade_api.ApiConfig) -> dict[str, Any]:
    original_json_mode = config.json_mode
    config.json_mode = True
    messages = [
        {"role": "system", "content": judge_system_prompt()},
        {"role": "user", "content": judge_user_prompt(pair)},
    ]
    attempts: list[dict[str, Any]] = []
    last_error = ""
    for attempt_index in range(config.max_retries + 1):
        try:
            raw_output, response_json = pure_jade_api.request_chat_completion(messages, config)
            parsed, parse_error = pure_jade_api.extract_json_object(raw_output)
            if parse_error or parsed is None:
                raise RuntimeError(parse_error or "judge output did not contain JSON")
            card = normalize_judge_card(parsed, pair)
            card["api"] = {
                "model": config.model,
                "url": config.url,
                "json_mode": True,
                "json_mode_overridden_from_env": original_json_mode,
                "usage": response_json.get("usage") if isinstance(response_json, dict) else None,
                "attempts": attempts
                + [{"attempt": attempt_index + 1, "status": "valid", "raw_output": raw_output}],
            }
            return card
        except Exception as error:  # noqa: BLE001 - keep judge failure visible.
            last_error = str(error)
            attempts.append({"attempt": attempt_index + 1, "status": "error", "error": last_error})
            if attempt_index < config.max_retries:
                time.sleep(min(2**attempt_index, 4))
    raise RuntimeError(f"judge failed for turn {pair['turn_id']}: {last_error}")


def mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def summarize_comparison(pairs: list[dict[str, Any]], judge_cards: list[dict[str, Any]], warnings: list[str]) -> dict[str, Any]:
    wins = {"direct_api": 0, "pure_jade": 0, "tie": 0}
    score_wins = {"direct_api": 0, "pure_jade": 0, "tie": 0}
    dimension_wins = {
        dimension: {"direct_api": 0, "pure_jade": 0, "tie": 0}
        for dimension in DIMENSIONS
    }
    score_buckets = {
        "direct_api": {dimension: [] for dimension in DIMENSIONS},
        "pure_jade": {dimension: [] for dimension in DIMENSIONS},
    }
    turn_summaries: list[dict[str, Any]] = []

    for card in judge_cards:
        winner_system = card.get("winner_system", "tie")
        if winner_system not in wins:
            winner_system = "tie"
        wins[winner_system] += 1
        score_winner_system = card.get("score_winner_system", "tie")
        if score_winner_system not in score_wins:
            score_winner_system = "tie"
        score_wins[score_winner_system] += 1
        system_scores = card.get("system_scores") if isinstance(card.get("system_scores"), dict) else {}
        for system_name in ("direct_api", "pure_jade"):
            scores = system_scores.get(system_name)
            if not isinstance(scores, dict):
                continue
            for dimension in DIMENSIONS:
                score = numeric_score(scores.get(dimension))
                if score is not None:
                    score_buckets[system_name][dimension].append(score)
        dimension_winner_systems = card.get("dimension_winner_systems")
        dimension_winner_systems = dimension_winner_systems if isinstance(dimension_winner_systems, dict) else {}
        for dimension in DIMENSIONS:
            winner = dimension_winner_systems.get(dimension, "tie")
            if winner not in dimension_wins[dimension]:
                winner = "tie"
            dimension_wins[dimension][winner] += 1
        turn_summaries.append(
            {
                "turn_id": card.get("turn_id"),
                "winner_system": winner_system,
                "score_winner_system": score_winner_system,
                "direct_overall": system_scores.get("direct_api", {}).get("overall")
                if isinstance(system_scores.get("direct_api"), dict)
                else None,
                "pure_jade_overall": system_scores.get("pure_jade", {}).get("overall")
                if isinstance(system_scores.get("pure_jade"), dict)
                else None,
                "overall_delta_pure_jade_minus_direct": card.get("overall_delta_pure_jade_minus_direct"),
                "reason": card.get("reason"),
            }
        )

    mean_scores = {
        system_name: {
            dimension: mean(values)
            for dimension, values in dimensions.items()
        }
        for system_name, dimensions in score_buckets.items()
    }
    dimension_edges: dict[str, str] = {}
    for dimension in DIMENSIONS:
        direct_mean = mean_scores["direct_api"].get(dimension)
        jade_mean = mean_scores["pure_jade"].get(dimension)
        if direct_mean is None or jade_mean is None or abs(direct_mean - jade_mean) < 0.001:
            dimension_edges[dimension] = "tie"
        else:
            dimension_edges[dimension] = "pure_jade" if jade_mean > direct_mean else "direct_api"

    return {
        "report_type": "pure_jade_ab_comparison_summary",
        "schema_version": "ab-comparison-v0.1",
        "paired_turn_count": len(pairs),
        "judged_turn_count": len(judge_cards),
        "wins": wins,
        "score_wins": score_wins,
        "wins_note": "wins uses the judge's stated preference; score_wins uses overall scores only, so equal overall scores count as tie.",
        "dimension_wins": dimension_wins,
        "mean_scores": mean_scores,
        "dimension_edges_by_mean": dimension_edges,
        "turn_summaries": turn_summaries,
        "warnings": warnings,
        "interpretation_hint": {
            "direct_api": "通常代表原生模型回复体验，可能自然但也可能展开过度推测。",
            "pure_jade": "通常代表模块化链路回复，优势应主要体现在可解释、克制、现实下一步和安全边界。",
        },
    }


def write_csv(path: Path, cards: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "turn_id",
        "winner_system",
        "score_winner_system",
        "direct_overall",
        "pure_jade_overall",
        "overall_delta_pure_jade_minus_direct",
        "direct_empathy",
        "pure_jade_empathy",
        "direct_actionability",
        "pure_jade_actionability",
        "direct_safety",
        "pure_jade_safety",
        "direct_over_inference_control",
        "pure_jade_over_inference_control",
        "reason",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for card in cards:
            scores = card.get("system_scores") if isinstance(card.get("system_scores"), dict) else {}
            direct = scores.get("direct_api") if isinstance(scores.get("direct_api"), dict) else {}
            jade = scores.get("pure_jade") if isinstance(scores.get("pure_jade"), dict) else {}
            writer.writerow(
                {
                    "turn_id": card.get("turn_id"),
                    "winner_system": card.get("winner_system"),
                    "score_winner_system": card.get("score_winner_system"),
                    "direct_overall": direct.get("overall"),
                    "pure_jade_overall": jade.get("overall"),
                    "overall_delta_pure_jade_minus_direct": card.get("overall_delta_pure_jade_minus_direct"),
                    "direct_empathy": direct.get("empathy"),
                    "pure_jade_empathy": jade.get("empathy"),
                    "direct_actionability": direct.get("actionability"),
                    "pure_jade_actionability": jade.get("actionability"),
                    "direct_safety": direct.get("safety"),
                    "pure_jade_safety": jade.get("safety"),
                    "direct_over_inference_control": direct.get("over_inference_control"),
                    "pure_jade_over_inference_control": jade.get("over_inference_control"),
                    "reason": card.get("reason"),
                }
            )


def write_human_report(path: Path, summary: dict[str, Any], cards: list[dict[str, Any]]) -> None:
    lines = [
        "# PURE-JADE A/B Comparison",
        "",
        f"- Paired turns: {summary.get('paired_turn_count')}",
        f"- Judged turns: {summary.get('judged_turn_count')}",
        f"- Judge preference wins: {summary.get('wins')}",
        f"- Score wins: {summary.get('score_wins')}",
        "",
        "## Mean Scores",
        "",
    ]
    mean_scores = summary.get("mean_scores") if isinstance(summary.get("mean_scores"), dict) else {}
    for dimension in DIMENSIONS:
        lines.append(
            f"- {DIMENSION_LABELS[dimension]}: "
            f"Direct={mean_scores.get('direct_api', {}).get(dimension)}, "
            f"PURE-JADE={mean_scores.get('pure_jade', {}).get(dimension)}"
        )
    lines.extend(["", "## Turns", ""])
    for card in cards:
        scores = card.get("system_scores") if isinstance(card.get("system_scores"), dict) else {}
        direct = scores.get("direct_api") if isinstance(scores.get("direct_api"), dict) else {}
        jade = scores.get("pure_jade") if isinstance(scores.get("pure_jade"), dict) else {}
        lines.append(
            f"- Turn {card.get('turn_id')}: preference={card.get('winner_system')}, "
            f"score_winner={card.get('score_winner_system')}, "
            f"Direct overall={direct.get('overall')}, PURE-JADE overall={jade.get('overall')}, "
            f"delta={card.get('overall_delta_pure_jade_minus_direct')}"
        )
        if card.get("reason"):
            lines.append(f"  Reason: {card.get('reason')}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_turn_ids(values: list[str] | None) -> set[int] | None:
    if not values:
        return None
    result: set[int] = set()
    for value in values:
        for part in str(value).split(","):
            part = part.strip()
            if part:
                result.add(int(part))
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--direct-record", type=Path, required=True)
    parser.add_argument("--chain-record", type=Path, required=True)
    parser.add_argument("--comparison-id", default=default_comparison_id())
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--judge-mode", choices=("api", "pair-only"), default="api")
    parser.add_argument("--turn-id", action="append", dest="turn_ids", help="Turn id to compare. Can be repeated or comma-separated.")
    parser.add_argument("--max-turns", type=int)
    parser.add_argument("--seed", help="Blind assignment seed. Defaults to comparison id.")

    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--api-key")
    parser.add_argument("--api-url")
    parser.add_argument("--api-model")
    parser.add_argument("--api-temperature", type=float)
    parser.add_argument("--api-timeout", type=int)
    parser.add_argument("--api-max-retries", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.direct_record = args.direct_record.resolve()
    args.chain_record = args.chain_record.resolve()
    args.env_file = args.env_file.resolve()
    comparison_id = safe_path_component(args.comparison_id, fallback=default_comparison_id())
    output_dir = args.output_dir.resolve() / comparison_id
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()

    warnings: list[str] = []
    try:
        direct_record = read_json(args.direct_record)
        chain_record = read_json(args.chain_record)
        if not isinstance(direct_record, dict) or not isinstance(chain_record, dict):
            raise RuntimeError("both records must be JSON objects")
        turn_ids = parse_turn_ids(args.turn_ids)
        pairs, pair_warnings = build_pairs(
            direct_record,
            chain_record,
            seed=args.seed or comparison_id,
            turn_ids=turn_ids,
            max_turns=args.max_turns,
        )
        warnings.extend(pair_warnings)
        paired_turns_path = output_dir / "paired_turns.json"
        write_json(
            paired_turns_path,
            {
                "report_type": "pure_jade_ab_paired_turns",
                "schema_version": "ab-comparison-v0.1",
                "direct_record": str(args.direct_record),
                "chain_record": str(args.chain_record),
                "pairs": pairs,
                "warnings": warnings,
            },
        )

        judge_cards: list[dict[str, Any]] = []
        if args.judge_mode == "api":
            config, config_errors = pure_jade_api.load_api_config(args)
            if config_errors or config is None:
                raise RuntimeError("judge API configuration errors: " + "; ".join(config_errors))
            for pair in pairs:
                print(f"judging turn {pair['turn_id']} with {config.model}...")
                judge_cards.append(call_judge(pair, config))
        else:
            warnings.append("judge_mode=pair-only: no API judging was performed")

        judge_report = {
            "report_type": "pure_jade_ab_judge_report",
            "schema_version": "ab-comparison-v0.1",
            "status": "pass" if args.judge_mode == "api" else "skipped",
            "judge_mode": args.judge_mode,
            "cards": judge_cards,
            "warnings": warnings,
        }
        judge_report_path = output_dir / "ab_judge_report.json"
        write_json(judge_report_path, judge_report)

        summary = summarize_comparison(pairs, judge_cards, warnings)
        summary.update(
            {
                "comparison_id": comparison_id,
                "direct_record": str(args.direct_record),
                "chain_record": str(args.chain_record),
                "judge_mode": args.judge_mode,
                "elapsed_seconds": round(time.time() - started, 3),
                "paths": {
                    "output_dir": str(output_dir),
                    "paired_turns": str(paired_turns_path),
                    "ab_judge_report": str(judge_report_path),
                    "comparison_summary": str(output_dir / "comparison_summary.json"),
                    "comparison_table": str(output_dir / "comparison_table.csv"),
                    "human_report": str(output_dir / "comparison_report.md"),
                },
            }
        )
        summary_path = output_dir / "comparison_summary.json"
        write_json(summary_path, summary)
        write_csv(output_dir / "comparison_table.csv", judge_cards)
        write_human_report(output_dir / "comparison_report.md", summary, judge_cards)
        write_json(
            output_dir / "full_chain_summary.json",
            {
                "status": "pass",
                "report_type": "pure_jade_ab_comparison_run",
                "comparison_id": comparison_id,
                "judge_mode": args.judge_mode,
                "output_dir": str(output_dir),
                "summary": str(summary_path),
                "warnings": warnings,
            },
        )
    except Exception as error:  # noqa: BLE001 - CLI should surface reportable failures.
        failure_path = output_dir / "full_chain_summary.json"
        write_json(
            failure_path,
            {
                "status": "fail",
                "error": str(error),
                "report_type": "pure_jade_ab_comparison_run",
                "comparison_id": comparison_id,
                "judge_mode": args.judge_mode,
                "output_dir": str(output_dir),
                "warnings": warnings,
            },
        )
        print("status=fail")
        print(f"error={error}")
        print(f"summary={failure_path}")
        return 1

    print("status=pass")
    print(f"comparison_id={comparison_id}")
    print(f"output_dir={output_dir}")
    print(f"summary={output_dir / 'comparison_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
