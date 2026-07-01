"""PURE-JADE 完整链路 runner 的轻量 Tkinter 前端。

界面把所选完整链路 runner 当作黑盒 CLI 调用，不 import 或修改阶段源码。
"""

from __future__ import annotations

import datetime as dt
import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHAIN_PROFILES = {
    "v0.2.1 当前版（稳定/规则较强）": {
        "runner": PROJECT_ROOT / "scripts" / "run_full_chain_v021.py",
        "output_root": PROJECT_ROOT / "reports" / "full_chain_v021",
        "record_name": "conversation_record_v021_chain.json",
        "supports_eval_mode": False,
    },
    "v0.2.2 优化版（副本/少规则）": {
        "runner": PROJECT_ROOT / "scripts" / "full_chain_v022" / "run_full_chain_v022.py",
        "output_root": PROJECT_ROOT / "reports" / "full_chain_v022",
        "record_name": "conversation_record_v022_chain.json",
        "supports_eval_mode": False,
    },
    "v0.2.3 诊断评价版（一次 API）": {
        "runner": PROJECT_ROOT / "scripts" / "full_chain_v023" / "run_full_chain_v023.py",
        "output_root": PROJECT_ROOT / "reports" / "full_chain_v023",
        "record_name": "conversation_record_v023_chain.json",
        "supports_eval_mode": True,
    },
    "v0.2.4 现实任务敏感版": {
        "runner": PROJECT_ROOT / "scripts" / "full_chain_v024" / "run_full_chain_v024.py",
        "output_root": PROJECT_ROOT / "reports" / "full_chain_v024",
        "record_name": "conversation_record_v024_chain.json",
        "supports_eval_mode": True,
    },
    "Direct API Baseline（Minimal Support，一次 API）": {
        "runner": PROJECT_ROOT / "scripts" / "direct_api_baseline" / "run_direct_api_baseline.py",
        "output_root": PROJECT_ROOT / "reports" / "direct_api_baseline",
        "record_name": "conversation_record_direct_baseline.json",
        "supports_eval_mode": False,
        "extra_args": ["--baseline-mode", "minimal-support"],
    },
    "Direct API Baseline（Raw，一次 API）": {
        "runner": PROJECT_ROOT / "scripts" / "direct_api_baseline" / "run_direct_api_baseline.py",
        "output_root": PROJECT_ROOT / "reports" / "direct_api_baseline",
        "record_name": "conversation_record_direct_baseline.json",
        "supports_eval_mode": False,
        "extra_args": ["--baseline-mode", "raw"],
    },
}
DEFAULT_CHAIN_PROFILE = "v0.2.1 当前版（稳定/规则较强）"

STRATEGY_MODES = {
    "API（真实调用）": "api",
    "规则（不耗费 API）": "rules",
    "Mock（使用样例）": "mock",
}
BEHAVIOR_MODES = {
    "API（真实调用）": "api",
    "Mock（使用样例）": "mock",
    "Dry-run（只检查输入）": "dry-run",
}
EVAL_STAGES = {
    "行为回应质量（推荐）": "empathetic_actions",
    "共情策略规划": "empathetic_planning",
    "用户情境理解": "scenario_understanding",
}
EVAL_SCOPES = {
    "只评估最新一轮": "current-turn",
    "评估所有已完成轮次": "all-turns",
    "最新一轮 + 全部轮次": "both",
}
EVAL_MODES = {
    "Fast（一次 API 诊断评价）": "fast",
    "Full（旧版逐维评价）": "full",
}
INVALID_RUN_ID_CHARS = set('<>:"/\\|?*')
BG = "#f4f6f8"
PANEL = "#ffffff"
TEXT = "#172033"
MUTED = "#5b6472"
ACCENT = "#2563eb"
ACCENT_DARK = "#1d4ed8"
DANGER = "#b42318"


def default_run_id() -> str:
    return "frontend_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def format_json(value: Any) -> str:
    if value is None:
        return "未找到数据。"
    return json.dumps(value, ensure_ascii=False, indent=2)


def selected_option_value(raw_value: str, options: dict[str, str]) -> str:
    return options.get(raw_value, raw_value)


def normalize_user_path(raw_path: str) -> Path:
    path = Path(raw_path.strip().strip('"'))
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def existing_path_from_summary(value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value)
    return path if path.exists() else None


def find_run_output_dir(run_id: str, output_root: Path) -> Path | None:
    if not run_id:
        return None
    conversations_root = output_root / "conversations"
    if not conversations_root.exists():
        return None
    matches = sorted(
        [
            path
            for path in conversations_root.glob(f"*/{run_id}")
            if path.is_dir() and (path / "full_chain_summary.json").exists()
        ],
        key=lambda path: (path / "full_chain_summary.json").stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None


def find_turn_record(record: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any] | None:
    turns = record.get("turn_records")
    if not isinstance(turns, list) or not turns:
        return None

    target_turn_id: int | None = None
    strategy = summary.get("stages", {}).get("strategy")
    if isinstance(strategy, dict) and isinstance(strategy.get("turn_id"), int):
        target_turn_id = strategy["turn_id"]
    elif isinstance(record.get("current_turn_id"), int):
        target_turn_id = record["current_turn_id"]

    if target_turn_id is not None:
        for item in turns:
            if isinstance(item, dict) and item.get("turn_id") == target_turn_id:
                return item

    for item in reversed(turns):
        if isinstance(item, dict):
            return item
    return None


def stage_status(stage: Any) -> str:
    if not isinstance(stage, dict):
        return "缺失"
    return str(
        stage.get("_runner_status")
        or stage.get("status")
        or stage.get("validation", {}).get("status")
        or "未知"
    )


def result_score_line(eval_report: dict[str, Any] | None) -> str | None:
    if not isinstance(eval_report, dict):
        return None
    summary = eval_report.get("summary")
    if isinstance(summary, dict) and "mean_overall_score" in summary:
        return (
            "评估分数："
            f"均值={summary.get('mean_overall_score')}，"
            f"最小={summary.get('min_overall_score')}，"
            f"最大={summary.get('max_overall_score')}"
        )
    cards = eval_report.get("evaluation_cards")
    if isinstance(cards, list) and cards and isinstance(cards[0], dict):
        return f"评估分数：overall={cards[0].get('overall_score')}"
    return None


def build_overview(
    output_dir: Path,
    summary: dict[str, Any],
    record: dict[str, Any] | None,
    turn_record: dict[str, Any] | None,
    eval_report: dict[str, Any] | None,
) -> str:
    lines: list[str] = [
        f"状态：{summary.get('status', '未知')}",
        f"输出目录：{output_dir}",
    ]
    if summary.get("error"):
        lines.append(f"错误：{summary['error']}")

    modes = summary.get("modes")
    if isinstance(modes, dict):
        lines.append("")
        lines.append("运行模式：")
        for key in ("strategy_mode", "behavior_mode", "evaluation_skipped", "eval_mode", "eval_stage"):
            lines.append(f"  {key}: {modes.get(key)}")

    stages = summary.get("stages")
    if isinstance(stages, dict):
        lines.append("")
        lines.append("阶段状态：")
        for name in ("first", "strategy", "behavior", "evaluation"):
            stage = stages.get(name)
            mode = f" mode={stage.get('mode')}" if isinstance(stage, dict) and stage.get("mode") else ""
            lines.append(f"  {name}: {stage_status(stage)}{mode}")

    if isinstance(record, dict):
        lines.append("")
        lines.append(f"对话 ID：{record.get('conversation_id', '未知')}")
        if isinstance(turn_record, dict):
            lines.append(f"轮次：{turn_record.get('turn_id', '未知')}")

    if isinstance(turn_record, dict):
        behavior = turn_record.get("behavior_response_card")
        if isinstance(behavior, dict) and behavior.get("text_response"):
            lines.append("")
            lines.append("助手回复：")
            lines.append(str(behavior["text_response"]))

    score_line = result_score_line(eval_report)
    if score_line:
        lines.append("")
        lines.append(score_line)
        cards = eval_report.get("evaluation_cards") if isinstance(eval_report, dict) else None
        if isinstance(cards, list) and cards and isinstance(cards[0], dict):
            violations = cards[0].get("violations")
            lines.append(f"违规项数量：{len(violations) if isinstance(violations, list) else '未知'}")
            lines.append(f"需要人工复核：{cards[0].get('review_needed')}")

    lines.append("")
    lines.append("输出文件：")
    for name in (
        "01_direct_request_report.json",
        "01_first_state_report.json",
        "02_strategy_report.json",
        "03_behavior_report.json",
        "04_evaluation_cases.json",
        "05_evaluation_report.json",
        "06_all_turn_evaluation_cases.json",
        "07_all_turn_evaluation_report.json",
        "08_conversation_summary_report.json",
        "09_dialogue_review_report.json",
        "conversation_record_v021_chain.json",
        "conversation_record_v022_chain.json",
        "conversation_record_v023_chain.json",
        "conversation_record_v024_chain.json",
        "conversation_record_direct_baseline.json",
        "full_chain_summary.json",
    ):
        path = output_dir / name
        if path.exists():
            lines.append(f"  {path}")

    return "\n".join(lines)


def format_dialogue_log(record: dict[str, Any] | None) -> str:
    if not isinstance(record, dict):
        return "未找到对话日志。"
    dialogue = record.get("dialogue_log")
    if not isinstance(dialogue, list) or not dialogue:
        return "dialogue_log 为空。"

    speaker_names = {"user": "用户", "assistant": "助手"}
    lines: list[str] = []
    for item in dialogue:
        if not isinstance(item, dict):
            continue
        turn_id = item.get("turn_id", "?")
        speaker = speaker_names.get(str(item.get("speaker")), str(item.get("speaker", "未知")))
        content = str(item.get("content", "")).strip()
        if content:
            lines.append(f"[第 {turn_id} 轮] {speaker}：\n{content}")
    return "\n\n".join(lines) if lines else "dialogue_log 中没有可显示的内容。"


def load_result_views(output_dir: Path) -> dict[str, str]:
    summary_path = output_dir / "full_chain_summary.json"
    if not summary_path.exists():
        return {
            "总览": f"尚未找到 summary 文件。\n预期路径：{summary_path}",
            "对话日志": "未找到数据。",
            "状态卡": "未找到数据。",
            "策略卡": "未找到数据。",
            "行为卡": "未找到数据。",
            "评估": "未找到数据。",
            "全对话复盘": "未找到数据。",
            "汇总 JSON": "未找到数据。",
        }

    summary = read_json(summary_path)
    if not isinstance(summary, dict):
        summary = {"status": "未知", "raw_summary": summary}

    paths = summary.get("paths") if isinstance(summary.get("paths"), dict) else {}
    record_path = existing_path_from_summary(paths.get("working_record")) if paths else None
    if record_path is None:
        fallbacks = [
            output_dir / "conversation_record_direct_baseline.json",
            output_dir / "conversation_record_v024_chain.json",
            output_dir / "conversation_record_v023_chain.json",
            output_dir / "conversation_record_v022_chain.json",
            output_dir / "conversation_record_v021_chain.json",
        ]
        record_path = next((path for path in fallbacks if path.exists()), None)

    record: dict[str, Any] | None = None
    turn_record: dict[str, Any] | None = None
    if record_path is not None:
        loaded_record = read_json(record_path)
        if isinstance(loaded_record, dict):
            record = loaded_record
            turn_record = find_turn_record(record, summary)

    strategy_report = None
    strategy_path = output_dir / "02_strategy_report.json"
    if strategy_path.exists():
        strategy_report = read_json(strategy_path)

    behavior_report = None
    behavior_path = output_dir / "03_behavior_report.json"
    if behavior_path.exists():
        behavior_report = read_json(behavior_path)

    eval_report = None
    eval_path = output_dir / "05_evaluation_report.json"
    if eval_path.exists():
        loaded_eval = read_json(eval_path)
        if isinstance(loaded_eval, dict):
            eval_report = loaded_eval

    all_turn_eval_report = None
    all_turn_eval_path = output_dir / "07_all_turn_evaluation_report.json"
    if all_turn_eval_path.exists():
        loaded_all_turn_eval = read_json(all_turn_eval_path)
        if isinstance(loaded_all_turn_eval, dict):
            all_turn_eval_report = loaded_all_turn_eval

    conversation_summary_report = None
    conversation_summary_path = output_dir / "08_conversation_summary_report.json"
    if conversation_summary_path.exists():
        loaded_conversation_summary = read_json(conversation_summary_path)
        if isinstance(loaded_conversation_summary, dict):
            conversation_summary_report = loaded_conversation_summary

    dialogue_review_report = None
    dialogue_review_path = output_dir / "09_dialogue_review_report.json"
    if dialogue_review_path.exists():
        loaded_dialogue_review = read_json(dialogue_review_path)
        if isinstance(loaded_dialogue_review, dict):
            dialogue_review_report = loaded_dialogue_review

    evaluation_view = {
        "current_turn": eval_report,
        "all_turns": all_turn_eval_report,
    }
    summary_view = {
        "full_chain_summary": summary,
        "conversation_summary": conversation_summary_report,
        "dialogue_review": dialogue_review_report,
    }

    return {
        "总览": build_overview(output_dir, summary, record, turn_record, eval_report),
        "对话日志": format_dialogue_log(record),
        "状态卡": format_json(turn_record.get("user_state_card") if isinstance(turn_record, dict) else None),
        "策略卡": format_json(
            turn_record.get("strategy_decision_card")
            if isinstance(turn_record, dict) and turn_record.get("strategy_decision_card")
            else strategy_report
        ),
        "行为卡": format_json(
            turn_record.get("behavior_response_card")
            if isinstance(turn_record, dict) and turn_record.get("behavior_response_card")
            else behavior_report
        ),
        "评估": format_json(evaluation_view),
        "全对话复盘": format_json(dialogue_review_report),
        "汇总 JSON": format_json(summary_view),
    }


class FullChainFrontend(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PURE-JADE 完整链路")
        self.geometry("1240x800")
        self.minsize(1040, 680)
        self.configure(bg=BG)

        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.process: subprocess.Popen[str] | None = None
        self.current_output_dir: Path | None = None
        self.last_record_path: Path | None = None

        self.chain_profile = tk.StringVar(value=DEFAULT_CHAIN_PROFILE)
        self.api_key = tk.StringVar()
        self.api_url = tk.StringVar()
        self.api_model = tk.StringVar()
        self.source_mode = tk.StringVar(value="message")
        self.run_id = tk.StringVar(value=default_run_id())
        self.record_path = tk.StringVar()
        self.strategy_mode = tk.StringVar(value="规则（不耗费 API）")
        self.behavior_mode = tk.StringVar(value="Dry-run（只检查输入）")
        self.eval_stage = tk.StringVar(value="行为回应质量（推荐）")
        self.eval_scope = tk.StringVar(value="只评估最新一轮")
        self.eval_mode = tk.StringVar(value="Fast（一次 API 诊断评价）")
        self.skip_eval = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="就绪。默认模式不会调用 API。")
        self.output_path = tk.StringVar(value=str(self._active_output_root()))

        self._configure_style()
        self._build_layout()
        self._sync_input_mode()
        self.after(100, self._poll_events)

    def _active_chain_config(self) -> dict[str, Any]:
        return CHAIN_PROFILES.get(self.chain_profile.get(), CHAIN_PROFILES[DEFAULT_CHAIN_PROFILE])

    def _active_runner_path(self) -> Path:
        return self._active_chain_config()["runner"]

    def _active_output_root(self) -> Path:
        return self._active_chain_config()["output_root"]

    def _active_record_name(self) -> str:
        return str(self._active_chain_config()["record_name"])

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        default_font = ("Microsoft YaHei UI", 9)
        title_font = ("Microsoft YaHei UI", 16, "bold")
        subtitle_font = ("Microsoft YaHei UI", 9)
        self.option_add("*Font", default_font)
        style.configure(".", font=default_font, background=BG, foreground=TEXT)
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("Header.TFrame", background=BG)
        style.configure("Title.TLabel", font=title_font, background=BG, foreground=TEXT)
        style.configure("Subtitle.TLabel", font=subtitle_font, background=BG, foreground=MUTED)
        style.configure("TLabel", padding=(0, 2), background=BG, foreground=TEXT)
        style.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
        style.configure("Status.TLabel", background=PANEL, foreground=MUTED)
        style.configure("TLabelframe", background=PANEL, borderwidth=1, relief="solid")
        style.configure("TLabelframe.Label", background=PANEL, foreground=TEXT, font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("TButton", padding=(12, 6), relief="flat")
        style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff")
        style.map("Accent.TButton", background=[("active", ACCENT_DARK), ("disabled", "#9ca3af")])
        style.configure("Danger.TButton", foreground=DANGER)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(12, 6))

    def _build_layout(self) -> None:
        shell = ttk.Frame(self, padding=(16, 14, 16, 16), style="Header.TFrame")
        shell.pack(fill=tk.BOTH, expand=True)
        shell.rowconfigure(1, weight=1)
        shell.columnconfigure(0, weight=1)

        header = ttk.Frame(shell, style="Header.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="PURE-JADE 完整链路 Demo", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="多轮对话、策略卡、行为卡、卡片评估和全对话复盘集中在一个入口。",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        root = ttk.PanedWindow(shell, orient=tk.HORIZONTAL)
        root.grid(row=1, column=0, sticky="nsew")

        controls = ttk.Frame(root, padding=12, style="Panel.TFrame")
        results = ttk.Frame(root, padding=(12, 0, 0, 0), style="Header.TFrame")
        root.add(controls, weight=0)
        root.add(results, weight=1)

        self._build_controls(controls)
        self._build_results(results)

    def _build_controls(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)

        source = ttk.LabelFrame(parent, text="输入", padding=10)
        source.grid(row=0, column=0, sticky="nsew")
        source.columnconfigure(0, weight=1)

        mode_row = ttk.Frame(source)
        mode_row.grid(row=0, column=0, sticky="ew")
        ttk.Radiobutton(
            mode_row,
            text="新对话",
            variable=self.source_mode,
            value="message",
            command=self._sync_input_mode,
        ).pack(side=tk.LEFT)
        ttk.Radiobutton(
            mode_row,
            text="继续对话",
            variable=self.source_mode,
            value="continue",
            command=self._sync_input_mode,
        ).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Radiobutton(
            mode_row,
            text="仅重跑 record",
            variable=self.source_mode,
            value="record",
            command=self._sync_input_mode,
        ).pack(side=tk.LEFT, padx=(12, 0))

        self.message_text = ScrolledText(source, height=8, width=42, wrap=tk.WORD, undo=True)
        self.message_text.grid(row=1, column=0, sticky="nsew", pady=(8, 8))
        self.message_text.insert("1.0", "我最近真的很累，明明一直在复习，但成绩还是没有起色。")

        record_row = ttk.Frame(source)
        record_row.grid(row=2, column=0, sticky="ew")
        record_row.columnconfigure(0, weight=1)
        self.record_entry = ttk.Entry(record_row, textvariable=self.record_path)
        self.record_entry.grid(row=0, column=0, sticky="ew")
        self.browse_button = ttk.Button(record_row, text="选择", command=self._browse_record)
        self.browse_button.grid(row=0, column=1, padx=(8, 0))

        chain_api = ttk.LabelFrame(parent, text="链路与 API", padding=10)
        chain_api.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        chain_api.columnconfigure(1, weight=1)

        ttk.Label(chain_api, text="链路版本").grid(row=0, column=0, sticky="w")
        chain_box = ttk.Combobox(
            chain_api,
            textvariable=self.chain_profile,
            values=tuple(CHAIN_PROFILES),
            state="readonly",
        )
        chain_box.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        chain_box.bind("<<ComboboxSelected>>", lambda _event: self._on_chain_changed())

        ttk.Label(chain_api, text="API Key").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(chain_api, textvariable=self.api_key, show="*").grid(
            row=1, column=1, sticky="ew", padx=(8, 0), pady=(8, 0)
        )

        ttk.Label(chain_api, text="API URL").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(chain_api, textvariable=self.api_url).grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))

        ttk.Label(chain_api, text="模型").grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(chain_api, textvariable=self.api_model).grid(row=3, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))

        run = ttk.LabelFrame(parent, text="运行配置", padding=10)
        run.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        run.columnconfigure(1, weight=1)
        ttk.Label(run, text="运行 ID").grid(row=0, column=0, sticky="w")
        ttk.Entry(run, textvariable=self.run_id).grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Button(run, text="新建", command=self._new_run_id).grid(row=0, column=2, padx=(8, 0))

        ttk.Label(run, text="策略模式").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(run, textvariable=self.strategy_mode, values=tuple(STRATEGY_MODES), state="readonly").grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=(8, 0)
        )

        ttk.Label(run, text="行为模式").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(run, textvariable=self.behavior_mode, values=tuple(BEHAVIOR_MODES), state="readonly").grid(
            row=2, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=(8, 0)
        )

        ttk.Label(run, text="评估对象").grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(run, textvariable=self.eval_stage, values=tuple(EVAL_STAGES), state="readonly").grid(
            row=3, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=(8, 0)
        )

        ttk.Label(run, text="评估范围").grid(row=4, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(run, textvariable=self.eval_scope, values=tuple(EVAL_SCOPES), state="readonly").grid(
            row=4, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=(8, 0)
        )

        ttk.Label(run, text="评价模式").grid(row=5, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(run, textvariable=self.eval_mode, values=tuple(EVAL_MODES), state="readonly").grid(
            row=5, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=(8, 0)
        )

        ttk.Checkbutton(run, text="跳过评估", variable=self.skip_eval).grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(8, 0)
        )

        buttons = ttk.Frame(parent)
        buttons.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        buttons.columnconfigure(0, weight=1)
        self.run_button = ttk.Button(buttons, text="运行完整链路", command=self._start_run, style="Accent.TButton")
        self.run_button.grid(row=0, column=0, sticky="ew")
        self.stop_button = ttk.Button(buttons, text="停止", command=self._stop_run, state=tk.DISABLED, style="Danger.TButton")
        self.stop_button.grid(row=0, column=1, padx=(8, 0))

        status = ttk.LabelFrame(parent, text="状态", padding=10)
        status.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        status.columnconfigure(0, weight=1)
        ttk.Label(status, textvariable=self.status, style="Status.TLabel", wraplength=330).grid(row=0, column=0, sticky="ew")
        path_entry = ttk.Entry(status, textvariable=self.output_path, state="readonly")
        path_entry.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        status_buttons = ttk.Frame(status, style="Panel.TFrame")
        status_buttons.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        status_buttons.columnconfigure(0, weight=1)
        status_buttons.columnconfigure(1, weight=1)
        ttk.Button(status_buttons, text="复制输出路径", command=self._copy_output_path).grid(row=0, column=0, sticky="ew")
        ttk.Button(status_buttons, text="打开输出文件夹", command=self._open_output_dir).grid(
            row=0, column=1, sticky="ew", padx=(8, 0)
        )

        parent.rowconfigure(5, weight=1)

    def _build_results(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(parent)
        self.notebook.grid(row=0, column=0, sticky="nsew")

        self.view_widgets: dict[str, ScrolledText] = {}
        for name in ("总览", "对话日志", "状态卡", "策略卡", "行为卡", "评估", "全对话复盘", "汇总 JSON", "日志"):
            frame = ttk.Frame(self.notebook, padding=6)
            frame.rowconfigure(0, weight=1)
            frame.columnconfigure(0, weight=1)
            widget = ScrolledText(frame, wrap=tk.WORD, undo=False)
            widget.grid(row=0, column=0, sticky="nsew")
            widget.configure(state=tk.DISABLED)
            self.notebook.add(frame, text=name)
            self.view_widgets[name] = widget

        self._set_view("总览", "配置运行参数后，点击“运行完整链路”。默认模式不会调用 API。")
        self._set_view("日志", "runner 日志会显示在这里。")

    def _browse_record(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 conversation record",
            initialdir=str(PROJECT_ROOT),
            filetypes=(("JSON 文件", "*.json"), ("所有文件", "*.*")),
        )
        if path:
            self.record_path.set(path)
            if self.source_mode.get() == "message":
                self.source_mode.set("continue")
            self._sync_input_mode()

    def _replace_message(self, value: str) -> None:
        self.message_text.configure(state=tk.NORMAL)
        self.message_text.delete("1.0", tk.END)
        self.message_text.insert("1.0", value)
        if self.source_mode.get() == "record":
            self.message_text.configure(state=tk.DISABLED)

    def _sync_input_mode(self) -> None:
        mode = self.source_mode.get()
        if not hasattr(self, "message_text"):
            return

        record_enabled = mode in {"continue", "record"}
        message_enabled = mode in {"message", "continue"}
        self.message_text.configure(state=tk.NORMAL if message_enabled else tk.DISABLED)
        self.record_entry.configure(state=tk.NORMAL if record_enabled else tk.DISABLED)
        self.browse_button.configure(state=tk.NORMAL if record_enabled else tk.DISABLED)

        if mode == "message":
            self.status.set("新对话模式：输入用户消息后会从第 1 轮开始。默认不调用 API 评估。")
        elif mode == "continue":
            self.status.set("继续对话模式：选择上一次输出的 record，输入下一轮用户消息后再运行。")
            self.record_entry.focus_set()
        else:
            self.status.set("仅重跑 record 模式：跳过 first，只对已有 record 的当前轮重跑后续阶段。")
            self.record_entry.focus_set()

    def _new_run_id(self) -> None:
        self.run_id.set(default_run_id())

    def _copy_output_path(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.output_path.get())
        self.status.set("输出路径已复制。")

    def _open_output_dir(self) -> None:
        raw_path = self.output_path.get().strip()
        if not raw_path or raw_path.startswith("等待"):
            messagebox.showinfo("暂无输出", "当前还没有可打开的输出文件夹。")
            return
        path = normalize_user_path(raw_path)
        if not path.exists():
            messagebox.showerror("找不到输出文件夹", f"找不到路径：\n{path}")
            return
        os.startfile(path)

    def _set_view(self, name: str, value: str) -> None:
        widget = self.view_widgets[name]
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", value)
        widget.configure(state=tk.DISABLED)

    def _append_log(self, value: str) -> None:
        widget = self.view_widgets["日志"]
        widget.configure(state=tk.NORMAL)
        widget.insert(tk.END, value)
        widget.see(tk.END)
        widget.configure(state=tk.DISABLED)

    def _on_chain_changed(self) -> None:
        self.output_path.set(str(self._active_output_root()))
        self.status.set(f"已选择链路：{self.chain_profile.get()}。")

    def _build_env_overrides(self) -> dict[str, str]:
        env: dict[str, str] = {}
        key = self.api_key.get().strip()
        url = self.api_url.get().strip()
        model = self.api_model.get().strip()
        if key:
            env["PURE_JADE_API_KEY"] = key
            env["LLM_API_KEY"] = key
        if url:
            env["PURE_JADE_API_URL"] = url
            env["LLM_BASE_URL"] = url
        if model:
            env["PURE_JADE_API_MODEL"] = model
            env["LLM_MODEL"] = model
        return env
    def _validate_run_id(self) -> str | None:
        run_id = self.run_id.get().strip()
        if not run_id:
            messagebox.showerror("缺少运行 ID", "运行 ID 不能为空。")
            return None
        if any(char in INVALID_RUN_ID_CHARS for char in run_id):
            messagebox.showerror("运行 ID 无效", "运行 ID 不能包含路径分隔符或 Windows 文件名非法字符。")
            return None
        return run_id

    def _build_command(self, run_id: str) -> list[str] | None:
        runner_path = self._active_runner_path()
        if not runner_path.exists():
            messagebox.showerror("缺少 runner", f"找不到 runner：\n{runner_path}")
            return None

        command = [sys.executable, "-B", str(runner_path), "--run-id", run_id]
        command.extend(str(value) for value in self._active_chain_config().get("extra_args", []))
        mode = self.source_mode.get()
        if mode in {"continue", "record"}:
            raw_record = self.record_path.get().strip()
            if not raw_record:
                messagebox.showerror("缺少 record", "请先选择一个 conversation record。")
                return None
            record_path = normalize_user_path(raw_record)
            if not record_path.exists():
                messagebox.showerror("找不到 record", f"找不到 record：\n{record_path}")
                return None

        if mode == "record":
            command.extend(["--record", str(record_path)])
        else:
            message = self.message_text.get("1.0", tk.END).strip()
            if not message:
                messagebox.showerror("缺少用户消息", "请先输入一条用户消息。")
                return None
            command.extend(["--message", message])
            if mode == "continue":
                command.extend(["--continue-record", str(record_path)])

        strategy_mode = selected_option_value(self.strategy_mode.get(), STRATEGY_MODES)
        behavior_mode = selected_option_value(self.behavior_mode.get(), BEHAVIOR_MODES)
        eval_stage = selected_option_value(self.eval_stage.get(), EVAL_STAGES)
        eval_scope = selected_option_value(self.eval_scope.get(), EVAL_SCOPES)
        eval_mode = selected_option_value(self.eval_mode.get(), EVAL_MODES)

        command.extend(["--strategy-mode", strategy_mode])
        command.extend(["--behavior-mode", behavior_mode])

        if behavior_mode == "dry-run" and not self.skip_eval.get():
            self.skip_eval.set(True)
            messagebox.showinfo("已关闭评估", "behavior dry-run 不能进入评估，因此已自动勾选“跳过评估”。")

        if self.skip_eval.get():
            command.append("--skip-evaluation")
        else:
            command.extend(["--eval-stage", eval_stage])
            command.extend(["--eval-scope", eval_scope])
            if self._active_chain_config().get("supports_eval_mode"):
                command.extend(["--eval-mode", eval_mode])

        return command

    def _start_run(self) -> None:
        if self.worker and self.worker.is_alive():
            return

        run_id = self._validate_run_id()
        if not run_id:
            return
        command = self._build_command(run_id)
        if command is None:
            return

        self.current_output_dir = self._active_output_root() / run_id
        self.output_path.set("等待 runner 输出 summary 路径...")
        for name in ("总览", "对话日志", "状态卡", "策略卡", "行为卡", "评估", "全对话复盘", "汇总 JSON"):
            self._set_view(name, "")
        self._set_view("日志", "")
        self._append_log("$ " + subprocess.list2cmdline(command) + "\n\n")

        self.status.set("正在运行完整链路...")
        self.run_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)

        env_overrides = self._build_env_overrides()
        self.worker = threading.Thread(
            target=self._run_worker,
            args=(command, self.current_output_dir, self._active_output_root(), env_overrides),
            daemon=True,
        )
        self.worker.start()

    def _stop_run(self) -> None:
        process = self.process
        if process and process.poll() is None:
            self.status.set("正在停止...")
            process.terminate()

    def _run_worker(
        self,
        command: list[str],
        output_dir: Path,
        output_root: Path,
        env_overrides: dict[str, str],
    ) -> None:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        summary_path: Path | None = None
        try:
            self.process = subprocess.Popen(
                command,
                cwd=PROJECT_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
                env={**os.environ, **env_overrides},
            )
            assert self.process.stdout is not None
            for line in self.process.stdout:
                if line.startswith("summary="):
                    raw_summary = line.split("=", 1)[1].strip()
                    if raw_summary:
                        summary_path = Path(raw_summary)
                self.events.put(("log", line))
            code = self.process.wait()
            self.events.put((
                "finished",
                {"code": code, "output_dir": output_dir, "summary_path": summary_path, "output_root": output_root},
            ))
        except Exception as error:  # noqa: BLE001 - surface UI worker failures.
            self.events.put(("failed", str(error)))
        finally:
            self.process = None

    def _poll_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "finished":
                    self._finish_run(
                        int(payload["code"]),
                        payload["output_dir"],
                        payload.get("summary_path"),
                        payload.get("output_root") or self._active_output_root(),
                    )
                elif kind == "failed":
                    self._finish_run(1, self.current_output_dir, None, self._active_output_root())
                    self._append_log(f"\n界面后台任务错误：{payload}\n")
        except queue.Empty:
            pass
        self.after(100, self._poll_events)

    def _finish_run(
        self,
        code: int,
        output_dir: Path | None,
        summary_path: Path | None = None,
        output_root: Path | None = None,
    ) -> None:
        self.run_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        if summary_path is not None and summary_path.exists():
            output_dir = summary_path.parent
        elif output_dir is not None:
            found_output_dir = find_run_output_dir(output_dir.name, output_root or self._active_output_root())
            if found_output_dir is not None:
                output_dir = found_output_dir
        if output_dir is None:
            self.status.set("尚未创建输出路径就失败了。")
            return

        views = load_result_views(output_dir)
        for name, value in views.items():
            self._set_view(name, value)
        self.notebook.select(0)
        self.output_path.set(str(output_dir))
        record_candidates = [
            output_dir / self._active_record_name(),
            output_dir / "conversation_record_direct_baseline.json",
            output_dir / "conversation_record_v024_chain.json",
            output_dir / "conversation_record_v023_chain.json",
            output_dir / "conversation_record_v022_chain.json",
            output_dir / "conversation_record_v021_chain.json",
        ]
        output_record = next((path for path in record_candidates if path.exists()), None)
        if output_record is not None:
            self.last_record_path = output_record
        if code == 0 and self.last_record_path:
            self.record_path.set(str(self.last_record_path))
            self.source_mode.set("continue")
            self.skip_eval.set(True)
            self._replace_message("")
            self._sync_input_mode()
            self.status.set("运行完成。已切到继续对话：输入下一轮用户消息后再运行；需要最终评估时取消“跳过评估”。")
        else:
            self.status.set("运行完成。" if code == 0 else f"运行失败，退出码 {code}。")
        if code == 0:
            self.run_id.set(default_run_id())


def main() -> int:
    app = FullChainFrontend()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
