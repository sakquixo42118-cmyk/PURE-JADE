"""
PURE-JADE 情感支持AI — 用户状态卡生成 API

基于 schema-v0.1（总框架） 和 new_stategy.md（多轮状态更新）实现。

功能：
1. 引入 AI 模型（OpenAI 兼容 API）
2. 根据对话生成用户状态卡：
   - 首轮：直接生成
   - 后续轮次：基于上一轮状态卡 + AI 回复生成新状态卡
3. 本地 MD 对话记录备份
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

# ── 运行时配置（可通过 /config 端点动态修改） ──────────────────────────
_RUNTIME_CONFIG: dict = {
    "llm_api_key": os.getenv("LLM_API_KEY", ""),
    "llm_base_url": os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
    "llm_model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
    "llm_use_json_mode": os.getenv("LLM_USE_JSON_MODE", "false").lower() == "true",
}


def get_runtime_config() -> dict:
    """获取运行时配置副本"""
    return dict(_RUNTIME_CONFIG)


def update_runtime_config(**kwargs) -> None:
    """更新运行时配置（仅更新显式传入的键）"""
    allowed = {"llm_api_key", "llm_base_url", "llm_model", "llm_use_json_mode"}
    for k, v in kwargs.items():
        if v is not None and k in allowed:
            _RUNTIME_CONFIG[k] = v


# ---------------------------------------------------------------------------
# 系统提示词
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """你的任务是根据当前用户消息、对话历史窗口以及可选的前一轮状态快照，生成一张用户情感状态卡（User State Card）。
你只负责描述用户当前的情感状态、处境阶段和核心需求，不进行策略决策，也不生成最终回复。
必须遵守以下规则：
1. 只输出一个合法 JSON 对象，不要输出 Markdown、解释文字或代码块。
2. 输出对象必须符合 Schema v0.2 的 `user_state_card`，字段结构如下：
   - `conversation_id`：字符串，对话标识。
   - `turn_id`：整数，当前轮次编号。
   - `schema_version`：固定字符串 `"0.2"`。
   - `problem_summary`：字符串，用一两句话客观概括用户当前表达的核心困境，不添加未陈述的细节。
   - `emotion`：字符串数组，每个元素从预定义情绪标签中选择。标签仅包括["平静", "焦虑", "沮丧", "愤怒", "羞耻", "孤独", "疲惫", "自我怀疑", "无助", "困惑", "压力", "其他"]。当用户存在无特定情感表达的句式时，填入"平静"。若不属于以上几种情绪或平静，用"其他"。数组长度 1～3，按主导程度降序排列。
   - `emotion_intensity`：整数 1～5，表示整体情绪强烈程度。1 为轻微，3 为中等，5 为极其强烈。当 `risk_level` 为 `"high"` 时，不得低于 4。
   - `need`：字符串数组，每个元素从预定义需求标签中选择：`"被理解"`、`"被肯定"`、"情绪陪伴"、`"信息澄清"`、 "解决方案", "事实资源", "安全支持", "表达空间", "其他"]。允许为空数组。必须基于用户原话表达的真实诉求，按重要性排序。
   - `support_stage`：字符串，枚举值 `"exploration"` / `"comforting"` / `"action"` / `"safety_override"`。
   - `risk_level`：字符串，枚举值 `"low"` / `"medium"` / `"high"`。
   - `risk_signals`：字符串数组，记录检测到的风险信号，枚举值限定：`"self_harm"`、`"suicide"`、`"violence"`、`"abuse"`、`"crisis"`。无风险时为空数组。
   - `evidence`：字符串数组，从用户原话中摘取的关键词句，作为上述情绪、需求、阶段判断的依据。每条 evidence 应尽可能直接引用或紧密改写用户原话，不得凭空编造。
   - `unknowns`：字符串数组，列出对理解用户全貌或提供有效支持有明显影响的关键缺失信息，如事件背景、关系、时间、已尝试的应对方式等。无缺失时为空数组。
   - `confidence`：浮点数，取值 0.0～1.0，表示对本卡片整体判断的置信度。信息充分、表达明确时置信度高；若用户表达模糊或信息不足，应降低置信度。
3. 所有枚举值必须从给定枚举中选择，禁止自创标签。
4. 不进行医学或心理诊断，不编造用户未陈述的事实、经历或背景。
5. 安全规则：
   - 若用户表达中出现明确的自杀、自伤、伤害他人意图，或正在经历虐待、暴力等严重危机，必须将 `risk_level` 设为 `"high"`，`support_stage` 设为 `"safety_override"`，`need` 中必须包含 `"安全支持"`，`risk_signals` 中须填入对应信号。
   - 此时 `emotion_intensity` 至少为 4，其他字段正常填写但不得冲淡安全优先性。
6. 情感标签选择规则：
   - 优先选择用户原话中直接表达或强烈暗示的情绪词。
   - 若多种情绪并存，最多选取最突出的 3 个，按明显程度降序排列。
   - 禁止将策略意图混淆为情绪，如"需要建议"不是情绪。
7. `support_stage` 判定规则：
   - 主要在进行叙述、理清事件、还原经过，情绪未占据绝对主导 → `"exploration"`。
   - 主要表达痛苦、寻求安慰、渴望被理解和陪伴 → `"comforting"`。
   - 主要询问怎么办、请求方法、讨论行动方案 → `"action"`。
   - 触发安全规则时，强制设为 `"safety_override"`。
8. `need` 识别规则：
   - "被理解"：用户表达感到孤独、不被懂得、需要有人看见自己的处境。
   - "被肯定"：出现自我怀疑、自我否定、自责、感觉自己无用、多余、努力无意义等
   - "情绪陪伴"：用户流露出不被理解、自我否定、无力感或迷茫，且没有明确寻求解决方案时，说明需要情感陪伴。
   - "信息澄清"：询问事实、规则、资源、流程。
   - "解决方案"：明确要求方法、步骤、指导意见。
   - "表达空间"：表达想发泄、吐槽，或以强烈情绪倾诉。
   - "事实资源"： 寻求取得帮助的途径和相关现实资源。
   - "安全支持"：仅在触发安全规则时强制加入，不可用于普通安慰场景。
   - 若同一句话满足多项，按重要性放入数组；不要将推断出的需求当作用户直接诉求。
9. 当提供 `previous_state_snapshot` 且 `update_policy.require_evidence_for_revision` 为 `true` 时，必须遵守以下更新规则：
   - 仅当能从当前用户消息中提取到新的、明确的反向证据时，才允许修改上一轮的 `risk_level`、`support_stage` 或核心 `emotion`。
   - 对于 `need` 和 `unknowns`，允许因新信息出现而追加或移除，但必须在 `evidence` 中反映依据。
   - 风险记忆（`risk_memory`）中如果 `highest_risk_level` 曾为 `"high"`，即使本轮文本缓和，也不得将 `risk_level` 降为 `"low"` 或 `"medium"` 除非有明确的安全确认对话。
   - 必须保留上一轮 `open_questions` 中仍未被回答的关键缺口，并同步更新 `unknowns`。
10. `evidence` 必须严格基于用户原话和对话窗口中的内容，不得使用第二轮推断或外部知识。

情感状态识别优先级：
1. 生命威胁或严重伤害信号 > 一切。出现即 `risk_level = "high"`, `support_stage = "safety_override"`, `need` 中含 `"安全支持"`, `risk_signals` 非空。
2. 大量情感词汇（"好难过""崩溃""受不了"）且无明确行动指向 → `support_stage = "comforting"`，`need` 中优先包含 `"被理解"` 或 `"表达空间"`。
3. 自我否定、自责、孤独、被抛弃感、努力无意义等表达 → `need` 中必须包含 `"被肯定"`，且 `support_stage` 通常为 `"comforting"`。
4. 明确询问"我该怎么办""有什么办法""你能教我吗" → `support_stage = "action"`，`need` 中优先 `"解决方案"` 或 `"信息澄清"`。
5. 主要描述事件、试图理清前因后果，情绪词汇较少或附带提及 → `support_stage = "exploration"`，`need` 中优先 `"梳理处境"`。
6. 若既有强烈情绪又有具体求助，按整体基调判断：情绪压倒问题解决 → `"comforting"`；情绪为背景、重点在找方法 → `"action"`。"""

# ---------------------------------------------------------------------------
# 聊天系统提示词 — 用于生成情感支持回复
# ---------------------------------------------------------------------------

CHAT_SYSTEM_PROMPT = """你是 PURE-JADE，一个温暖、专业的情感支持 AI 助手。

## 你的角色
- 你通过对话为用户提供情感支持，不是心理治疗师
- 不进行医学或心理诊断，不提供医疗建议

## 回复原则
1. **共情优先**：先确认和理解用户的情绪，再回应内容
2. **倾听为主**：多用开放式提问鼓励用户表达，不急于给建议
3. **保持温暖**：语气温和自然，不评判、不说教、不空洞安慰
4. **回复简洁**：每轮 2～4 句话，避免长篇大论
5. **安全优先**：识别到严重风险时，引导寻求专业帮助

## 安全规则（重要）
- 用户表达自杀/自伤意图 → 回复包含心理援助热线（希望24热线：400-161-9995）
- 用户表达遭受暴力/虐待 → 鼓励联系可信赖的人或机构
- 不得承诺"一切都会好起来"等空洞安慰
- 不得进行诊断或提供医疗建议"""

# ---------------------------------------------------------------------------
# FastAPI 应用
# ---------------------------------------------------------------------------

app = FastAPI(
    title="PURE-JADE 用户状态卡生成 API",
    description="基于 Schema v0.1 和 v0.2/v0.2.1 多轮状态更新协议的情感状态卡生成服务",
    version="0.2.1",
)


# ---------------------------------------------------------------------------
# 提示词构建
# ---------------------------------------------------------------------------


def _build_first_turn_user_message(
    conversation_id: str,
    turn_id: int,
    user_message: str,
    history: list[DialogueEntry],
) -> str:
    """构建第一轮的用户消息（无前轮状态）"""
    history_text = _format_history(history)
    return (
        f"请为以下对话生成第一轮用户状态卡。\n\n"
        f"对话 ID：{conversation_id}\n"
        f"当前轮次：{turn_id}\n\n"
        f"最近对话窗口：\n{history_text}\n\n"
        f"当前用户消息：{user_message}"
    )


def _build_subsequent_turn_user_message(
    conversation_id: str,
    turn_id: int,
    user_message: str,
    history: list[DialogueEntry],
    previous_snapshot: PreviousStateSnapshot,
    ai_response: Optional[str],
    require_evidence: bool,
) -> str:
    """构建后续轮次的用户消息（包含前轮状态和 AI 回复）"""
    history_text = _format_history(history)
    snapshot_json = json.dumps(
        {
            "turn_id": previous_snapshot.turn_id,
            "dialogue_summary": previous_snapshot.dialogue_summary,
            "user_state_card": previous_snapshot.user_state_card,
            "risk_memory": previous_snapshot.risk_memory,
            "open_questions": previous_snapshot.open_questions,
        },
        ensure_ascii=False,
        indent=2,
    )

    parts = [
        f"请为以下对话生成第 {turn_id} 轮用户状态卡。\n",
        f"对话 ID：{conversation_id}",
        f"当前轮次：{turn_id}\n",
        "前一轮状态快照：",
        f"```json\n{snapshot_json}\n```\n",
    ]

    if ai_response:
        parts.append(f"AI 上一轮回复：\n{ai_response}\n")

    parts.append(f"最近对话窗口：\n{history_text}\n")
    parts.append(f"当前用户消息：{user_message}\n")

    if require_evidence:
        parts.append(
            "更新策略：require_evidence_for_revision = true\n"
            "注意：仅当能从当前用户消息中提取到新的、明确的反向证据时，"
            "才允许修改上一轮的 risk_level、support_stage 或核心 emotion。"
        )

    return "\n".join(parts)


def _format_history(history: list[DialogueEntry]) -> str:
    """将对话历史格式化为可读文本"""
    if not history:
        return "（无）"
    lines = []
    for entry in history:
        speaker_label = "用户" if entry.speaker == "user" else "系统"
        lines.append(f"  {speaker_label}：{entry.content}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM 调用与 JSON 解析
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> Optional[dict]:
    """从 LLM 回复中提取并解析 JSON 对象"""
    # 尝试直接解析
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试提取 ```json ... ``` 代码块
    match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 尝试提取最外层 { ... }
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def _call_llm_raw(messages: list[dict], temperature: float = 0.1) -> str:
    """调用 LLM API 并返回原始回复文本（使用运行时配置）"""
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
    except httpx.HTTPStatusError as e:
        detail = ""
        try:
            detail = f"，响应内容：{e.response.text[:300]}"
        except Exception:
            pass
        raise RuntimeError(f"LLM API 返回错误 (HTTP {e.response.status_code}){detail}")
    except httpx.RequestError as e:
        raise RuntimeError(f"LLM API 请求失败（网络错误）：{e}")
    except Exception as e:
        raise RuntimeError(f"LLM API 调用失败：{e}")

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(
            f"LLM 返回格式异常，无法提取回复内容。原始响应：\n"
            f"{json.dumps(data, ensure_ascii=False)[:500]}"
        )

    if not content or not content.strip():
        raise RuntimeError("LLM 返回了空内容")

    return content


def _call_llm(messages: list[dict]) -> dict:
    """调用 LLM API 并返回解析后的 JSON 对象"""
    content = _call_llm_raw(messages, temperature=0.1)

    result = _extract_json(content)
    if result is None:
        raise RuntimeError(
            f"LLM 返回了非 JSON 内容，无法解析。原始内容：\n{content[:500]}"
        )

    return result


def _call_llm_text(messages: list[dict]) -> str:
    """调用 LLM API 并返回纯文本回复"""
    return _call_llm_raw(messages, temperature=0.7)


# ---------------------------------------------------------------------------
# 聊天消息构建
# ---------------------------------------------------------------------------


def _build_chat_messages(
    user_message: str,
    history: list[DialogueEntry],
    is_first_turn: bool,
) -> list[dict]:
    """构建用于生成情感支持回复的消息列表"""
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
    """健康检查"""
    cfg = get_runtime_config()
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "model": cfg["llm_model"],
        "api_base": cfg["llm_base_url"],
    }


@app.get("/config", tags=["系统"])
async def get_config():
    """获取当前运行时配置（API 密钥脱敏）"""
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
    """更新运行时配置（只更新显式传入的字段）"""
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
    """
    根据对话生成用户情感状态卡。

    **功能：**
    - 首轮（turn_id == 1 且无 previous_state_snapshot）→ 直接生成状态卡。
    - 后续轮次（有 previous_state_snapshot）→ 基于上一轮状态卡 + AI 回复生成新状态卡。

    **规则：**
    - 严格遵循 schema-v0.1 的枚举和格式。
    - 遵循 new_stategy.md 的多轮状态更新规则。
    """
    # ── 参数校验 ──────────────────────────────────────────────────────
    conversation_id = request.conversation_id
    turn_id = request.turn_id
    is_first_turn = (turn_id == 1) or (request.previous_state_snapshot is None)

    if turn_id > 1 and request.previous_state_snapshot is None:
        raise HTTPException(
            status_code=400,
            detail="非首轮对话（turn_id > 1）必须提供 previous_state_snapshot",
        )

    # ── 检查轮次是否已生成本地记录（防重复） ─────────────────────────
    if conversation_exists(conversation_id):
        existing_turns = get_existing_turns(conversation_id)
        if turn_id in existing_turns:
            raise HTTPException(
                status_code=400,
                detail=f"第 {turn_id} 轮状态卡已存在，请勿重复生成",
            )

    # ── 构建提示词 ──────────────────────────────────────────────────
    if is_first_turn:
        user_prompt = _build_first_turn_user_message(
            conversation_id=conversation_id,
            turn_id=turn_id,
            user_message=request.current_user_message,
            history=request.dialogue_history,
        )
    else:
        user_prompt = _build_subsequent_turn_user_message(
            conversation_id=conversation_id,
            turn_id=turn_id,
            user_message=request.current_user_message,
            history=request.dialogue_history,
            previous_snapshot=request.previous_state_snapshot,
            ai_response=request.ai_response,
            require_evidence=request.update_policy.require_evidence_for_revision,
        )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    # ── 调用 LLM ────────────────────────────────────────────────────
    try:
        state_card = _call_llm(messages)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # ── 补充必填字段（若 LLM 漏填） ─────────────────────────────────
    state_card.setdefault("conversation_id", conversation_id)
    state_card.setdefault("turn_id", turn_id)
    state_card.setdefault("schema_version", "0.2")
    state_card.setdefault("risk_signals", [])

    # ── 本地 MD 记录 ────────────────────────────────────────────────
    if not conversation_exists(conversation_id):
        create_conversation_record(conversation_id)

    append_turn(
        conversation_id=conversation_id,
        turn_id=turn_id,
        user_message=request.current_user_message,
        state_card=state_card,
        ai_response=request.ai_response,
    )

    print(
        f"[API] 对话 {conversation_id} 第 {turn_id} 轮状态卡已生成"
        f"（{'首轮' if is_first_turn else '后续轮次'}）"
    )

    return StateCardResponse(
        conversation_id=conversation_id,
        turn_id=turn_id,
        schema_version="0.2",
        state_card=state_card,
        is_first_turn=is_first_turn,
    )


# ---------------------------------------------------------------------------
# 聊天端点 — 情感支持对话 + 状态卡一体化
# ---------------------------------------------------------------------------


@app.post(
    "/chat",
    response_model=ChatResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["对话"],
)
async def chat(request: ChatRequest):
    """
    情感支持对话（一体化端点）。

    **流程：**
    1. 基于对话历史生成 AI 情感支持回复
    2. 基于对话 + AI 回复生成用户状态卡
    3. 将本轮对话和状态卡保存至 data/conversations/
    4. 返回 {ai_response, state_card}
    """
    conversation_id = request.conversation_id
    turn_id = request.turn_id
    is_first_turn = (turn_id == 1) or (request.previous_state_snapshot is None)

    if turn_id > 1 and request.previous_state_snapshot is None:
        raise HTTPException(
            status_code=400,
            detail="非首轮对话（turn_id > 1）必须提供 previous_state_snapshot",
        )

    # ── 1. 生成 AI 情感支持回复 ───────────────────────────────────────
    chat_messages = _build_chat_messages(
        user_message=request.current_user_message,
        history=request.dialogue_history,
        is_first_turn=is_first_turn,
    )

    try:
        ai_response = _call_llm_text(chat_messages)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=f"生成回复失败：{e}")

    # ── 2. 生成状态卡 ──────────────────────────────────────────────────
    if is_first_turn:
        user_prompt = _build_first_turn_user_message(
            conversation_id=conversation_id,
            turn_id=turn_id,
            user_message=request.current_user_message,
            history=request.dialogue_history,
        )
    else:
        user_prompt = _build_subsequent_turn_user_message(
            conversation_id=conversation_id,
            turn_id=turn_id,
            user_message=request.current_user_message,
            history=request.dialogue_history,
            previous_snapshot=request.previous_state_snapshot,
            ai_response=ai_response,
            require_evidence=True,
        )

    state_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        state_card = _call_llm(state_messages)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=f"生成状态卡失败：{e}")

    # ── 补充必填字段 ──────────────────────────────────────────────────
    state_card.setdefault("conversation_id", conversation_id)
    state_card.setdefault("turn_id", turn_id)
    state_card.setdefault("schema_version", "0.2")
    state_card.setdefault("risk_signals", [])

    # ── 3. 保存 JSON 记录 ──────────────────────────────────────────────
    if not conversation_exists(conversation_id):
        create_conversation_record(conversation_id)

    append_turn(
        conversation_id=conversation_id,
        turn_id=turn_id,
        user_message=request.current_user_message,
        state_card=state_card,
        ai_response=ai_response,
    )

    print(
        f"[Chat] 对话 {conversation_id} 第 {turn_id} 轮 "
        f"（{'首轮' if is_first_turn else '后续轮次'}）完成"
    )

    # ── 4. 返回 ────────────────────────────────────────────────────────
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
        print(
            "[启动警告] LLM_API_KEY 未设置或为默认值。"
            "请创建 .env 文件并设置 LLM_API_KEY，或通过环境变量设置。"
        )
    print(f"[启动] 服务地址: http://{HOST}:{PORT}")
    print(f"[启动] 模型: {cfg['llm_model']} | API 地址: {cfg['llm_base_url']}")
    print(f"[启动] 文档: http://{HOST}:{PORT}/docs")
    uvicorn.run(app, host=HOST, port=PORT)
