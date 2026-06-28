"""Extract ESConv strategy examples into JSON Lines.

The output is intended for PURE-JADE's case library:
context + strategy + supporter response.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DEFAULT_INPUT = Path("data/raw/esconv/ESConv.json")
DEFAULT_OUTPUT = Path("data/processed/esconv_examples.jsonl")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_strategy(value: Any) -> str:
    strategy = clean_text(value)
    if strategy.startswith("[") and strategy.endswith("]"):
        strategy = strategy[1:-1].strip()
    return strategy


def annotation_strategy(turn: dict[str, Any]) -> str:
    annotation = turn.get("annotation") or {}
    if not isinstance(annotation, dict):
        return ""
    return normalize_strategy(annotation.get("strategy"))


def build_context(dialog: list[dict[str, Any]], turn_index: int, context_turns: int) -> list[dict[str, str]]:
    start = max(0, turn_index - context_turns)
    context: list[dict[str, str]] = []
    for turn in dialog[start:turn_index]:
        speaker = clean_text(turn.get("speaker"))
        content = clean_text(turn.get("content"))
        if not speaker or not content:
            continue
        context.append({"speaker": speaker, "content": content})
    return context


def iter_examples(
    conversations: list[dict[str, Any]],
    context_turns: int,
) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for conversation_index, conversation in enumerate(conversations):
        dialog = conversation.get("dialog") or []
        if not isinstance(dialog, list):
            continue

        for turn_index, turn in enumerate(dialog):
            if not isinstance(turn, dict):
                continue
            if clean_text(turn.get("speaker")) != "supporter":
                continue

            strategy = annotation_strategy(turn)
            response = clean_text(turn.get("content"))
            if not strategy or not response:
                continue

            examples.append(
                {
                    "example_id": f"esconv_{conversation_index:04d}_t{turn_index:03d}",
                    "source": "ESConv",
                    "conversation_index": conversation_index,
                    "turn_index": turn_index,
                    "emotion_type": clean_text(conversation.get("emotion_type")),
                    "problem_type": clean_text(conversation.get("problem_type")),
                    "situation": clean_text(conversation.get("situation")),
                    "survey_score": conversation.get("survey_score") or {},
                    "context": build_context(dialog, turn_index, context_turns),
                    "strategy": strategy,
                    "supporter_response": response,
                }
            )
    return examples


def limit_per_strategy(
    examples: list[dict[str, Any]],
    max_per_strategy: int | None,
) -> list[dict[str, Any]]:
    if max_per_strategy is None:
        return examples
    if max_per_strategy <= 0:
        raise ValueError("--max-per-strategy must be positive when provided")

    kept: list[dict[str, Any]] = []
    counts: dict[str, int] = defaultdict(int)
    for example in examples:
        strategy = str(example["strategy"])
        if counts[strategy] >= max_per_strategy:
            continue
        kept.append(example)
        counts[strategy] += 1
    return kept


def write_jsonl(path: Path, examples: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for example in examples:
            file.write(json.dumps(example, ensure_ascii=False))
            file.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--context-turns", type=int, default=4)
    parser.add_argument("--max-per-strategy", type=int, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.context_turns < 1:
        raise ValueError("--context-turns must be at least 1")
    if not args.input.exists():
        raise FileNotFoundError(f"Input file not found: {args.input}")

    conversations = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(conversations, list):
        raise ValueError("ESConv input must be a JSON array")

    examples = iter_examples(conversations, args.context_turns)
    examples = limit_per_strategy(examples, args.max_per_strategy)
    write_jsonl(args.output, examples)

    counts = Counter(example["strategy"] for example in examples)
    print(f"conversations={len(conversations)}")
    print(f"examples={len(examples)}")
    for strategy, count in sorted(counts.items()):
        print(f"{strategy}={count}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
