#!/usr/bin/env python3
"""
PURE-JADE 情感支持AI — 桌面客户端

基于 CustomTkinter 构建，可通过 PyInstaller 打包为 EXE。

功能：
  - API 配置管理（密钥／地址／模型）
  - 新建对话 + 多轮情感支持对话
  - 后端服务自动启停
  - 对话记录自动保存至 data/conversations/
  - 用户状态卡可视化展示
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
import customtkinter as ctk

# ═══════════════════════════════════════════════════════════════════════
# 全局常量
# ═══════════════════════════════════════════════════════════════════════

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_SCRIPT = PROJECT_ROOT / "main.py"
BACKEND_URL = "http://127.0.0.1:8000"

# ═══════════════════════════════════════════════════════════════════════
# CustomTkinter 主题
# ═══════════════════════════════════════════════════════════════════════

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

# ── 颜色常量 ─────────────────────────────────────────────────────────────
COLOR_USER_BUBBLE = "#DCF8C6"  # 浅绿 — 用户气泡
COLOR_AI_BUBBLE = "#F0F0F0"  # 浅灰 — AI 气泡
COLOR_STATE_CARD_BG = "#EDF3FF"  # 浅蓝 — 状态卡背景
COLOR_STATUS_OK = "#00CC00"
COLOR_STATUS_ERR = "#FF4444"


# ═══════════════════════════════════════════════════════════════════════
# 后端管理器
# ═══════════════════════════════════════════════════════════════════════

class BackendManager:
    """管理后端 FastAPI 服务的生命周期（子进程）"""

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None

    # ── 生命周期 ──────────────────────────────────────────────────────────

    def start(self) -> None:
        """异步启动后端（调用者需等待就绪）"""
        if self._is_process_alive():
            return
        try:
            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            self._process = subprocess.Popen(
                [sys.executable, str(BACKEND_SCRIPT)],
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
            )
        except FileNotFoundError:
            print("[Backend] 找不到 main.py，请确认项目结构正确。")

    def stop(self) -> None:
        """停止后端服务"""
        if self._process is None:
            return
        try:
            self._process.terminate()
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=3)
        except Exception:
            pass
        finally:
            self._process = None

    def wait_until_ready(self, timeout: float = 15.0) -> bool:
        """轮询 /health 直到后端就绪；超时返回 False"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.is_running():
                return True
            time.sleep(0.5)
        return False

    def is_running(self) -> bool:
        """后端是否响应"""
        try:
            r = httpx.get(f"{BACKEND_URL}/health", timeout=2)
            return r.status_code == 200
        except (httpx.RequestError, httpx.HTTPStatusError):
            return False

    # ── 内部 ─────────────────────────────────────────────────────────────

    def _is_process_alive(self) -> bool:
        if self._process is None:
            return False
        return self._process.poll() is None

    def __del__(self):
        self.stop()


# ═══════════════════════════════════════════════════════════════════════
# API 客户端
# ═══════════════════════════════════════════════════════════════════════

class APIClient:
    """与后端 API 通信（线程安全）"""

    def __init__(self):
        self._client = httpx.Client(timeout=60.0)

    def get_config(self) -> dict:
        r = self._client.get(f"{BACKEND_URL}/config", timeout=5)
        r.raise_for_status()
        return r.json()

    def update_config(self, **kwargs) -> dict:
        r = self._client.post(f"{BACKEND_URL}/config", json=kwargs, timeout=5)
        r.raise_for_status()
        return r.json()

    def chat(self, payload: dict) -> dict:
        r = self._client.post(f"{BACKEND_URL}/chat", json=payload, timeout=180.0)
        r.raise_for_status()
        return r.json()

    def close(self):
        self._client.close()


# ═══════════════════════════════════════════════════════════════════════
# 设置对话框
# ═══════════════════════════════════════════════════════════════════════

class SettingsDialog(ctk.CTkToplevel):
    """API 配置设置弹窗"""

    def __init__(self, parent: ctk.CTk, api_client: APIClient):
        super().__init__(parent)
        self.api_client = api_client
        self.title("PURE-JADE 设置")
        self.geometry("520x420")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._current_config: dict = {}
        self._load_config()
        self._build_ui()

    # ── 构建 ─────────────────────────────────────────────────────────────

    def _load_config(self):
        try:
            self._current_config = self.api_client.get_config()
        except Exception:
            self._current_config = {
                "llm_api_key": "",
                "llm_base_url": "https://api.openai.com/v1",
                "llm_model": "gpt-4o-mini",
                "llm_use_json_mode": False,
            }

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        row = 0

        # ── API 密钥 ──
        ctk.CTkLabel(self, text="API 密钥", anchor="w",
                      font=ctk.CTkFont(size=13)).grid(row=row, column=0, sticky="w", padx=20, pady=(15, 0))
        row += 1
        self._key_entry = ctk.CTkEntry(self, show="*", height=35,
                                        font=ctk.CTkFont(size=13))
        self._key_entry.insert(0, self._current_config.get("llm_api_key", ""))
        self._key_entry.grid(row=row, column=0, sticky="ew", padx=20, pady=(3, 5))
        row += 1

        # ── API 地址 ──
        ctk.CTkLabel(self, text="API 地址", anchor="w",
                      font=ctk.CTkFont(size=13)).grid(row=row, column=0, sticky="w", padx=20, pady=(5, 0))
        row += 1
        self._url_entry = ctk.CTkEntry(self, height=35,
                                        font=ctk.CTkFont(size=13))
        self._url_entry.insert(0, self._current_config.get("llm_base_url", ""))
        self._url_entry.grid(row=row, column=0, sticky="ew", padx=20, pady=(3, 5))
        row += 1

        # ── 模型名 ──
        ctk.CTkLabel(self, text="模型名称", anchor="w",
                      font=ctk.CTkFont(size=13)).grid(row=row, column=0, sticky="w", padx=20, pady=(5, 0))
        row += 1
        self._model_entry = ctk.CTkEntry(self, height=35,
                                          font=ctk.CTkFont(size=13))
        self._model_entry.insert(0, self._current_config.get("llm_model", ""))
        self._model_entry.grid(row=row, column=0, sticky="ew", padx=20, pady=(3, 5))
        row += 1

        # ── JSON 模式 ──
        self._json_var = ctk.BooleanVar(value=self._current_config.get("llm_use_json_mode", False))
        ctk.CTkCheckBox(self, text="启用 JSON Mode（仅你的 API 支持时勾选）",
                         variable=self._json_var,
                         font=ctk.CTkFont(size=12)).grid(row=row, column=0, sticky="w", padx=20, pady=(10, 5))
        row += 1

        # ── 按钮 ──
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=row, column=0, pady=(20, 15))
        btn_frame.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(btn_frame, text="取消", width=100,
                       command=self.destroy).grid(row=0, column=0, padx=5)
        ctk.CTkButton(btn_frame, text="保存", width=100,
                       command=self._save).grid(row=0, column=1, padx=5)

    # ── 保存 ─────────────────────────────────────────────────────────────

    def _save(self):
        key = self._key_entry.get().strip()
        url = self._url_entry.get().strip()
        model = self._model_entry.get().strip()
        json_mode = self._json_var.get()

        # 构建只含非空字段的 payload
        payload = {}
        if key:
            payload["llm_api_key"] = key
        if url:
            payload["llm_base_url"] = url
        if model:
            payload["llm_model"] = model
        payload["llm_use_json_mode"] = json_mode

        try:
            self.api_client.update_config(**payload)
            self.destroy()
        except Exception as e:
            import tkinter.messagebox as mb
            mb.showerror("保存失败", f"无法更新后端配置：\n{e}")


# ═══════════════════════════════════════════════════════════════════════
# 主应用
# ═══════════════════════════════════════════════════════════════════════

class ChatApp(ctk.CTk):
    """PURE-JADE 对话客户端主窗口"""

    def __init__(self):
        super().__init__()

        self.title("PURE-JADE 情感支持AI")
        self.geometry("1000x720")
        self.minsize(800, 600)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # ── 对话状态 ──────────────────────────────────────────────────
        self._conversation_id: str = ""
        self._turn_id: int = 0
        self._dialogue_history: list[dict] = []  # {speaker, content}
        self._previous_snapshot: Optional[dict] = None
        self._is_waiting: bool = False

        # ── 服务 ──────────────────────────────────────────────────────
        self._backend = BackendManager()
        self._api = APIClient()

        # ── UI ────────────────────────────────────────────────────────
        self._build_ui()

        # ── 启动后端 ──────────────────────────────────────────────────
        self._start_backend_then_init()

    # ═══════════════════════════════════════════════════════════════════
    # UI 构建
    # ═══════════════════════════════════════════════════════════════════

    def _build_ui(self):
        """构建全部 UI 组件"""
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ── 顶栏 ──────────────────────────────────────────────────────
        top = ctk.CTkFrame(self, corner_radius=0, height=50)
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(3, weight=1)
        top.grid_propagate(False)

        ctk.CTkLabel(top, text="PURE-JADE  情感支持AI",
                      font=ctk.CTkFont(size=18, weight="bold")).grid(row=0, column=0, padx=(15, 5))

        self._status_dot = ctk.CTkLabel(top, text="●",
                                         text_color="gray",
                                         font=ctk.CTkFont(size=14))
        self._status_dot.grid(row=0, column=1, padx=2)

        self._status_text = ctk.CTkLabel(top, text="检查中…",
                                          font=ctk.CTkFont(size=12))
        self._status_text.grid(row=0, column=2, padx=(0, 5))

        self._settings_btn = ctk.CTkButton(top, text="⚙ 设置", width=80,
                                            command=self._open_settings)
        self._settings_btn.grid(row=0, column=3, padx=5, pady=8, sticky="e")

        self._new_btn = ctk.CTkButton(top, text="✚ 新对话", width=100,
                                       command=self._new_conversation)
        self._new_btn.grid(row=0, column=4, padx=(5, 15), pady=8)

        # ── 对话区 ────────────────────────────────────────────────────
        self._chat = ctk.CTkScrollableFrame(self, corner_radius=0)
        self._chat.grid(row=1, column=0, sticky="nsew", padx=10, pady=(5, 0))

        # ── 输入区 ────────────────────────────────────────────────────
        bottom = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        bottom.grid(row=2, column=0, sticky="ew", padx=10, pady=(5, 10))
        bottom.grid_columnconfigure(0, weight=1)

        self._input_box = ctk.CTkTextbox(bottom, height=60, wrap="word",
                                          font=ctk.CTkFont(size=14))
        self._input_box.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self._input_box.bind("<Return>", self._on_enter)
        self._input_box.bind("<Shift-Return>", self._on_shift_enter)

        self._send_btn = ctk.CTkButton(bottom, text="发送", width=80, height=60,
                                        command=self._send_message)
        self._send_btn.grid(row=0, column=1)

        # ── 底部状态栏 ─────────────────────────────────────────────────
        self._footer = ctk.CTkLabel(self, text="就绪",
                                     font=ctk.CTkFont(size=11), anchor="w")
        self._footer.grid(row=3, column=0, sticky="ew", padx=15, pady=2)

    # ═══════════════════════════════════════════════════════════════════
    # 后端生命周期
    # ═══════════════════════════════════════════════════════════════════

    def _start_backend_then_init(self):
        """异步启动后端，然后自动新建对话"""
        self._footer.configure(text="正在启动后端服务…")

        def _task():
            if not self._backend.is_running():
                self._backend.start()
                ready = self._backend.wait_until_ready(timeout=20)
            else:
                ready = True

            self.after(0, self._on_backend_ready, ready)

        threading.Thread(target=_task, daemon=True).start()

    def _on_backend_ready(self, ready: bool):
        if ready:
            self._set_status(True)
            self._footer.configure(text="后端已就绪")
            # 延迟半秒自动新建对话
            self.after(500, self._new_conversation)
        else:
            self._set_status(False)
            self._footer.configure(text="后端启动失败，请检查 main.py 是否能正常运行")
            self._show_system_message(
                "⚠️ 后端服务启动超时。请手动在终端运行 `python main.py` 后重试。"
            )

        # 定期健康检查
        self.after(3000, self._periodic_health_check)
        self.after(5000, self._periodic_health_check)

    def _periodic_health_check(self):
        running = self._backend.is_running()
        self._set_status(running)
        self.after(5000, self._periodic_health_check)

    def _set_status(self, running: bool):
        self._status_dot.configure(
            text_color=COLOR_STATUS_OK if running else COLOR_STATUS_ERR
        )
        self._status_text.configure(text="服务运行中" if running else "未连接")

    # ═══════════════════════════════════════════════════════════════════
    # 对话管理
    # ═══════════════════════════════════════════════════════════════════

    def _new_conversation(self):
        """重置对话状态，清空聊天区"""
        self._conversation_id = str(uuid.uuid4())[:8]
        self._turn_id = 0
        self._dialogue_history = []
        self._previous_snapshot = None
        self._is_waiting = False

        # 清空聊天区
        for w in self._chat.winfo_children():
            w.destroy()

        self._send_btn.configure(state="normal")
        self._input_box.configure(state="normal")
        self._input_box.delete("0.0", "end")
        self._input_box.focus()

        self._conversation_id_label = ctk.CTkLabel(
            self._chat, text=f"对话 {self._conversation_id}",
            font=ctk.CTkFont(size=11), text_color="gray"
        )
        self._conversation_id_label.pack(pady=(5, 0))

        self._show_system_message(
            "你好，我是 PURE-JADE 🤗\n"
            "请告诉我你最近的感受或困扰，我会倾听并提供情感支持。"
        )

        self._footer.configure(text=f"新对话已开始 │ {self._conversation_id}")

    def _open_settings(self):
        SettingsDialog(self, self._api)

    # ═══════════════════════════════════════════════════════════════════
    # 发送消息
    # ═══════════════════════════════════════════════════════════════════

    def _on_enter(self, event):
        """回车发送"""
        if not self._is_waiting:
            self._send_message()
        return "break"

    def _on_shift_enter(self, event):
        """Shift+回车换行"""
        self._input_box.insert("insert", "\n")
        return "break"

    def _send_message(self):
        """读取输入框内容并发送"""
        text = self._input_box.get("0.0", "end").strip()
        if not text:
            return

        if self._is_waiting:
            return

        if not self._backend.is_running():
            self._show_system_message("⚠️ 后端未运行，请联系开发者或手动启动 main.py")
            return

        # 清空输入框
        self._input_box.delete("0.0", "end")

        # 更新轮次
        self._turn_id += 1

        # 显示用户消息
        self._show_user_message(text)

        # 禁用发送
        self._is_waiting = True
        self._send_btn.configure(state="disabled", text="处理中…")
        self._footer.configure(text="正在生成回复…")

        # 发起请求（后台线程）
        threading.Thread(
            target=self._do_chat_request,
            args=(text,),
            daemon=True,
        ).start()

    def _do_chat_request(self, user_message: str):
        """在后台线程中调用 /chat"""
        try:
            payload = {
                "conversation_id": self._conversation_id,
                "turn_id": self._turn_id,
                "current_user_message": user_message,
                "dialogue_history": self._dialogue_history,
                "previous_state_snapshot": self._previous_snapshot,
            }

            result = self._api.chat(payload)

            # 更新对话状态
            self._dialogue_history.append({"speaker": "user", "content": user_message})
            self._dialogue_history.append({
                "speaker": "assistant",
                "content": result.get("ai_response", ""),
            })

            # 构建下一轮的 snapshot
            sc = result.get("state_card", {})
            self._previous_snapshot = {
                "turn_id": self._turn_id,
                "dialogue_summary": sc.get("problem_summary", ""),
                "user_state_card": sc,
                "risk_memory": sc.get("risk_memory", {
                    "highest_risk_level": sc.get("risk_level", "low"),
                    "risk_signals_seen": sc.get("risk_signals", []),
                    "safety_followup_needed": sc.get("risk_level") == "high",
                }),
                "open_questions": sc.get("unknowns", []),
            }

            # 回到主线程更新 UI
            self.after(0, self._on_chat_response, result)

        except httpx.HTTPStatusError as e:
            detail = ""
            try:
                detail = e.response.text[:200]
            except Exception:
                pass
            self.after(0, self._on_chat_error, f"HTTP {e.response.status_code}: {detail}")
        except httpx.RequestError as e:
            self.after(0, self._on_chat_error, f"网络错误：{e}")
        except Exception as e:
            self.after(0, self._on_chat_error, str(e))

    def _on_chat_response(self, result: dict):
        """处理成功的聊天响应"""
        ai_text = result.get("ai_response", "")
        state_card = result.get("state_card", {})

        # 显示 AI 回复
        self._show_ai_message(ai_text)

        # 显示状态卡
        if state_card:
            self._show_state_card(state_card)

        # 恢复输入
        self._is_waiting = False
        self._send_btn.configure(state="normal", text="发送")
        self._input_box.focus()

        self._footer.configure(
            text=f"第 {self._turn_id} 轮完成 │ {self._conversation_id}"
        )

    def _on_chat_error(self, error_msg: str):
        """处理错误"""
        self._show_system_message(f"⚠️ 请求失败：{error_msg}")

        self._is_waiting = False
        self._send_btn.configure(state="normal", text="发送")
        self._footer.configure(text="出错了，请重试")

    # ═══════════════════════════════════════════════════════════════════
    # 消息气泡渲染
    # ═══════════════════════════════════════════════════════════════════

    def _make_bubble(self, parent_frame, text: str, align: str,
                     bg: str, fg: str = "black") -> ctk.CTkFrame:
        """创建一条消息气泡"""
        anchor = "e" if align == "right" else "w"
        bubble = ctk.CTkFrame(parent_frame, corner_radius=12, fg_color=bg)
        bubble.pack(fill="x", padx=60 if align == "right" else 20,
                    pady=4, anchor=anchor)

        # 在气泡内加 padding
        inner = ctk.CTkFrame(bubble, fg_color=bg)
        inner.pack(fill="both", padx=12, pady=8)

        label = ctk.CTkLabel(inner, text=text, font=ctk.CTkFont(size=14),
                              wraplength=520, justify="left",
                              text_color=fg)
        label.pack(fill="x")

        return bubble

    def _show_user_message(self, text: str):
        now = datetime.now().strftime("%H:%M")
        bubble = self._make_bubble(self._chat, text, "right",
                                    COLOR_USER_BUBBLE)
        # 时间戳
        ctk.CTkLabel(bubble, text=now, font=ctk.CTkFont(size=10),
                      text_color="#666666").pack(anchor="e", padx=12, pady=(0, 4))
        self._scroll_to_bottom()

    def _show_ai_message(self, text: str):
        now = datetime.now().strftime("%H:%M")

        # 带名称的气泡（左对齐 + 名称）
        container = ctk.CTkFrame(self._chat, fg_color="transparent")
        container.pack(fill="x", padx=20, pady=2, anchor="w")

        name_label = ctk.CTkLabel(container, text="PURE-JADE",
                                   font=ctk.CTkFont(size=12, weight="bold"),
                                   text_color="#2B579A")
        name_label.pack(anchor="w", padx=(4, 0), pady=(4, 0))

        bubble = self._make_bubble(container, text, "left",
                                    COLOR_AI_BUBBLE)
        ctk.CTkLabel(bubble, text=now, font=ctk.CTkFont(size=10),
                      text_color="#666666").pack(anchor="w", padx=12, pady=(0, 4))

        self._scroll_to_bottom()

    def _show_state_card(self, card: dict):
        """在对话中显示用户状态卡"""
        container = ctk.CTkFrame(self._chat, fg_color="transparent")
        container.pack(fill="x", padx=40, pady=2, anchor="w")

        # 卡片框
        card_frame = ctk.CTkFrame(container, corner_radius=10,
                                   fg_color=COLOR_STATE_CARD_BG)
        card_frame.pack(fill="x", pady=2)

        # 标题
        ctk.CTkLabel(card_frame, text="📋 用户状态卡",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      text_color="#1A3C6E").pack(anchor="w", padx=14, pady=(10, 4))

        # 摘要
        emotion_list = card.get("emotion", [])
        intensity = card.get("emotion_intensity", "?")
        risk = card.get("risk_level", "?")
        stage = card.get("support_stage", "?")
        need_list = card.get("need", [])
        confidence = card.get("confidence", "?")
        problem = card.get("problem_summary", "")

        summary_lines = [
            f"情绪：{'、'.join(emotion_list) if emotion_list else '—'}　强度：{intensity}/5",
            f"风险：{risk}　  阶段：{stage}",
            f"需求：{'、'.join(need_list) if need_list else '—'}",
        ]
        if problem:
            summary_lines.insert(0, f"困境：{problem}")

        summary_text = "\n".join(summary_lines)
        ctk.CTkLabel(card_frame, text=summary_text,
                      font=ctk.CTkFont(size=12),
                      text_color="#333333", justify="left",
                      anchor="w").pack(anchor="w", padx=14, pady=2)

        # 分隔线
        ctk.CTkFrame(card_frame, height=1, fg_color="#CCCCCC"
                     ).pack(fill="x", padx=14, pady=6)

        # 完整 JSON
        json_text = json.dumps(card, ensure_ascii=False, indent=2)
        line_count = json_text.count("\n") + 1
        json_height = min(line_count * 18 + 10, 350)

        json_box = ctk.CTkTextbox(card_frame, height=json_height,
                                   font=ctk.CTkFont(size=11, family="Consolas"),
                                   fg_color="#F8FAFF", activate_scrollbars=False)
        json_box.insert("1.0", json_text)
        json_box.configure(state="disabled")
        json_box.pack(fill="x", padx=14, pady=(0, 10))

        self._scroll_to_bottom()

    def _show_system_message(self, text: str):
        """显示系统消息（居中）"""
        label = ctk.CTkLabel(self._chat, text=text,
                              font=ctk.CTkFont(size=13),
                              text_color="#555555", justify="center",
                              wraplength=500)
        label.pack(pady=12, anchor="center")
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        """滚动对话区到底部"""
        self._chat.update_idletasks()
        try:
            self._chat._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════════════
    # 关闭
    # ═══════════════════════════════════════════════════════════════════

    def _on_close(self):
        self._backend.stop()
        self._api.close()
        self.destroy()

    def run(self):
        self.mainloop()


# ═══════════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = ChatApp()
    app.run()
