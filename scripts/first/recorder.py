"""
PURE-JADE 情感支持AI — 对话记录保存器（JSON 格式）

将每轮对话和状态卡以 JSON 格式保存到 data/conversations/ 目录下。
遵循 new_stategy.md 中 conversation_record 的数据结构。

记录层级：
  data/
    conversations/
      <conversation_id>.json   # 每段对话一个 JSON 文件
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional

# 数据根目录（与主文件夹分离）
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CONVERSATIONS_DIR = os.path.join(DATA_DIR, "conversations")


# ---------------------------------------------------------------------------
# 路径与目录
# ---------------------------------------------------------------------------


def _ensure_dirs():
    """确保数据目录结构存在"""
    os.makedirs(CONVERSATIONS_DIR, exist_ok=True)


def _record_path(conversation_id: str) -> str:
    """获取某个对话的 JSON 记录文件路径"""
    _ensure_dirs()
    # 文件名安全处理
    safe_id = conversation_id.replace("/", "_").replace("\\", "_")
    return os.path.join(CONVERSATIONS_DIR, f"{safe_id}.json")


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------


def conversation_exists(conversation_id: str) -> bool:
    """检查该对话是否已有本地记录"""
    return os.path.exists(_record_path(conversation_id))


def get_existing_turns(conversation_id: str) -> set[int]:
    """读取已有记录中的轮次号集合"""
    path = _record_path(conversation_id)
    if not os.path.exists(path):
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {turn["turn_id"] for turn in data.get("turn_records", []) if "turn_id" in turn}
    except (json.JSONDecodeError, KeyError, ValueError):
        return set()


# ---------------------------------------------------------------------------
# 创建与追加
# ---------------------------------------------------------------------------


def _build_blank_record(
    conversation_id: str,
    schema_version: str,
) -> dict:
    """创建一份空的 conversation_record 骨架"""
    now = datetime.now().isoformat()
    return {
        "conversation_id": conversation_id,
        "schema_version": schema_version,
        "created_at": now,
        "updated_at": now,
        "current_turn_id": 0,
        "dialogue_log": [],
        "turn_records": [],
        "current_state": {
            "dialogue_summary": "",
            "user_state_card": {},
            "risk_memory": {
                "highest_risk_level": "low",
                "risk_signals_seen": [],
                "safety_followup_needed": False,
            },
            "open_questions": [],
        },
    }


def create_conversation_record(
    conversation_id: str,
    schema_version: str = "0.2",
) -> None:
    """创建新的对话记录文件（JSON 格式）"""
    path = _record_path(conversation_id)
    if os.path.exists(path):
        return  # 文件已存在，不覆盖

    record = _build_blank_record(conversation_id, schema_version)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    print(f"[Recorder] 创建对话记录: {path}")


def append_turn(
    conversation_id: str,
    turn_id: int,
    user_message: str,
    state_card: dict,
    ai_response: Optional[str] = None,
) -> None:
    """向对话记录追加一轮内容"""
    path = _record_path(conversation_id)

    # 如果文件还不存在，先创建
    if not os.path.exists(path):
        create_conversation_record(conversation_id)

    # 读取现有记录
    with open(path, "r", encoding="utf-8") as f:
        record = json.load(f)

    now = datetime.now().isoformat()

    # ── 追加到 dialogue_log ──────────────────────────────────────────
    record.setdefault("dialogue_log", [])
    record["dialogue_log"].append({
        "turn_id": turn_id,
        "speaker": "user",
        "content": user_message,
        "timestamp": now,
    })
    if ai_response:
        record["dialogue_log"].append({
            "turn_id": turn_id,
            "speaker": "assistant",
            "content": ai_response,
            "timestamp": now,
        })

    # ── 追加到 turn_records ──────────────────────────────────────────
    record.setdefault("turn_records", [])
    turn_record: dict = {
        "turn_id": turn_id,
        "user_message": user_message,
        "user_state_card": state_card,
        "generated_at": now,
    }
    if ai_response:
        turn_record["ai_response"] = ai_response
    record["turn_records"].append(turn_record)

    # ── 更新 current_state ───────────────────────────────────────────
    record.setdefault("current_state", {})
    record["current_state"]["user_state_card"] = state_card
    if "problem_summary" in state_card:
        record["current_state"]["dialogue_summary"] = state_card["problem_summary"]
    if "risk_memory" in state_card:
        record["current_state"]["risk_memory"] = state_card["risk_memory"]
    if "open_questions" in state_card:
        record["current_state"]["open_questions"] = state_card["open_questions"]

    # ── 更新元信息 ───────────────────────────────────────────────────
    record["current_turn_id"] = turn_id
    record["updated_at"] = now

    # ── 写回文件 ─────────────────────────────────────────────────────
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    print(f"[Recorder] 已追加第 {turn_id} 轮到 {path}")
