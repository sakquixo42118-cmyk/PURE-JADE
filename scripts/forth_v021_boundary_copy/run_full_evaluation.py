"""End-to-end runner: PURE-JADE pipeline → EmpathyAgent 8-dim evaluation.

Runs the strategy pipeline to generate cards, then evaluates them with the
8-dimension empathy evaluation framework, outputting v0.1-compatible evaluation cards.

Usage:
    python scripts/run_full_evaluation.py --mode api
    python scripts/run_full_evaluation.py --mode api --cases examples/eval-test-cases-v0.1.json
    python scripts/run_full_evaluation.py --mode api --eval-stage empathetic_actions

If test cases already include all four cards (user_state_card, strategy_decision_card,
behavior_response_card), the pipeline step is skipped and evaluation runs directly.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Add project root to path so we can import sibling modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from empathy_evaluator import (
    DEFAULT_CASES,
    DEFAULT_DIMENSIONS,
    DEFAULT_ENV_FILE,
    DEFAULT_REPORT_DIR,
    ApiConfig,
    CaseEvalResult,
    evaluate_case,
    load_api_config,
    load_json,
    cases_from_conversation_record,
    write_json,
)


def check_cards_complete(case: dict) -> tuple[bool, list[str]]:
    """Check if a test case already has all cards needed for evaluation."""
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PURE-JADE end-to-end evaluation runner",
    )
    parser.add_argument(
        "--mode", choices=["api"], default="api",
        help="Evaluation mode (default: api)",
    )
    parser.add_argument(
        "--cases", type=Path, default=DEFAULT_CASES,
        help="Path to test cases JSON",
    )
    parser.add_argument(
        "--record", type=Path, default=None,
        help="Path to a v0.2.1 conversation_record JSON. If set, cases are built from turn_records.",
    )
    parser.add_argument(
        "--turn-id", type=int, default=None,
        help="Evaluate one turn from --record. Defaults to all complete turn_records.",
    )
    parser.add_argument(
        "--max-recent-turns", type=int, default=3,
        help="Recent dialogue turns to include when building cases from --record.",
    )
    parser.add_argument(
        "--dimensions", type=Path, default=DEFAULT_DIMENSIONS,
        help="Path to evaluation dimensions config",
    )
    parser.add_argument(
        "--eval-stage",
        choices=["scenario_understanding", "empathetic_planning", "empathetic_actions", "multi_turn_state_update"],
        default="empathetic_actions",
        help="Which evaluation stage to run (default: empathetic_actions)",
    )
    parser.add_argument(
        "--format", choices=["v0.1", "v0.2"], default="v0.1",
        help="Evaluation card format to write (default: v0.1)",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Output report path",
    )
    parser.add_argument(
        "--env-file", type=Path, default=DEFAULT_ENV_FILE,
        help="Path to .env file",
    )
    parser.add_argument("--api-url", type=str, default=None)
    parser.add_argument("--api-model", type=str, default=None)
    parser.add_argument("--api-temperature", type=float, default=None)
    parser.add_argument("--api-timeout", type=int, default=None)
    parser.add_argument("--api-max-retries", type=int, default=None)
    parser.add_argument("--verbose", "-v", action="store_true", default=False)
    args = parser.parse_args()

    # Load configs
    dimensions_config = load_json(args.dimensions)
    if args.max_recent_turns < 1:
        print("ERROR: --max-recent-turns must be at least 1")
        sys.exit(1)

    if args.record is not None:
        if not args.record.exists():
            print(f"ERROR: conversation record not found: {args.record}")
            sys.exit(1)
        try:
            cases = cases_from_conversation_record(args.record, args.turn_id, args.max_recent_turns)
        except ValueError as exc:
            print(f"ERROR: {exc}")
            sys.exit(1)
        cases_source = str(args.record)
    else:
        if not args.cases.exists():
            print(f"ERROR: test cases not found: {args.cases}")
            sys.exit(1)

        cases_doc = load_json(args.cases)
        cases = cases_doc.get("cases") if isinstance(cases_doc, dict) else cases_doc
        cases_source = str(args.cases)
        if not isinstance(cases, list):
            print("ERROR: test cases must be a JSON array or object with 'cases' array")
            sys.exit(1)

    api_config, api_errors = load_api_config(args)
    api_config, api_errors = load_api_config(args)
    if api_errors:
        for err in api_errors:
            print(f"CONFIG ERROR: {err}")
        sys.exit(1)
    assert api_config is not None

    # Check which cases need pipeline run
    need_pipeline = []
    ready_cases = []
    for case in cases:
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
        print("\nTo generate missing cards, run:")
        print("  python run_strategy_pipeline.py --mode api --cases <your_cases>.json")
        print("Then add user_state_card and behavior_response_card to each case.")
        print()

    if not ready_cases:
        print("No cases ready for evaluation. Exiting.")
        sys.exit(0)

    # Run evaluation on ready cases
    print(f"\n{'='*60}")
    print(f"Evaluating {len(ready_cases)} case(s) with {args.eval_stage} stage")
    print(f"Model: {api_config.model}")
    print(f"{'='*60}")

    all_v0_1_cards = []
    total_start = time.time()

    for i, case in enumerate(ready_cases):
        case_start = time.time()
        result = evaluate_case(
            case_data=case,
            dimensions_config=dimensions_config,
            config=api_config,
            stage_filter=args.eval_stage,
            verbose=args.verbose,
        )
        elapsed = time.time() - case_start

        eval_card = result.map_to_v0_2_card(api_config) if args.format == "v0.2" else result.map_to_v0_1_card(api_config)
        all_v0_1_cards.append(eval_card)

        print(
            f"[{i+1}/{len(ready_cases)}] {result.conversation_id} "
            f"8d={result.overall_score} {args.format}={eval_card['overall_score']}/5 "
            f"violations={len(eval_card['violations'])} "
            f"({elapsed:.1f}s)"
        )

    total_elapsed = time.time() - total_start

    # Build v0.1 report
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    report = {
        "report_type": f"pure_jade_{args.format.replace('.', '_')}_evaluation",
        "schema_version": args.format,
        "evaluator_type": "llm_initial",
        "evaluator_model": api_config.model,
        "cases_file": cases_source,
        "eval_stage": args.eval_stage,
        "total_cases": len(ready_cases),
        "total_duration_seconds": round(total_elapsed, 1),
        "evaluation_cards": all_v0_1_cards,
    }

    scores = [c["overall_score"] for c in all_v0_1_cards]
    if scores:
        report["summary"] = {
            "mean_overall_score": round(sum(scores) / len(scores), 2),
            "min_overall_score": min(scores),
            "max_overall_score": max(scores),
        }

    output_path = args.output or (DEFAULT_REPORT_DIR / f"full_eval_{timestamp}.json")
    write_json(output_path, report)

    print(f"\n{'='*60}")
    print(f"Report: {output_path}")
    if scores:
        print(f"v0.1 scores (1-5): mean={report['summary']['mean_overall_score']}, "
              f"min={report['summary']['min_overall_score']}, "
              f"max={report['summary']['max_overall_score']}")
    print(f"Total time: {total_elapsed:.1f}s")


if __name__ == "__main__":
    main()
