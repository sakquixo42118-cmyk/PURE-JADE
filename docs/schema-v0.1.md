# Schema v0.1

## 文档目的

本文冻结 PURE-JADE 原型系统第一版卡片接口。卡片既用于答辩展示，也用于模块之间传递机器可读结果。

当前版本优先服务于最小可运行 Demo，不覆盖完整心理咨询流程，也不进行医学或心理诊断。

## 总体流程

```text
用户输入 / 历史对话
-> 风险优先检测
-> 用户状态卡
-> 共情策略决策卡
-> 行为回应卡
-> 场景应用与评价卡
```

所有模块必须保留原始用户输入，并在进入下一模块时同时传入原始对话和上一张卡片，避免级联过程中丢失信息。

## 统一字段

所有卡片必须包含以下字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `conversation_id` | string | 是 | 一段对话的唯一标识，同一段对话内保持不变 |
| `turn_id` | integer | 是 | 当前用户轮次，从 `1` 开始递增 |
| `schema_version` | string | 是 | 当前固定为 `"0.1"` |

## 固定枚举

### `support_stage`

| 值 | 说明 |
|---|---|
| `exploration` | 信息不足，需要先理解事件、情绪或需求 |
| `comforting` | 用户主要需要被理解、接住和肯定 |
| `action` | 用户已经明确请求建议、方案、信息或资源 |
| `safety_override` | 出现高风险表达，普通流程被安全流程覆盖 |

### `risk_level`

| 值 | 说明 |
|---|---|
| `low` | 普通情绪困扰或生活压力，未出现明显危险信号 |
| `medium` | 有持续强烈痛苦、失控感、极端表达或需要人工关注的信号 |
| `high` | 出现自伤、自杀、伤害他人、现实即时危险等表达 |

### `emotion`

固定为以下值之一或多项：

```json
[
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
  "其他"
]
```

### `need`

固定为以下值之一或多项：

```json
[
  "被理解",
  "被肯定",
  "情绪陪伴",
  "信息澄清",
  "解决方案",
  "事实资源",
  "安全支持",
  "表达空间",
  "其他"
]
```

### ESConv 支持策略

共情策略决策卡的 `primary_strategy` 和 `secondary_strategy` 使用 ESConv 的 8 类策略标签：

```json
[
  "Question",
  "Restatement or Paraphrasing",
  "Reflection of feelings",
  "Self-disclosure",
  "Affirmation and Reassurance",
  "Providing Suggestions",
  "Information",
  "Others"
]
```

高风险安全流程不强行归入 ESConv 策略，此时 `primary_strategy` 和 `secondary_strategy` 应为 `null`。

### `support_intention`

| 值 | 说明 |
|---|---|
| `clarify` | 澄清信息、确认用户处境或需求 |
| `comfort` | 接住情绪、表达理解 |
| `affirm` | 肯定用户的努力、价值或合理感受 |
| `normalize` | 适度正常化处境，降低孤立感 |
| `advise` | 给出低门槛、可选择的行动建议 |
| `inform` | 提供事实性信息或资源方向 |
| `safety_support` | 安全优先，引导用户寻求人类帮助或紧急支持 |
| `fallback_review` | 无法可靠归类，需要人工复核 |

### `response_timing`

| 值 | 说明 |
|---|---|
| `ask_clarification` | 先问一个关键问题 |
| `respond_now` | 当前轮直接回应情绪或需求 |
| `offer_next_step` | 给出下一步建议或资源方向 |
| `safety_override` | 启动安全流程 |

### `response_intensity`

| 值 | 说明 |
|---|---|
| `light` | 轻量回应，适合信息不足或低强度情绪 |
| `gentle` | 温和承接，适合多数安慰场景 |
| `moderate` | 更明确地支持、总结或建议 |
| `directive` | 明确指向安全行动，仅用于高风险或强约束场景 |

## JSON Schema

以下 Schema 可作为实现阶段的统一校验依据。后续可以拆分为 `schemas/user-state-card.schema.json`、`schemas/strategy-decision-card.schema.json`、`schemas/behavior-response-card.schema.json` 和 `schemas/evaluation-card.schema.json`。

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://pure-jade.local/schemas/cards.v0.1.schema.json",
  "title": "PURE-JADE Cards v0.1",
  "oneOf": [
    { "$ref": "#/$defs/user_state_card" },
    { "$ref": "#/$defs/strategy_decision_card" },
    { "$ref": "#/$defs/behavior_response_card" },
    { "$ref": "#/$defs/evaluation_card" }
  ],
  "$defs": {
    "conversation_id": {
      "type": "string",
      "minLength": 1,
      "maxLength": 80
    },
    "turn_id": {
      "type": "integer",
      "minimum": 1
    },
    "schema_version": {
      "const": "0.1"
    },
    "support_stage": {
      "type": "string",
      "enum": ["exploration", "comforting", "action", "safety_override"]
    },
    "risk_level": {
      "type": "string",
      "enum": ["low", "medium", "high"]
    },
    "emotion": {
      "type": "string",
      "enum": ["平静", "焦虑", "沮丧", "愤怒", "羞耻", "孤独", "疲惫", "自我怀疑", "无助", "困惑", "压力", "其他"]
    },
    "need": {
      "type": "string",
      "enum": ["被理解", "被肯定", "情绪陪伴", "信息澄清", "解决方案", "事实资源", "安全支持", "表达空间", "其他"]
    },
    "esconv_strategy": {
      "type": "string",
      "enum": [
        "Question",
        "Restatement or Paraphrasing",
        "Reflection of feelings",
        "Self-disclosure",
        "Affirmation and Reassurance",
        "Providing Suggestions",
        "Information",
        "Others"
      ]
    },
    "support_intention": {
      "type": "string",
      "enum": ["clarify", "comfort", "affirm", "normalize", "advise", "inform", "safety_support", "fallback_review"]
    },
    "response_timing": {
      "type": "string",
      "enum": ["ask_clarification", "respond_now", "offer_next_step", "safety_override"]
    },
    "response_intensity": {
      "type": "string",
      "enum": ["light", "gentle", "moderate", "directive"]
    },
    "tone_style": {
      "type": "string",
      "enum": ["warm_and_calm", "validating", "exploratory", "practical", "safety_directive"]
    },
    "score_1_to_5": {
      "type": "integer",
      "minimum": 1,
      "maximum": 5
    },
    "user_state_card": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "conversation_id",
        "turn_id",
        "schema_version",
        "problem_summary",
        "emotion",
        "emotion_intensity",
        "need",
        "support_stage",
        "risk_level",
        "evidence",
        "unknowns",
        "confidence"
      ],
      "properties": {
        "conversation_id": { "$ref": "#/$defs/conversation_id" },
        "turn_id": { "$ref": "#/$defs/turn_id" },
        "schema_version": { "$ref": "#/$defs/schema_version" },
        "problem_summary": {
          "type": "string",
          "minLength": 1,
          "maxLength": 120
        },
        "emotion": {
          "type": "array",
          "minItems": 1,
          "maxItems": 4,
          "uniqueItems": true,
          "items": { "$ref": "#/$defs/emotion" }
        },
        "emotion_intensity": {
          "type": "integer",
          "minimum": 0,
          "maximum": 3
        },
        "need": {
          "type": "array",
          "minItems": 1,
          "maxItems": 4,
          "uniqueItems": true,
          "items": { "$ref": "#/$defs/need" }
        },
        "support_stage": { "$ref": "#/$defs/support_stage" },
        "risk_level": { "$ref": "#/$defs/risk_level" },
        "risk_signals": {
          "type": "array",
          "maxItems": 5,
          "items": {
            "type": "string",
            "minLength": 1,
            "maxLength": 120
          }
        },
        "evidence": {
          "type": "array",
          "minItems": 1,
          "maxItems": 5,
          "items": {
            "type": "string",
            "minLength": 1,
            "maxLength": 160
          }
        },
        "unknowns": {
          "type": "array",
          "maxItems": 5,
          "items": {
            "type": "string",
            "minLength": 1,
            "maxLength": 120
          }
        },
        "confidence": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        }
      },
      "allOf": [
        {
          "if": {
            "properties": {
              "risk_level": { "const": "high" }
            },
            "required": ["risk_level"]
          },
          "then": {
            "properties": {
              "support_stage": { "const": "safety_override" },
              "need": {
                "contains": { "const": "安全支持" }
              }
            }
          }
        }
      ]
    },
    "strategy_decision_card": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "conversation_id",
        "turn_id",
        "schema_version",
        "support_intention",
        "primary_strategy",
        "secondary_strategy",
        "response_timing",
        "response_intensity",
        "response_goal",
        "reason",
        "esconv_example_ids",
        "constraints",
        "prohibited_actions",
        "safety_override"
      ],
      "properties": {
        "conversation_id": { "$ref": "#/$defs/conversation_id" },
        "turn_id": { "$ref": "#/$defs/turn_id" },
        "schema_version": { "$ref": "#/$defs/schema_version" },
        "support_intention": { "$ref": "#/$defs/support_intention" },
        "primary_strategy": {
          "anyOf": [
            { "$ref": "#/$defs/esconv_strategy" },
            { "type": "null" }
          ]
        },
        "secondary_strategy": {
          "anyOf": [
            { "$ref": "#/$defs/esconv_strategy" },
            { "type": "null" }
          ]
        },
        "response_timing": { "$ref": "#/$defs/response_timing" },
        "response_intensity": { "$ref": "#/$defs/response_intensity" },
        "response_goal": {
          "type": "string",
          "minLength": 1,
          "maxLength": 160
        },
        "reason": {
          "type": "string",
          "minLength": 1,
          "maxLength": 240
        },
        "esconv_example_ids": {
          "type": "array",
          "maxItems": 3,
          "uniqueItems": true,
          "items": {
            "type": "string",
            "pattern": "^(train|valid|test|manual|esconv)_[A-Za-z0-9_-]+$"
          }
        },
        "constraints": {
          "type": "array",
          "minItems": 1,
          "maxItems": 8,
          "items": {
            "type": "string",
            "minLength": 1,
            "maxLength": 120
          }
        },
        "prohibited_actions": {
          "type": "array",
          "maxItems": 8,
          "items": {
            "type": "string",
            "minLength": 1,
            "maxLength": 120
          }
        },
        "safety_override": {
          "type": "boolean"
        }
      },
      "allOf": [
        {
          "if": {
            "properties": {
              "safety_override": { "const": true }
            },
            "required": ["safety_override"]
          },
          "then": {
            "properties": {
              "support_intention": { "const": "safety_support" },
              "primary_strategy": { "type": "null" },
              "secondary_strategy": { "type": "null" },
              "response_timing": { "const": "safety_override" },
              "response_intensity": { "const": "directive" },
              "esconv_example_ids": {
                "type": "array",
                "maxItems": 0
              }
            }
          }
        },
        {
          "if": {
            "properties": {
              "safety_override": { "const": false }
            },
            "required": ["safety_override"]
          },
          "then": {
            "properties": {
              "primary_strategy": { "$ref": "#/$defs/esconv_strategy" }
            }
          }
        }
      ]
    },
    "behavior_response_card": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "conversation_id",
        "turn_id",
        "schema_version",
        "text_response",
        "tone_style",
        "strategy_realization",
        "follow_up_question_count",
        "facial_expression",
        "action",
        "safety_message_used"
      ],
      "properties": {
        "conversation_id": { "$ref": "#/$defs/conversation_id" },
        "turn_id": { "$ref": "#/$defs/turn_id" },
        "schema_version": { "$ref": "#/$defs/schema_version" },
        "text_response": {
          "type": "string",
          "minLength": 1,
          "maxLength": 360
        },
        "tone_style": { "$ref": "#/$defs/tone_style" },
        "strategy_realization": {
          "type": "array",
          "minItems": 1,
          "maxItems": 4,
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": ["strategy", "text_span"],
            "properties": {
              "strategy": {
                "anyOf": [
                  { "$ref": "#/$defs/esconv_strategy" },
                  {
                    "type": "string",
                    "enum": ["Safety Guidance"]
                  }
                ]
              },
              "text_span": {
                "type": "string",
                "minLength": 1,
                "maxLength": 120
              }
            }
          }
        },
        "follow_up_question_count": {
          "type": "integer",
          "minimum": 0,
          "maximum": 1
        },
        "facial_expression": {
          "type": ["string", "null"],
          "enum": ["neutral", "soft_smile", "concerned", null]
        },
        "action": {
          "type": ["string", "null"],
          "enum": ["none", "pause", "offer_resource", null]
        },
        "safety_message_used": {
          "type": "boolean"
        }
      }
    },
    "evaluation_card": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "conversation_id",
        "turn_id",
        "schema_version",
        "emotion_alignment",
        "strategy_consistency",
        "relevance",
        "naturalness",
        "safety",
        "overall_score",
        "violations",
        "review_needed",
        "evaluator_type",
        "review_notes"
      ],
      "properties": {
        "conversation_id": { "$ref": "#/$defs/conversation_id" },
        "turn_id": { "$ref": "#/$defs/turn_id" },
        "schema_version": { "$ref": "#/$defs/schema_version" },
        "emotion_alignment": { "$ref": "#/$defs/score_1_to_5" },
        "strategy_consistency": { "$ref": "#/$defs/score_1_to_5" },
        "relevance": { "$ref": "#/$defs/score_1_to_5" },
        "naturalness": { "$ref": "#/$defs/score_1_to_5" },
        "safety": { "$ref": "#/$defs/score_1_to_5" },
        "overall_score": { "$ref": "#/$defs/score_1_to_5" },
        "violations": {
          "type": "array",
          "uniqueItems": true,
          "items": {
            "type": "string",
            "enum": [
              "medical_diagnosis",
              "unsafe_advice",
              "strategy_mismatch",
              "unsupported_claim",
              "overly_didactic",
              "copied_esconv_response",
              "too_many_questions",
              "privacy_risk",
              "other"
            ]
          }
        },
        "review_needed": {
          "type": "boolean"
        },
        "evaluator_type": {
          "type": "string",
          "enum": ["llm_initial", "human_review", "teacher_review"]
        },
        "review_notes": {
          "type": "string",
          "maxLength": 300
        }
      }
    }
  }
}
```

## 卡片示例

### 用户状态卡

```json
{
  "conversation_id": "demo_001",
  "turn_id": 1,
  "schema_version": "0.1",
  "problem_summary": "用户觉得学习努力没有得到预期结果",
  "emotion": ["疲惫", "沮丧", "自我怀疑"],
  "emotion_intensity": 2,
  "need": ["被理解", "被肯定"],
  "support_stage": "comforting",
  "risk_level": "low",
  "risk_signals": [],
  "evidence": ["感觉怎么努力都没有用"],
  "unknowns": ["具体学习任务和持续时间尚不清楚"],
  "confidence": 0.84
}
```

### 共情策略决策卡

```json
{
  "conversation_id": "demo_001",
  "turn_id": 1,
  "schema_version": "0.1",
  "support_intention": "comfort",
  "primary_strategy": "Reflection of feelings",
  "secondary_strategy": "Affirmation and Reassurance",
  "response_timing": "respond_now",
  "response_intensity": "gentle",
  "response_goal": "让用户感到情绪被理解，并承认其持续努力的价值",
  "reason": "用户表达了努力无效带来的沮丧和自我怀疑，目前没有主动请求解决方案",
  "esconv_example_ids": [],
  "constraints": ["先共情，不急于给建议", "最多提出一个问题", "不得进行心理诊断"],
  "prohibited_actions": ["不要说教", "不要否定用户感受", "不要承诺一定会变好"],
  "safety_override": false
}
```

### 行为回应卡

```json
{
  "conversation_id": "demo_001",
  "turn_id": 1,
  "schema_version": "0.1",
  "text_response": "听起来你已经努力了很久，却一直没有看到期待的结果，这种无力感确实很磨人。你能坚持到现在，本身也说明这件事对你很重要。最近是哪一次结果让这种感觉特别明显？",
  "tone_style": "warm_and_calm",
  "strategy_realization": [
    {
      "strategy": "Reflection of feelings",
      "text_span": "这种无力感确实很磨人"
    },
    {
      "strategy": "Affirmation and Reassurance",
      "text_span": "你能坚持到现在，本身也说明这件事对你很重要"
    }
  ],
  "follow_up_question_count": 1,
  "facial_expression": null,
  "action": null,
  "safety_message_used": false
}
```

### 评价卡

```json
{
  "conversation_id": "demo_001",
  "turn_id": 1,
  "schema_version": "0.1",
  "emotion_alignment": 4,
  "strategy_consistency": 5,
  "relevance": 4,
  "naturalness": 4,
  "safety": 5,
  "overall_score": 4,
  "violations": [],
  "review_needed": false,
  "evaluator_type": "llm_initial",
  "review_notes": "回复承接了用户的无力感，并保持了单一追问。最终评分仍需人工复核。"
}
```

## 安全流程约束

当 `risk_level` 为 `high` 时：

- `support_stage` 必须使用 `safety_override`。
- 策略卡必须设置 `safety_override: true`。
- `support_intention` 必须为 `safety_support`。
- `primary_strategy` 和 `secondary_strategy` 必须为 `null`。
- `response_timing` 必须为 `safety_override`。
- `response_intensity` 必须为 `directive`。
- `esconv_example_ids` 必须为空数组。
- 行为回应必须避免诊断、承诺、责备和复杂建议，优先鼓励联系可信任的人或当地紧急支持。

当 `risk_level` 为 `medium` 时，可以继续普通策略流程，但必须在 `constraints` 中加入更谨慎的安全边界，例如“不做诊断”“建议联系现实中的可信任支持者”“必要时人工复核”。

## 实现阶段建议

- Prompt 输出必须是纯 JSON 对象，不要包含 Markdown 或解释文字。
- 每次模型输出后先执行 JSON 解析，再执行 Schema 校验。
- 校验失败时使用重试 Prompt，并明确指出失败字段。
- 记录每轮的 `prompt_version`、模型名、检索到的 `esconv_example_ids` 和原始输出，便于复现实验。
- 评价卡可以先由 LLM 初评，但最终实验结果必须加入人工评分或人工复核。
