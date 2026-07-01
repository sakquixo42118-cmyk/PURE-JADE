"""PURE-JADE v0.2.3 evaluation runner.

Default mode is fast diagnostic evaluation: one judge API call per case.
The old EmpathyAgent-style per-dimension evaluator is still available through
``--eval-mode full`` for final reports or small offline experiments.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from diagnostic_evaluator import (  # noqa: E402
    DIAGNOSTIC_SCHEMA_VERSION,
    EVALUATOR_TYPE as FAST_EVALUATOR_TYPE,
    evaluate_case_fast,
)
from empathy_evaluator import (  # noqa: E402
    DEFAULT_CASES,
    DEFAULT_DIMENSIONS,
    DEFAULT_ENV_FILE,
    DEFAULT_REPORT_DIR,
    EVALUATOR_TYPE as FULL_EVALUATOR_TYPE,
    evaluate_case,
    load_api_config,
    load_json,
    write_json,
)


def check_cards_complete(case: dict[str, Any]) -> tuple[bool, list[str]]:
    missing = []
    if not case.get("user_state_card"):
        missing.append("user_state_card")
    if not case.get("strategy_decision_card"):
        missing.append("strategy_decision_card")
    if not case.get("behavior_response_card"):
        missing.append("behavior_response_card")
    if not case.get("dialogue"):
        missing.append("dialogue")
    return len(missing) == 0, missing


def load_ready_cases(cases_path: Path) -> list[dict[str, Any]]:
    if not cases_path.exists():
        raise SystemExit(f"ERROR: test cases not found: {cases_path}")

    cases_doc = load_json(cases_path)
    cases = cases_doc.get("cases") if isinstance(cases_doc, dict) else cases_doc
    if not isinstance(cases, list):
        raise SystemExit("ERROR: test cases must be a JSON array or object with 'cases' array")

    ready_cases = []
    need_pipeline = []
    for case in cases:
        if not isinstance(case, dict):
            continue
        complete, missing = check_cards_complete(case)
        if complete:
            ready_cases.append(case)
        else:
            need_pipeline.append((case, missing))

    print(f"Cases: {len(cases)} total")
    print(f"  Ready for evaluation: {len(ready_cases)}")
    print(f"  Need pipeline run: {len(need_pipeline)}")
    if need_pipeline:
        for case, missing in need_pipeline:
            cid = case.get("conversation_id", "unknown")
            print(f"    - {cid}: missing {missing}")
        print()

    if not ready_cases:
        raise SystemExit("No cases ready for evaluation. Exiting.")
    return ready_cases


def summarize_cards(cards: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [
        card.get("overall_score")
        for card in cards
        if isinstance(card.get("overall_score"), (int, float))
    ]
    if not scores:
        return {}
    review_needed = sum(1 for card in cards if card.get("review_needed"))
    failure_counts: dict[str, int] = {}
    for card in cards:
        tags = card.get("failure_tags")
        if not isinstance(tags, list):
            tags = card.get("violations")
        if not isinstance(tags, list):
            continue
        for tag in tags:
            tag_text = str(tag)
            failure_counts[tag_text] = failure_counts.get(tag_text, 0) + 1
    return {
        "mean_overall_score": round(sum(scores) / len(scores), 2),
        "min_overall_score": min(scores),
        "max_overall_score": max(scores),
        "review_needed_count": review_needed,
        "failure_tag_counts": failure_counts,
    }


def run_fast_evaluation(args: argparse.Namespace, cases: list[dict[str, Any]], api_config: Any) -> dict[str, Any]:
    cards: list[dict[str, Any]] = []
    total_start = time.time()

    for i, case in enumerate(cases):
        case_start = time.time()
        card = evaluate_case_fast(case, api_config, verbose=args.verbose)
        elapsed = time.time() - case_start
        cards.append(card)
        print(
            f"[{i + 1}/{len(cases)}] {card['conversation_id']} "
            f"diagnostic={card['overall_score']}/5 "
            f"tags={','.join(card.get('failure_tags', []))} "
            f"({elapsed:.1f}s)"
        )

    total_elapsed = time.time() - total_start
    return {
        "report_type": "pure_jade_v0_2_2_diagnostic_evaluation",
        "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
        "evaluator_type": FAST_EVALUATOR_TYPE,
        "evaluator_model": api_config.model,
        "eval_mode": "fast",
        "cases_file": str(args.cases),
        "eval_stage": args.eval_stage,
        "total_cases": len(cases),
        "total_duration_seconds": round(total_elapsed, 1),
        "evaluation_cards": cards,
        "summary": summarize_cards(cards),
    }


def full_card_from_result(result: Any, api_config: Any, full_format: str) -> dict[str, Any]:
    if full_format == "v0.2":
        card = result.map_to_v0_2_card(api_config)
        card["evaluation_mode"] = "full"
        return card
    if full_format == "8d":
        card = result.to_evaluation_card(api_config)
        card["evaluation_mode"] = "full"
        return card
    card = result.map_to_v0_1_card(api_config)
    card["evaluation_mode"] = "full"
    return card


def run_full_evaluation(args: argparse.Namespace, cases: list[dict[str, Any]], api_config: Any) -> dict[str, Any]:
    if not args.dimensions.exists():
        raise SystemExit(f"ERROR: dimensions config not found: {args.dimensions}")
    dimensions_config = load_json(args.dimensions)

    cards: list[dict[str, Any]] = []
    total_start = time.time()

    for i, case in enumerate(cases):
        case_start = time.time()
        result = evaluate_case(
            case_data=case,
            dimensions_config=dimensions_config,
            config=api_config,
            stage_filter=args.eval_stage,
            verbose=args.verbose,
        )
        elapsed = time.time() - case_start
        card = full_card_from_result(result, api_config, args.full_format)
        cards.append(card)
        print(
            f"[{i + 1}/{len(cases)}] {result.conversation_id} "
            f"full={card.get('overall_score')}/5 "
            f"({elapsed:.1f}s)"
        )

    total_elapsed = time.time() - total_start
    return {
        "report_type": f"pure_jade_full_{args.full_format}_evaluation",
        "schema_version": cards[0].get("schema_version") if cards else "0.1",
        "evaluator_type": FULL_EVALUATOR_TYPE,
        "evaluator_model": api_config.model,
        "eval_mode": "full",
        "full_format": args.full_format,
        "cases_file": str(args.cases),
        "eval_stage": args.eval_stage,
        "total_cases": len(cases),
        "total_duration_seconds": round(total_elapsed, 1),
        "evaluation_cards": cards,
        "summary": summarize_cards(cards),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PURE-JADE v0.2.3 evaluation runner")
    parser.add_argument("--mode", choices=["api"], default="api")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--dimensions", type=Path, default=DEFAULT_DIMENSIONS)
    parser.add_argument(
        "--eval-mode",
        choices=["fast", "full"],
        default="fast",
        help="fast = one API diagnostic card; full = old per-dimension evaluator",
    )
    parser.add_argument(
        "--eval-stage",
        choices=[
            "scenario_understanding",
            "empathetic_planning",
            "empathetic_actions",
            "multi_turn_state_update",
        ],
        default="empathetic_actions",
    )
    parser.add_argument(
        "--full-format",
        choices=["v0.1", "v0.2", "8d"],
        default="v0.1",
        help="Output card mapping used only by --eval-mode full.",
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--api-url", type=str, default=None)
    parser.add_argument("--api-model", type=str, default=None)
    parser.add_argument("--api-temperature", type=float, default=None)
    parser.add_argument("--api-timeout", type=int, default=None)
    parser.add_argument("--api-max-retries", type=int, default=None)
    parser.add_argument("--verbose", "-v", action="store_true", default=False)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = load_ready_cases(args.cases)
    api_config, api_errors = load_api_config(args)
    if api_errors:
        for err in api_errors:
            print(f"CONFIG ERROR: {err}")
        sys.exit(1)
    assert api_config is not None

    print(f"Evaluator mode: {args.eval_mode}")
    print(f"Model: {api_config.model}")
    print(f"API URL: {api_config.url}")
    print(f"Stage: {args.eval_stage}")
    print()

    if args.eval_mode == "fast":
        report = run_fast_evaluation(args, cases, api_config)
        default_name = f"diagnostic_eval_{time.strftime('%Y%m%d_%H%M%S')}.json"
    else:
        report = run_full_evaluation(args, cases, api_config)
        default_name = f"full_eval_{time.strftime('%Y%m%d_%H%M%S')}.json"

    output_path = args.output or (DEFAULT_REPORT_DIR / default_name)
    write_json(output_path, report)

    print()
    print(f"Report: {output_path}")
    summary = report.get("summary")
    if isinstance(summary, dict) and summary:
        print(
            "Scores (1-5): "
            f"mean={summary.get('mean_overall_score')}, "
            f"min={summary.get('min_overall_score')}, "
            f"max={summary.get('max_overall_score')}"
        )
    print(f"Total time: {report['total_duration_seconds']}s")


if __name__ == "__main__":
    main()
