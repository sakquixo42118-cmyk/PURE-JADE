"""
PURE-JADE 情感支持AI — 第一部分 v0.2.1 边界副本

这个副本只在 scripts/first_v021_boundary_copy 下工作，不修改原 scripts/first。
它把状态更新输入统一为 state_update_request，并把本地记录保存为
schema-v0.2.1 的 conversation_record。
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Optional

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

from models import (
    ChatRequest,
    ChatResponse,
    DialogueEntry,
    ErrorResponse,
    PreviousStateSnapshot,
    ServerConfig,
    StateCardRequest,
    StateCardResponse,
    StateUpdatePolicy,
)
from recorder import (
    append_turn,
    conversation_exists,
    create_conversation_record,
    get_existing_turns,
)

# ---------------------------------------------------------------------------
# 环境变量
# ---------------------------------------------------------------------------

load_dotenv()

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

_RUNTIME_CONFIG: dict = {
    "llm_api_key": os.getenv("LLM_API_KEY", ""),
    "llm_base_url": os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
    "llm_model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
    "llm_use_json_mode": os.getenv("LLM_USE_JSON_MODE", "false").lower() == "true",
}


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

ALLOWED_EMOTIONS = [
    "平静",
    "焦虑",
    "沮丧",
    "愤怒",
    "羞耻",
    "孤独",
    "疲惫",
    "自我怀疑",
    "无助",
    "困惑",
    "压力",
    "其他",
]
ALLOWED_NEEDS = [
    "被理解",
    "被肯定",
    "情绪陪伴",
    "信息澄清",
    "解决方案",
    "事实资源",
    "安全支持",
    "表达空间",
    "其他",
]
ALLOWED_SUPPORT_STAGES = ["exploration", "comforting", "action", "safety_override"]
ALLOWED_RISK_LEVELS = ["low", "medium", "high"]
ALLOWED_RISK_SIGNALS = ["self_harm", "suicide", "violence", "abuse", "crisis"]
RISK_RANK = {"low": 0, "medium": 1, "high": 2}


# ---------------------------------------------------------------------------
# 运行时配置
# ---------------------------------------------------------------------------


def get_runtime_config() -> dict:
    """获取运行时配置副本。"""
    return dict(_RUNTIME_CONFIG)


def update_runtime_config(**kwargs) -> None:
    """更新运行时配置（仅更新显式传入的键）。"""
    allowed = {"llm_api_key", "llm_base_url", "llm_model", "llm_use_json_mode"}
    for key, value in kwargs.items():
        if value is not None and key in allowed:
            _RUNTIME_CONFIG[key] = value


# ---------------------------------------------------------------------------
# 系统提示词
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """你是 PURE-JADE 项目的第一部分：用户状态更新模块。

你的任务是根据 state_update_request 生成一张完整的 v0.2 用户状态卡。你只负责状态感知和状态更新，不生成策略决策，也不生成最终回复。

必须遵守：
1. 只输出一个合法 JSON 对象，不要输出 Markdown、解释文字或代码块。
2. 输出 schema_version 必须为 "0.2"。
3. 输出必须包含以下字段：
   conversation_id, turn_id, previous_turn_id, schema_version,
   dialogue_summary, state_update_type, problem_summary,
   emotion, emotion_intensity, need, support_stage, risk_level,
   risk_signals, evidence, unknowns, carried_over_facts,
   new_evidence, revised_fields, open_questions, risk_memory, confidence。
4. dialogue_summary 是到当前轮为止的短摘要，由你维护；它不是 problem_summary。problem_summary 只概括当前核心困境。
5. state_update_type 只能是 initial, carry_over, revised, risk_escalation, risk_deescalation。
6. emotion 只能从以下标签选择：平静、焦虑、沮丧、愤怒、羞耻、孤独、疲惫、自我怀疑、无助、困惑、压力、其他。
7. emotion_intensity 使用 0-3：0 无明显情绪，1 轻微，2 中等，3 强烈；high risk 时不得低于 3。
8. need 只能从以下标签选择：被理解、被肯定、情绪陪伴、信息澄清、解决方案、事实资源、安全支持、表达空间、其他。
9. support_stage 只能是 exploration, comforting, action, safety_override。
10. risk_level 只能是 low, medium, high。risk_signals 只能使用 self_harm, suicide, violence, abuse, crisis。
11. evidence 和 new_evidence 必须来自当前用户原话或最近对话窗口，不能编造。
12. revised_fields 只有在当前轮有明确证据修正上一轮状态时填写；否则输出空数组。
13. carried_over_facts 用来说明从 previous_state_snapshot 延续下来的事实或判断。
14. open_questions 用来保存后续仍需要澄清的问题，并继承上一轮仍未回答的问题。
15. risk_memory 必须包含 highest_risk_level, risk_signals_seen, safety_followup_needed。

风险优先规则：
- 出现明确自杀、自伤、伤害他人、虐待、暴力、现实危机时，risk_level 必须为 high，support_stage 必须为 safety_override，need 必须包含 安全支持。
- 如果 previous_state_snapshot.risk_memory.highest_risk_level 曾为 high，不能因为用户转移话题就删除风险记忆。
- 若风险下降，只能在有明确安全确认时使用 risk_deescalation，并仍保留 risk_memory 中的历史风险信号。

更新规则：
- 首轮 previous_state_snapshot 为 null，state_update_type 使用 initial。
- 非首轮必须读取 previous_state_snapshot，不要依赖模型自由记忆。
- 当 update_policy.require_evidence_for_revision 为 true 时，只有当前轮有明确证据时才允许修改 risk_level、support_stage、emotion 等核心字段。
- 不进行医学或心理诊断，不编造用户未陈述的事实、成员姓名、导师要求、实验结果或结论。
"""

CHAT_SYSTEM_PROMPT = """你是 PURE-JADE，一个温暖、专业的情感支持 AI 助手。

- 你通过对话为用户提供情感支持，不是心理治疗师。
- 不进行医学或心理诊断，不提供医疗建议。
- 先确认和理解用户的情绪，再回应内容。
- 回复保持 2-4 句话，温和、自然、不评判。
- 识别严重风险时，引导用户联系现实中的可信任的人或紧急支持。
"""


# ---------------------------------------------------------------------------
# FastAPI 应用
# ---------------------------------------------------------------------------

app = FastAPI(
    title="PURE-JADE 用户状态卡生成 API v0.2.1 副本",
    description="基于 Schema v0.2.1 状态更新请求和 conversation_record 的第一部分副本",
    version="0.2.1-boundary-copy",
)


# ---------------------------------------------------------------------------
# 请求构造
# ---------------------------------------------------------------------------


def _entry_to_dict(entry: DialogueEntry) -> dict:
    data = {"speaker": entry.speaker, "content": entry.content}
    if entry.turn_id is not None:
        data["turn_id"] = entry.turn_id
    return data


def _snapshot_to_dict(snapshot: Optional[PreviousStateSnapshot]) -> Optional[dict]:
    if snapshot is None:
        return None
    return {
        "turn_id": snapshot.turn_id,
        "dialogue_summary": snapshot.dialogue_summary,
        "user_state_card": snapshot.user_state_card,
        "risk_memory": snapshot.risk_memory,
        "open_questions": snapshot.open_questions,
    }


def _policy_to_dict(policy: StateUpdatePolicy) -> dict:
    return {
        "max_summary_chars": policy.max_summary_chars,
        "max_recent_turns": policy.max_recent_turns,
        "preserve_risk_memory": policy.preserve_risk_memory,
        "require_evidence_for_revision": policy.require_evidence_for_revision,
    }


def _build_state_update_request_payload(
    conversation_id: str,
    turn_id: int,
    current_user_message: str,
    recent_dialogue_window: list[DialogueEntry],
    previous_state_snapshot: Optional[PreviousStateSnapshot],
    update_policy: StateUpdatePolicy,
) -> dict:
    max_recent = max(update_policy.max_recent_turns, 1) * 2 + 1
    recent_window = [_entry_to_dict(item) for item in recent_dialogue_window[-max_recent:]]
    recent_window.append({"turn_id": turn_id, "speaker": "user", "content": current_user_message})
    return {
        "conversation_id": conversation_id,
        "turn_id": turn_id,
        "schema_version": "0.2.1",
        "current_user_message": current_user_message,
        "previous_state_snapshot": _snapshot_to_dict(previous_state_snapshot),
        "recent_dialogue_window": recent_window,
        "update_policy": _policy_to_dict(update_policy),
    }


def _build_state_update_user_message(state_update_request: dict) -> str:
    return (
        "请根据以下 state_update_request 生成 updated_user_state_card。\n\n"
        "[state_update_request]\n"
        f"{json.dumps(state_update_request, ensure_ascii=False, indent=2)}\n\n"
        "[输出要求]\n"
        "只输出一张完整 v0.2 user_state_card JSON，不要输出 Markdown 或解释文字。"
    )


def _format_history(history: list[DialogueEntry]) -> str:
    """将对话窗口格式化为可读文本。"""
    if not history:
        return "（无）"
    lines = []
    for entry in history:
        speaker_label = "用户" if entry.speaker == "user" else "系统"
        prefix = f"第{entry.turn_id}轮" if entry.turn_id is not None else "最近"
        lines.append(f"  {prefix} {speaker_label}：{entry.content}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM 调用与 JSON 解析
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> Optional[dict]:
    """从 LLM 回复中提取并解析 JSON 对象。"""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def _call_llm_raw(messages: list[dict], temperature: float = 0.1) -> str:
    """调用 LLM API 并返回原始回复文本。"""
    cfg = get_runtime_config()
    body = {
        "model": cfg["llm_model"],
        "messages": messages,
        "temperature": temperature,
    }
    if cfg["llm_use_json_mode"]:
        body["response_format"] = {"type": "json_object"}

    headers = {
        "Authorization": f"Bearer {cfg['llm_api_key']}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{cfg['llm_base_url'].rstrip('/')}/chat/completions",
                headers=headers,
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as error:
        detail = ""
        try:
            detail = f"，响应内容：{error.response.text[:300]}"
        except Exception:
            pass
        raise RuntimeError(f"LLM API 返回错误 (HTTP {error.response.status_code}){detail}")
    except httpx.RequestError as error:
        raise RuntimeError(f"LLM API 请求失败（网络错误）：{error}")
    except Exception as error:
        raise RuntimeError(f"LLM API 调用失败：{error}")

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(
            "LLM 返回格式异常，无法提取回复内容。原始响应：\n"
            f"{json.dumps(data, ensure_ascii=False)[:500]}"
        )

    if not content or not content.strip():
        raise RuntimeError("LLM 返回了空内容")
    return content


def _call_llm(messages: list[dict]) -> dict:
    """调用 LLM API 并返回解析后的 JSON 对象。"""
    content = _call_llm_raw(messages, temperature=0.1)
    result = _extract_json(content)
    if result is None:
        raise RuntimeError(f"LLM 返回了非 JSON 内容，无法解析。原始内容：\n{content[:500]}")
    return result


def _call_llm_text(messages: list[dict]) -> str:
    """调用 LLM API 并返回纯文本回复。"""
    return _call_llm_raw(messages, temperature=0.7)


# ---------------------------------------------------------------------------
# 状态卡规范化与校验
# ---------------------------------------------------------------------------


def _as_list(value) -> list:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _filter_allowed(values, allowed: list[str], fallback: list[str]) -> list[str]:
    filtered = [item for item in _as_list(values) if isinstance(item, str) and item in allowed]
    return filtered or fallback


def _default_risk_memory() -> dict:
    return {
        "highest_risk_level": "low",
        "risk_signals_seen": [],
        "safety_followup_needed": False,
    }


def _highest_risk(*levels: str) -> str:
    valid = [level for level in levels if level in RISK_RANK]
    if not valid:
        return "low"
    return max(valid, key=lambda item: RISK_RANK[item])


def _build_risk_memory(state_card: dict, previous_snapshot: Optional[PreviousStateSnapshot]) -> dict:
    previous = previous_snapshot.risk_memory if previous_snapshot else _default_risk_memory()
    current_risk = state_card.get("risk_level", "low")
    highest = _highest_risk(previous.get("highest_risk_level", "low"), current_risk)
    signals_seen = []
    for signal in _as_list(previous.get("risk_signals_seen")) + _as_list(state_card.get("risk_signals")):
        if isinstance(signal, str) and signal in ALLOWED_RISK_SIGNALS and signal not in signals_seen:
            signals_seen.append(signal)
    return {
        "highest_risk_level": highest,
        "risk_signals_seen": signals_seen,
        "safety_followup_needed": bool(previous.get("safety_followup_needed")) or highest == "high",
    }


def _infer_state_update_type(state_card: dict, previous_snapshot: Optional[PreviousStateSnapshot]) -> str:
    if previous_snapshot is None:
        return "initial"
    previous_risk = previous_snapshot.user_state_card.get("risk_level", "low")
    current_risk = state_card.get("risk_level", "low")
    if RISK_RANK.get(current_risk, 0) > RISK_RANK.get(previous_risk, 0):
        return "risk_escalation"
    if RISK_RANK.get(current_risk, 0) < RISK_RANK.get(previous_risk, 0):
        return "risk_deescalation"
    if state_card.get("revised_fields"):
        return "revised"
    return "carry_over"


def _fallback_dialogue_summary(state_card: dict, previous_snapshot: Optional[PreviousStateSnapshot], current_user_message: str) -> str:
    if isinstance(state_card.get("dialogue_summary"), str) and state_card["dialogue_summary"].strip():
        return state_card["dialogue_summary"].strip()
    if previous_snapshot and previous_snapshot.dialogue_summary:
        problem = state_card.get("problem_summary") or current_user_message
        return f"{previous_snapshot.dialogue_summary} 当前轮补充：{problem}"
    return state_card.get("problem_summary") or current_user_message[:120]


def _normalize_state_card(
    state_card: dict,
    state_update_request: dict,
    previous_snapshot: Optional[PreviousStateSnapshot],
) -> dict:
    """补齐 v0.2 用户状态卡必需字段，并同步风险记忆。"""
    turn_id = int(state_update_request["turn_id"])
    current_user_message = state_update_request["current_user_message"]
    update_policy = state_update_request.get("update_policy", {})
    max_summary_chars = int(update_policy.get("max_summary_chars", 180))

    state_card["conversation_id"] = state_update_request["conversation_id"]
    state_card["turn_id"] = turn_id
    state_card["previous_turn_id"] = None if previous_snapshot is None else previous_snapshot.turn_id
    state_card["schema_version"] = "0.2"

    risk_level = state_card.get("risk_level") if state_card.get("risk_level") in ALLOWED_RISK_LEVELS else "low"
    state_card["risk_level"] = risk_level
    state_card["risk_signals"] = _filter_allowed(state_card.get("risk_signals"), ALLOWED_RISK_SIGNALS, [])

    support_stage = state_card.get("support_stage") if state_card.get("support_stage") in ALLOWED_SUPPORT_STAGES else "exploration"
    state_card["support_stage"] = support_stage

    state_card["emotion"] = _filter_allowed(state_card.get("emotion"), ALLOWED_EMOTIONS, ["其他"])
    state_card["need"] = _filter_allowed(state_card.get("need"), ALLOWED_NEEDS, ["被理解"])
    state_card["evidence"] = [item for item in _as_list(state_card.get("evidence")) if isinstance(item, str)] or [current_user_message]
    state_card["unknowns"] = [item for item in _as_list(state_card.get("unknowns")) if isinstance(item, str)]
    state_card["new_evidence"] = [item for item in _as_list(state_card.get("new_evidence")) if isinstance(item, str)] or state_card["evidence"][:3]
    state_card["open_questions"] = [item for item in _as_list(state_card.get("open_questions")) if isinstance(item, str)] or state_card["unknowns"]
    state_card["revised_fields"] = [item for item in _as_list(state_card.get("revised_fields")) if isinstance(item, dict)]

    if previous_snapshot is None:
        state_card["carried_over_facts"] = []
    else:
        carried = [item for item in _as_list(state_card.get("carried_over_facts")) if isinstance(item, str)]
        if not carried:
            prev_card = previous_snapshot.user_state_card
            carried = [prev_card.get("problem_summary") or previous_snapshot.dialogue_summary]
        state_card["carried_over_facts"] = [item for item in carried if item]

    summary = _fallback_dialogue_summary(state_card, previous_snapshot, current_user_message)
    state_card["dialogue_summary"] = summary[:max_summary_chars]
    state_card.setdefault("problem_summary", current_user_message[:120])
    state_card["state_update_type"] = state_card.get("state_update_type") or _infer_state_update_type(state_card, previous_snapshot)

    try:
        intensity = int(state_card.get("emotion_intensity", 1))
    except (TypeError, ValueError):
        intensity = 1
    if risk_level == "high":
        intensity = max(intensity, 3)
        state_card["support_stage"] = "safety_override"
        if "安全支持" not in state_card["need"]:
            state_card["need"].append("安全支持")
    state_card["emotion_intensity"] = min(max(intensity, 0), 3)

    state_card["risk_memory"] = _build_risk_memory(state_card, previous_snapshot)
    state_card.setdefault("confidence", 0.75)
    return state_card


# ---------------------------------------------------------------------------
# 聊天消息构建
# ---------------------------------------------------------------------------


def _build_chat_messages(
    user_message: str,
    history: list[DialogueEntry],
    is_first_turn: bool,
) -> list[dict]:
    """构建用于生成情感支持回复的消息列表。"""
    messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]
    if not is_first_turn:
        for entry in history:
            role = "user" if entry.speaker == "user" else "assistant"
            messages.append({"role": role, "content": entry.content})
    messages.append({"role": "user", "content": user_message})
    return messages


# ---------------------------------------------------------------------------
# API 端点
# ---------------------------------------------------------------------------


@app.get("/health", tags=["系统"])
async def health_check():
    """健康检查。"""
    cfg = get_runtime_config()
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "model": cfg["llm_model"],
        "api_base": cfg["llm_base_url"],
        "schema_version": "0.2.1",
    }


@app.get("/config", tags=["系统"])
async def get_config():
    """获取当前运行时配置（API 密钥脱敏）。"""
    cfg = get_runtime_config()
    display = dict(cfg)
    key = display.get("llm_api_key", "")
    if key and len(key) > 8:
        display["llm_api_key"] = key[:4] + "****" + key[-4:]
    elif key:
        display["llm_api_key"] = "****"
    else:
        display["llm_api_key"] = ""
    return display


@app.post("/config", tags=["系统"])
async def update_config(config: ServerConfig):
    """更新运行时配置（只更新显式传入的字段）。"""
    updates = {}
    if config.llm_api_key is not None:
        updates["llm_api_key"] = config.llm_api_key
    if config.llm_base_url is not None:
        updates["llm_base_url"] = config.llm_base_url.rstrip("/")
    if config.llm_model is not None:
        updates["llm_model"] = config.llm_model
    if config.llm_use_json_mode is not None:
        updates["llm_use_json_mode"] = config.llm_use_json_mode
    if updates:
        update_runtime_config(**updates)
    return {"status": "ok", "updated": list(updates.keys())}


@app.post(
    "/generate_state_card",
    response_model=StateCardResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["状态卡生成"],
)
async def generate_state_card(request: StateCardRequest):
    """根据 state_update_request 生成用户状态卡。"""
    conversation_id = request.conversation_id
    turn_id = request.turn_id
    is_first_turn = request.previous_state_snapshot is None

    if conversation_exists(conversation_id):
        existing_turns = get_existing_turns(conversation_id)
        if turn_id in existing_turns:
            raise HTTPException(status_code=400, detail=f"第 {turn_id} 轮状态卡已存在，请勿重复生成")

    state_update_request = _build_state_update_request_payload(
        conversation_id=conversation_id,
        turn_id=turn_id,
        current_user_message=request.current_user_message,
        recent_dialogue_window=request.recent_dialogue_window,
        previous_state_snapshot=request.previous_state_snapshot,
        update_policy=request.update_policy,
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_state_update_user_message(state_update_request)},
    ]

    try:
        state_card = _call_llm(messages)
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error))

    state_card = _normalize_state_card(state_card, state_update_request, request.previous_state_snapshot)

    if not conversation_exists(conversation_id):
        create_conversation_record(conversation_id)

    append_turn(
        conversation_id=conversation_id,
        turn_id=turn_id,
        user_message=request.current_user_message,
        state_card=state_card,
        ai_response=request.ai_response,
        state_update_request=state_update_request,
    )

    print(f"[API v0.2.1] 对话 {conversation_id} 第 {turn_id} 轮状态卡已生成")
    return StateCardResponse(
        conversation_id=conversation_id,
        turn_id=turn_id,
        schema_version="0.2",
        state_card=state_card,
        is_first_turn=is_first_turn,
    )


@app.post(
    "/chat",
    response_model=ChatResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["对话"],
)
async def chat(request: ChatRequest):
    """情感支持对话（一体化端点）。"""
    conversation_id = request.conversation_id
    turn_id = request.turn_id
    is_first_turn = request.previous_state_snapshot is None

    chat_messages = _build_chat_messages(
        user_message=request.current_user_message,
        history=request.recent_dialogue_window,
        is_first_turn=is_first_turn,
    )
    try:
        ai_response = _call_llm_text(chat_messages)
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=f"生成回复失败：{error}")

    update_policy = StateUpdatePolicy()
    state_update_request = _build_state_update_request_payload(
        conversation_id=conversation_id,
        turn_id=turn_id,
        current_user_message=request.current_user_message,
        recent_dialogue_window=request.recent_dialogue_window,
        previous_state_snapshot=request.previous_state_snapshot,
        update_policy=update_policy,
    )
    state_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_state_update_user_message(state_update_request)},
    ]
    try:
        state_card = _call_llm(state_messages)
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=f"生成状态卡失败：{error}")

    state_card = _normalize_state_card(state_card, state_update_request, request.previous_state_snapshot)

    if not conversation_exists(conversation_id):
        create_conversation_record(conversation_id)

    append_turn(
        conversation_id=conversation_id,
        turn_id=turn_id,
        user_message=request.current_user_message,
        state_card=state_card,
        ai_response=ai_response,
        state_update_request=state_update_request,
    )

    print(f"[Chat v0.2.1] 对话 {conversation_id} 第 {turn_id} 轮完成")
    return ChatResponse(
        conversation_id=conversation_id,
        turn_id=turn_id,
        ai_response=ai_response,
        state_card=state_card,
        is_first_turn=is_first_turn,
    )


# ---------------------------------------------------------------------------
# 启动入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cfg = get_runtime_config()
    missing_key = not cfg["llm_api_key"] or cfg["llm_api_key"] == "your-api-key-here"
    if missing_key:
        print("[启动警告] LLM_API_KEY 未设置或为默认值。请创建 .env 文件并设置 LLM_API_KEY。")
    print(f"[启动] 服务地址: http://{HOST}:{PORT}")
    print(f"[启动] 模型: {cfg['llm_model']} | API 地址: {cfg['llm_base_url']}")
    print(f"[启动] 文档: http://{HOST}:{PORT}/docs")
    uvicorn.run(app, host=HOST, port=PORT)