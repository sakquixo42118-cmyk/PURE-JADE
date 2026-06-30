"""
PURE-JADE 情感支持AI — 数据模型

基于 schema-v0.1（总框架） 和 new_stategy.md（多轮状态更新）定义。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DialogueEntry(BaseModel):
    """单条对话记录"""
    speaker: str = Field(..., description="说话者：user 或 assistant")
    content: str = Field(..., description="说话内容")


class StateUpdatePolicy(BaseModel):
    """状态更新策略配置"""
    max_summary_chars: int = 180
    max_recent_turns: int = 3
    preserve_risk_memory: bool = True
    require_evidence_for_revision: bool = True


class PreviousStateSnapshot(BaseModel):
    """上一轮状态快照（来自 new_stategy.md）"""
    turn_id: int
    dialogue_summary: str
    user_state_card: dict
    risk_memory: dict
    open_questions: list[str]


class RiskMemory(BaseModel):
    """多轮风险记忆"""
    highest_risk_level: str = "low"
    risk_signals_seen: list[str] = []
    safety_followup_needed: bool = False


class RevisedField(BaseModel):
    """被修正的字段记录"""
    field: str
    previous_value: object
    current_value: object
    reason: str


class StateCardRequest(BaseModel):
    """生成用户状态卡的请求"""
    conversation_id: str = Field(..., description="会话唯一标识")
    turn_id: int = Field(..., ge=1, description="当前用户轮次，从 1 开始")
    current_user_message: str = Field(..., min_length=1, description="当前轮用户原话")
    dialogue_history: list[DialogueEntry] = Field(
        default_factory=list,
        description="最近对话窗口（如最近 1-3 轮原始对话）"
    )
    previous_state_snapshot: Optional[PreviousStateSnapshot] = Field(
        default=None,
        description="上一轮状态快照；首轮为 null"
    )
    ai_response: Optional[str] = Field(
        default=None,
        description="上一轮 AI 生成的回复（首轮为 null）"
    )
    update_policy: StateUpdatePolicy = Field(
        default_factory=StateUpdatePolicy,
        description="状态更新策略"
    )


class StateCardResponse(BaseModel):
    """生成的用户状态卡"""
    conversation_id: str
    turn_id: int
    schema_version: str = "0.2"
    state_card: dict = Field(..., description="完整的用户状态卡 JSON")
    is_first_turn: bool = Field(..., description="是否为第一轮")
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class ErrorResponse(BaseModel):
    """错误响应"""
    error: str
    detail: Optional[str] = None


# ---------------------------------------------------------------------------
# v0.3 — 聊天 + 配置
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    """聊天请求（前端发送）"""
    conversation_id: str = Field(..., description="会话唯一标识")
    turn_id: int = Field(..., ge=1, description="当前用户轮次，从 1 开始")
    current_user_message: str = Field(..., min_length=1, description="当前轮用户原话")
    dialogue_history: list[DialogueEntry] = Field(
        default_factory=list,
        description="之前的所有对话记录（用于构建上下文）"
    )
    previous_state_snapshot: Optional[PreviousStateSnapshot] = Field(
        default=None,
        description="上一轮状态快照；首轮为 null"
    )


class ChatResponse(BaseModel):
    """聊天响应（含 AI 回复 + 状态卡）"""
    conversation_id: str
    turn_id: int
    ai_response: str = Field(..., description="AI 生成的情感支持回复")
    state_card: dict = Field(..., description="本轮用户状态卡 JSON")
    is_first_turn: bool
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class ServerConfig(BaseModel):
    """服务端运行时配置（可局部更新）"""
    llm_api_key: Optional[str] = Field(default=None, description="LLM API 密钥")
    llm_base_url: Optional[str] = Field(default=None, description="LLM API 地址")
    llm_model: Optional[str] = Field(default=None, description="LLM 模型名")
    llm_use_json_mode: Optional[bool] = Field(default=None, description="是否启用 JSON mode")
