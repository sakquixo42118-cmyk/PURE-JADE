"""Small Tkinter frontend for PURE-JADE A/B comparison."""

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
RUNNER_PATH = PROJECT_ROOT / "scripts" / "ab_comparison" / "run_ab_comparison.py"
OUTPUT_ROOT = PROJECT_ROOT / "reports" / "ab_comparison"

BG = "#f4f6f8"
PANEL = "#ffffff"
TEXT = "#172033"
MUTED = "#5b6472"
ACCENT = "#2563eb"
ACCENT_DARK = "#1d4ed8"

JUDGE_MODES = {
    "API 盲评": "api",
    "只生成配对": "pair-only",
}


def default_comparison_id() -> str:
    return "ab_frontend_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def format_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def normalize_path(raw_path: str) -> Path:
    path = Path(raw_path.strip().strip('"'))
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def load_result_views(output_dir: Path) -> dict[str, str]:
    summary_path = output_dir / "comparison_summary.json"
    paired_path = output_dir / "paired_turns.json"
    judge_path = output_dir / "ab_judge_report.json"
    human_path = output_dir / "comparison_report.md"

    summary = read_json(summary_path) if summary_path.exists() else {"status": "missing", "path": str(summary_path)}
    paired = read_json(paired_path) if paired_path.exists() else {"status": "missing", "path": str(paired_path)}
    judge = read_json(judge_path) if judge_path.exists() else {"status": "missing", "path": str(judge_path)}
    human = human_path.read_text(encoding="utf-8") if human_path.exists() else "未生成 Markdown 报告。"

    overview_lines = [
        f"输出目录：{output_dir}",
        f"配对轮数：{summary.get('paired_turn_count')}",
        f"评估轮数：{summary.get('judged_turn_count')}",
        f"偏好胜负：{summary.get('wins')}",
        f"分数胜负：{summary.get('score_wins')}",
    ]
    mean_scores = summary.get("mean_scores")
    if isinstance(mean_scores, dict):
        overview_lines.append("")
        overview_lines.append("平均分：")
        for dimension in ("overall", "empathy", "actionability", "safety", "over_inference_control"):
            overview_lines.append(
                f"  {dimension}: "
                f"Direct={mean_scores.get('direct_api', {}).get(dimension)} | "
                f"PURE-JADE={mean_scores.get('pure_jade', {}).get(dimension)}"
            )
    warnings = summary.get("warnings")
    if warnings:
        overview_lines.append("")
        overview_lines.append("警告：")
        overview_lines.extend(f"  - {item}" for item in warnings)

    return {
        "总览": "\n".join(overview_lines),
        "配对 JSON": format_json(paired),
        "Judge JSON": format_json(judge),
        "汇总 JSON": format_json(summary),
        "Markdown": human,
    }


class ABComparisonApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PURE-JADE A/B 对比")
        self.geometry("1120x760")
        self.minsize(940, 640)
        self.configure(bg=BG)

        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.process: subprocess.Popen[str] | None = None
        self.current_output_dir: Path | None = None

        self.direct_record = tk.StringVar()
        self.chain_record = tk.StringVar()
        self.comparison_id = tk.StringVar(value=default_comparison_id())
        self.judge_mode = tk.StringVar(value="API 盲评")
        self.api_key = tk.StringVar()
        self.api_url = tk.StringVar()
        self.api_model = tk.StringVar()
        self.status = tk.StringVar(value="选择两份 conversation_record_latest.json 后运行。")
        self.output_path = tk.StringVar(value=str(OUTPUT_ROOT))

        self._configure_style()
        self._build_layout()
        self.after(100, self._poll_events)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        default_font = ("Microsoft YaHei UI", 9)
        self.option_add("*Font", default_font)
        style.configure(".", font=default_font, background=BG, foreground=TEXT)
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("Header.TFrame", background=BG)
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 16, "bold"), background=BG, foreground=TEXT)
        style.configure("Subtitle.TLabel", background=BG, foreground=MUTED)
        style.configure("Status.TLabel", background=PANEL, foreground=MUTED)
        style.configure("TLabelframe", background=PANEL, borderwidth=1, relief="solid")
        style.configure("TLabelframe.Label", background=PANEL, foreground=TEXT, font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("TButton", padding=(12, 6), relief="flat")
        style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff")
        style.map("Accent.TButton", background=[("active", ACCENT_DARK), ("disabled", "#9ca3af")])
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(12, 6))

    def _build_layout(self) -> None:
        shell = ttk.Frame(self, padding=(16, 14, 16, 16), style="Header.TFrame")
        shell.pack(fill=tk.BOTH, expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        header = ttk.Frame(shell, style="Header.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(header, text="PURE-JADE A/B 对比", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="读取 Direct API baseline 与三段链路 record，按轮次盲评并生成量化报告。",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w")

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

        records = ttk.LabelFrame(parent, text="对比记录", padding=10)
        records.grid(row=0, column=0, sticky="ew")
        records.columnconfigure(1, weight=1)

        ttk.Label(records, text="Direct record").grid(row=0, column=0, sticky="w")
        ttk.Entry(records, textvariable=self.direct_record).grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Button(records, text="选择", command=lambda: self._browse_record(self.direct_record)).grid(
            row=0, column=2, padx=(8, 0)
        )

        ttk.Label(records, text="PURE-JADE record").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(records, textvariable=self.chain_record).grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))
        ttk.Button(records, text="选择", command=lambda: self._browse_record(self.chain_record)).grid(
            row=1, column=2, padx=(8, 0), pady=(8, 0)
        )

        run = ttk.LabelFrame(parent, text="运行设置", padding=10)
        run.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        run.columnconfigure(1, weight=1)
        ttk.Label(run, text="对比 ID").grid(row=0, column=0, sticky="w")
        ttk.Entry(run, textvariable=self.comparison_id).grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Button(run, text="新建", command=lambda: self.comparison_id.set(default_comparison_id())).grid(
            row=0, column=2, padx=(8, 0)
        )
        ttk.Label(run, text="Judge 模式").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(run, textvariable=self.judge_mode, values=tuple(JUDGE_MODES), state="readonly").grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=(8, 0)
        )

        api = ttk.LabelFrame(parent, text="Judge API", padding=10)
        api.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        api.columnconfigure(1, weight=1)
        ttk.Label(api, text="API Key").grid(row=0, column=0, sticky="w")
        ttk.Entry(api, textvariable=self.api_key, show="*").grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Label(api, text="API URL").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(api, textvariable=self.api_url).grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))
        ttk.Label(api, text="模型").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(api, textvariable=self.api_model).grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=(8, 0))

        buttons = ttk.Frame(parent, style="Panel.TFrame")
        buttons.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        buttons.columnconfigure(0, weight=1)
        self.run_button = ttk.Button(buttons, text="运行 A/B 对比", command=self._start_run, style="Accent.TButton")
        self.run_button.grid(row=0, column=0, sticky="ew")
        self.stop_button = ttk.Button(buttons, text="停止", command=self._stop_run, state=tk.DISABLED)
        self.stop_button.grid(row=0, column=1, padx=(8, 0))

        status = ttk.LabelFrame(parent, text="状态", padding=10)
        status.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        status.columnconfigure(0, weight=1)
        ttk.Label(status, textvariable=self.status, style="Status.TLabel", wraplength=340).grid(row=0, column=0, sticky="ew")
        ttk.Entry(status, textvariable=self.output_path, state="readonly").grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(status, text="打开输出文件夹", command=self._open_output_dir).grid(row=2, column=0, sticky="ew")

    def _build_results(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        self.notebook = ttk.Notebook(parent)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        self.view_widgets: dict[str, ScrolledText] = {}
        for name in ("总览", "配对 JSON", "Judge JSON", "汇总 JSON", "Markdown", "日志"):
            frame = ttk.Frame(self.notebook, padding=6)
            frame.rowconfigure(0, weight=1)
            frame.columnconfigure(0, weight=1)
            widget = ScrolledText(frame, wrap=tk.WORD, undo=False)
            widget.grid(row=0, column=0, sticky="nsew")
            widget.configure(state=tk.DISABLED)
            self.notebook.add(frame, text=name)
            self.view_widgets[name] = widget
        self._set_view("总览", "运行完成后会显示 A/B 对比摘要。")
        self._set_view("日志", "runner 日志会显示在这里。")

    def _browse_record(self, variable: tk.StringVar) -> None:
        path = filedialog.askopenfilename(
            title="选择 conversation record",
            initialdir=str(PROJECT_ROOT / "reports"),
            filetypes=(("JSON 文件", "*.json"), ("所有文件", "*.*")),
        )
        if path:
            variable.set(path)

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

    def _build_command(self) -> list[str] | None:
        direct = self.direct_record.get().strip()
        chain = self.chain_record.get().strip()
        comparison_id = self.comparison_id.get().strip()
        if not direct or not chain:
            messagebox.showerror("缺少 record", "请先选择 Direct record 和 PURE-JADE record。")
            return None
        direct_path = normalize_path(direct)
        chain_path = normalize_path(chain)
        if not direct_path.exists():
            messagebox.showerror("找不到 Direct record", f"找不到路径：\n{direct_path}")
            return None
        if not chain_path.exists():
            messagebox.showerror("找不到 PURE-JADE record", f"找不到路径：\n{chain_path}")
            return None
        if not comparison_id:
            messagebox.showerror("缺少对比 ID", "对比 ID 不能为空。")
            return None
        if not RUNNER_PATH.exists():
            messagebox.showerror("缺少 runner", f"找不到 runner：\n{RUNNER_PATH}")
            return None
        judge_mode = JUDGE_MODES.get(self.judge_mode.get(), "api")
        return [
            sys.executable,
            "-B",
            str(RUNNER_PATH),
            "--direct-record",
            str(direct_path),
            "--chain-record",
            str(chain_path),
            "--comparison-id",
            comparison_id,
            "--judge-mode",
            judge_mode,
        ]

    def _start_run(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        command = self._build_command()
        if command is None:
            return
        self.current_output_dir = OUTPUT_ROOT / self.comparison_id.get().strip()
        self.output_path.set("等待 runner 输出 summary 路径...")
        for name in ("总览", "配对 JSON", "Judge JSON", "汇总 JSON", "Markdown", "日志"):
            self._set_view(name, "")
        self._append_log("$ " + subprocess.list2cmdline(command) + "\n\n")
        self.status.set("正在运行 A/B 对比...")
        self.run_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self.worker = threading.Thread(
            target=self._run_worker,
            args=(command, self.current_output_dir, self._build_env_overrides()),
            daemon=True,
        )
        self.worker.start()

    def _stop_run(self) -> None:
        process = self.process
        if process and process.poll() is None:
            self.status.set("正在停止...")
            process.terminate()

    def _run_worker(self, command: list[str], output_dir: Path, env_overrides: dict[str, str]) -> None:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
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
                self.events.put(("log", line))
                if line.startswith("output_dir="):
                    output_dir = Path(line.split("=", 1)[1].strip())
            code = self.process.wait()
            self.events.put(("finished", {"code": code, "output_dir": output_dir}))
        except Exception as error:  # noqa: BLE001 - surface UI worker errors.
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
                    self._finish_run(int(payload["code"]), payload["output_dir"])
                elif kind == "failed":
                    self._finish_run(1, self.current_output_dir)
                    self._append_log(f"\n界面后台任务错误：{payload}\n")
        except queue.Empty:
            pass
        self.after(100, self._poll_events)

    def _finish_run(self, code: int, output_dir: Path | None) -> None:
        self.run_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        if output_dir is None:
            self.status.set("尚未创建输出路径就失败了。")
            return
        self.output_path.set(str(output_dir))
        if (output_dir / "comparison_summary.json").exists():
            for name, value in load_result_views(output_dir).items():
                self._set_view(name, value)
            self.notebook.select(0)
        self.status.set("运行完成。" if code == 0 else f"运行失败，退出码 {code}。")
        if code == 0:
            self.comparison_id.set(default_comparison_id())

    def _open_output_dir(self) -> None:
        raw_path = self.output_path.get().strip()
        if not raw_path or raw_path.startswith("等待"):
            messagebox.showinfo("暂无输出", "当前还没有可打开的输出文件夹。")
            return
        path = normalize_path(raw_path)
        if not path.exists():
            messagebox.showerror("找不到输出文件夹", f"找不到路径：\n{path}")
            return
        os.startfile(path)


def main() -> int:
    app = ABComparisonApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
