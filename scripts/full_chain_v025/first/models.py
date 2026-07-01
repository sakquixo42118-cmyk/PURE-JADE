"""
PURE-JADE 情感支持AI — v0.2.1 数据模型副本

本副本用于验证 schema-v0.2.1 的状态更新请求、上一轮状态快照和本地
conversation_record 边界，不修改原 scripts/first。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class DialogueEntry(BaseModel):
    """单条对话记录。turn_id 为可选，以兼容旧前端历史格式。"""

    turn_id: Optional[int] = Field(default=None, description="对话轮次；旧前端可不传")
    speaker: str = Field(..., description="说话者：user 或 assistant")
    content: str = Field(..., description="说话内容")


class StateUpdatePolicy(BaseModel):
    """状态更新策略配置"""

    max_summary_chars: int = 180
    max_recent_turns: int = 3
    preserve_risk_memory: bool = True
    require_evidence_for_revision: bool = True


class PreviousStateSnapshot(BaseModel):
    """上一轮状态快照，来源于 conversation_record.current_state。"""

    turn_id: int
    dialogue_summary: str
    user_state_card: dict
    risk_memory: dict
    open_questions: list[str]

    @model_validator(mode="after")
    def require_state_card_snapshot(self):
        if not self.user_state_card:
            raise ValueError("previous_state_snapshot.user_state_card 不能为空")
        required = {"turn_id", "schema_version", "risk_level", "support_stage"}
        missing = sorted(required - set(self.user_state_card))
        if missing:
            raise ValueError(f"previous_state_snapshot.user_state_card 缺少字段: {missing}")
        return self


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
    """状态更新请求。

    规范字段为 recent_dialogue_window；validation_alias 兼容旧前端传入的
    dialogue_history。
    """

    model_config = ConfigDict(populate_by_name=True)

    conversation_id: str = Field(..., description="会话唯一标识")
    turn_id: int = Field(..., ge=1, description="当前用户轮次，从 1 开始")
    schema_version: str = Field(default="0.2.1", description="请求协议版本")
    current_user_message: str = Field(..., min_length=1, description="当前轮用户原话")
    recent_dialogue_window: list[DialogueEntry] = Field(
        default_factory=list,
        validation_alias=AliasChoices("recent_dialogue_window", "dialogue_history"),
        serialization_alias="recent_dialogue_window",
        description="最近 1-3 轮原始对话窗口",
    )
    previous_state_snapshot: Optional[PreviousStateSnapshot] = Field(
        default=None,
        description="上一轮状态快照；来源于本地 current_state，首轮为 null",
    )
    ai_response: Optional[str] = Field(
        default=None,
        description="上一轮或本轮 AI 生成的回复；状态更新时可作为最近窗口补充",
    )
    update_policy: StateUpdatePolicy = Field(
        default_factory=StateUpdatePolicy,
        description="状态更新策略",
    )

    @model_validator(mode="after")
    def validate_turn_snapshot_pair(self):
        if self.turn_id == 1 and self.previous_state_snapshot is not None:
            raise ValueError("首轮状态更新的 previous_state_snapshot 必须为 null")
        if self.turn_id > 1 and self.previous_state_snapshot is None:
            raise ValueError("非首轮状态更新必须提供 previous_state_snapshot")
        return self

    @property
    def dialogue_history(self) -> list[DialogueEntry]:
        """兼容旧代码中对 dialogue_history 的读取。"""
        return self.recent_dialogue_window


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


class ChatRequest(BaseModel):
    """聊天请求（前端发送）"""

    model_config = ConfigDict(populate_by_name=True)

    conversation_id: str = Field(..., description="会话唯一标识")
    turn_id: int = Field(..., ge=1, description="当前用户轮次，从 1 开始")
    schema_version: str = Field(default="0.2.1", description="请求协议版本")
    current_user_message: str = Field(..., min_length=1, description="当前轮用户原话")
    recent_dialogue_window: list[DialogueEntry] = Field(
        default_factory=list,
        validation_alias=AliasChoices("recent_dialogue_window", "dialogue_history"),
        serialization_alias="recent_dialogue_window",
        description="最近 1-3 轮原始对话窗口",
    )
    previous_state_snapshot: Optional[PreviousStateSnapshot] = Field(
        default=None,
        description="上一轮状态快照；来源于本地 current_state，首轮为 null",
    )

    @model_validator(mode="after")
    def validate_turn_snapshot_pair(self):
        if self.turn_id == 1 and self.previous_state_snapshot is not None:
            raise ValueError("首轮对话的 previous_state_snapshot 必须为 null")
        if self.turn_id > 1 and self.previous_state_snapshot is None:
            raise ValueError("非首轮对话必须提供 previous_state_snapshot")
        return self

    @property
    def dialogue_history(self) -> list[DialogueEntry]:
        """兼容旧代码中对 dialogue_history 的读取。"""
        return self.recent_dialogue_window


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