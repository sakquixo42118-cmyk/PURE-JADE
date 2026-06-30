"""
PURE-JADE 情感支持AI — v0.2.1 conversation_record 保存器

本副本遵循 docs/schema-v0.2.1.md：完整历史保存在 dialogue_log 与
turn_records 中；下一轮快速读取的信息保存在 current_state 中。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CONVERSATIONS_DIR = os.path.join(DATA_DIR, "conversations")


# ---------------------------------------------------------------------------
# 路径与目录
# ---------------------------------------------------------------------------


def _ensure_dirs() -> None:
    """确保数据目录结构存在。"""
    os.makedirs(CONVERSATIONS_DIR, exist_ok=True)


def _record_path(conversation_id: str) -> str:
    """获取某个对话的 JSON 记录文件路径。"""
    _ensure_dirs()
    safe_id = conversation_id.replace("/", "_").replace("\\", "_")
    return os.path.join(CONVERSATIONS_DIR, f"{safe_id}.json")


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------


def conversation_exists(conversation_id: str) -> bool:
    """检查该对话是否已有本地记录。"""
    return os.path.exists(_record_path(conversation_id))


def load_conversation_record(conversation_id: str) -> dict:
    """读取完整 conversation_record；不存在时返回空骨架。"""
    path = _record_path(conversation_id)
    if not os.path.exists(path):
        return _build_blank_record(conversation_id, "0.2.1")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_existing_turns(conversation_id: str) -> set[int]:
    """读取已有记录中的轮次号集合。"""
    try:
        data = load_conversation_record(conversation_id)
        return {turn["turn_id"] for turn in data.get("turn_records", []) if "turn_id" in turn}
    except (json.JSONDecodeError, KeyError, ValueError):
        return set()


def get_current_state_snapshot(conversation_id: str) -> Optional[dict]:
    """从 current_state 构造下一轮 previous_state_snapshot。"""
    if not conversation_exists(conversation_id):
        return None
    record = load_conversation_record(conversation_id)
    current_state = record.get("current_state") or {}
    user_state_card = current_state.get("user_state_card") or {}
    if not user_state_card:
        return None
    return {
        "turn_id": user_state_card.get("turn_id", record.get("current_turn_id", 0)),
        "dialogue_summary": current_state.get("dialogue_summary", ""),
        "user_state_card": user_state_card,
        "risk_memory": current_state.get("risk_memory", _default_risk_memory()),
        "open_questions": current_state.get("open_questions", []),
    }


# ---------------------------------------------------------------------------
# 创建与追加
# ---------------------------------------------------------------------------


def _default_risk_memory() -> dict:
    return {
        "highest_risk_level": "low",
        "risk_signals_seen": [],
        "safety_followup_needed": False,
    }


def _build_blank_record(
    conversation_id: str,
    schema_version: str,
) -> dict:
    """创建一份空的 conversation_record 骨架。"""
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
            "risk_memory": _default_risk_memory(),
            "open_questions": [],
        },
    }


def create_conversation_record(
    conversation_id: str,
    schema_version: str = "0.2.1",
) -> None:
    """创建新的对话记录文件（JSON 格式）。"""
    path = _record_path(conversation_id)
    if os.path.exists(path):
        return

    record = _build_blank_record(conversation_id, schema_version)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    print(f"[Recorder] 创建 v0.2.1 对话记录: {path}")


def _upsert_dialogue_entry(dialogue_log: list[dict], entry: dict) -> None:
    """按 turn_id + speaker + content 去重追加原始对话。"""
    key = (entry.get("turn_id"), entry.get("speaker"), entry.get("content"))
    for existing in dialogue_log:
        existing_key = (existing.get("turn_id"), existing.get("speaker"), existing.get("content"))
        if existing_key == key:
            return
    dialogue_log.append(entry)


def _summary_from_state(state_card: dict) -> str:
    return state_card.get("dialogue_summary") or state_card.get("problem_summary") or ""


def _open_questions_from_state(state_card: dict) -> list[str]:
    values = state_card.get("open_questions") or state_card.get("unknowns") or []
    return values if isinstance(values, list) else []


def append_turn(
    conversation_id: str,
    turn_id: int,
    user_message: str,
    state_card: dict,
    ai_response: Optional[str] = None,
    state_update_request: Optional[dict] = None,
) -> None:
    """向 conversation_record 追加一轮内容。"""
    path = _record_path(conversation_id)

    if not os.path.exists(path):
        create_conversation_record(conversation_id)

    with open(path, "r", encoding="utf-8") as f:
        record = json.load(f)

    now = datetime.now().isoformat()

    # ── 追加到 dialogue_log ──────────────────────────────────────────
    record.setdefault("dialogue_log", [])
    _upsert_dialogue_entry(
        record["dialogue_log"],
        {
            "turn_id": turn_id,
            "speaker": "user",
            "content": user_message,
            "timestamp": now,
        },
    )
    if ai_response:
        _upsert_dialogue_entry(
            record["dialogue_log"],
            {
                "turn_id": turn_id,
                "speaker": "assistant",
                "content": ai_response,
                "timestamp": now,
            },
        )

    # ── 追加到 turn_records ──────────────────────────────────────────
    record.setdefault("turn_records", [])
    turn_record: dict = {
        "turn_id": turn_id,
        "state_update_request": state_update_request or {},
        "user_state_card": state_card,
        "generated_at": now,
    }
    if ai_response:
        turn_record["behavior_response_card"] = {
            "text_response": ai_response,
            "schema_version": "0.2",
        }
    record["turn_records"].append(turn_record)

    # ── 更新 current_state ───────────────────────────────────────────
    record.setdefault("current_state", {})
    record["current_state"]["dialogue_summary"] = _summary_from_state(state_card)
    record["current_state"]["user_state_card"] = state_card
    record["current_state"]["risk_memory"] = state_card.get("risk_memory", _default_risk_memory())
    record["current_state"]["open_questions"] = _open_questions_from_state(state_card)

    # ── 更新元信息 ───────────────────────────────────────────────────
    record["schema_version"] = "0.2.1"
    record["current_turn_id"] = turn_id
    record["updated_at"] = now

    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    print(f"[Recorder] 已追加第 {turn_id} 轮到 {path}")