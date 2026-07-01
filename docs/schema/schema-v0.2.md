# Schema v0.2

## 文档目的

Schema v0.2 在 v0.1 四张卡片基础上，补充多轮对话中的状态持续更新能力。

v0.1 主要解决单轮流程：

```text
用户输入
-> 用户状态卡
-> 共情策略决策卡
-> 行为回应卡
-> 场景应用与评价卡
```

v0.2 重点解决多轮流程：

```text
历史摘要 + 上一轮状态卡 + 当前用户输入
-> 更新后的用户状态卡
-> 新的策略决策卡
-> 新的行为回应卡
-> 新的评价卡
```

## 版本关系

v0.2 是对 v0.1 的增量扩展，不推翻 v0.1。

| 项目 | v0.1 | v0.2 |
|---|---|---|
| 主要场景 | 单轮 case / golden case 回放 | 多轮对话 |
| 用户状态卡 | 描述当前状态 | 描述当前状态 + 解释状态如何更新 |
| 策略决策卡 | 基于当前状态选策略 | 基于最新状态选策略，并记录依据来自哪一轮状态 |
| 行为回应卡 | 落实策略 | 落实策略，并说明是否使用历史上下文 |
| 评价卡 | 评价单轮回复 | 增加状态更新和上下文连续性评价 |

## 多轮状态更新原则

每一轮都应维护一张最新用户状态卡。不要只依赖模型自由记忆上下文。

状态更新输入：

<u>v0.2 中的状态更新输入仍是概念结构；v0.2.1 会把它落成可直接传给 API 的 `state_update_request`。实现时不能依赖同一个 API key 自动记住历史。</u>

```text
previous_state_snapshot（包含 previous_user_state_card + dialogue_summary + risk_memory + open_questions）
+ recent_dialogue_window
+ current_user_message
-> updated_user_state_card
```

更新时必须区分：

- 哪些信息从上一轮延续；
- 哪些信息是当前轮新增；
- 哪些字段被修正；
- 哪些问题仍然未知；
- 风险信号是否需要持续保留。

## 用户状态卡 v0.2 新增字段

v0.2 用户状态卡保留 v0.1 的所有字段，并新增以下字段。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `previous_turn_id` | integer/null | 是 | 当前状态卡基于哪一轮状态更新；首轮为 `null` |
| `dialogue_summary` | string | 是 | 到当前轮为止的短摘要 |
| `state_update_type` | string | 是 | 状态更新类型 |
| `carried_over_facts` | string[] | 是 | 从上一轮延续下来的事实或判断 |
| `new_evidence` | string[] | 是 | 当前用户输入新增的证据 |
| `revised_fields` | object[] | 是 | 被修正的字段及原因 |
| `open_questions` | string[] | 是 | 后续仍需要澄清的问题 |
| `risk_memory` | object | 是 | 多轮风险记忆 |

### `state_update_type`

```json
[
  "initial",
  "carry_over",
  "revised",
  "risk_escalation",
  "risk_deescalation"
]
```

说明：

- `initial`：首轮状态卡；
- `carry_over`：主要延续上一轮状态；
- `revised`：当前轮显著修正了上一轮状态；
- `risk_escalation`：风险等级上升；
- `risk_deescalation`：风险等级下降，但仍需保留风险记忆。

### `revised_fields`

用于解释多轮中哪些判断被更新。

```json
[
  {
    "field": "support_stage",
    "previous_value": "comforting",
    "current_value": "exploration",
    "reason": "用户补充了具体科目和刷题无效的信息，当前需要先澄清学习方法问题。"
  }
]
```

### `risk_memory`

风险信息比普通情绪信息更持久。即使用户后续转移话题，也不能直接忘掉前面出现过的高风险信号。

```json
{
  "highest_risk_level": "low",
  "risk_signals_seen": [],
  "safety_followup_needed": false
}
```

字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| `highest_risk_level` | string | 本段对话到目前为止出现过的最高风险等级 |
| `risk_signals_seen` | string[] | 历史中出现过的风险信号 |
| `safety_followup_needed` | boolean | 后续是否仍需要安全跟进 |

## 用户状态卡 v0.2 示例

### 第 1 轮

用户输入：

```text
我最近真的很累，明明每天都在复习，但成绩还是没有起色。我感觉怎么努力都没有用。
```

状态卡：

```json
{
  "conversation_id": "demo_multiturn_001",
  "turn_id": 1,
  "previous_turn_id": null,
  "schema_version": "0.2",
  "dialogue_summary": "用户因持续复习但成绩没有起色而感到疲惫、沮丧和自我怀疑。",
  "state_update_type": "initial",
  "problem_summary": "用户觉得持续复习没有带来成绩提升",
  "emotion": ["疲惫", "沮丧", "自我怀疑"],
  "emotion_intensity": 2,
  "need": ["被理解", "被肯定"],
  "support_stage": "comforting",
  "risk_level": "low",
  "risk_signals": [],
  "evidence": ["明明每天都在复习", "成绩还是没有起色", "怎么努力都没有用"],
  "unknowns": ["具体科目不清楚", "是否复盘错因不清楚"],
  "carried_over_facts": [],
  "new_evidence": ["用户每天复习但成绩没有起色", "用户表达努力无用感"],
  "revised_fields": [],
  "open_questions": ["是哪一科或哪类反馈让用户最受挫"],
  "risk_memory": {
    "highest_risk_level": "low",
    "risk_signals_seen": [],
    "safety_followup_needed": false
  },
  "confidence": 0.88
}
```

### 第 2 轮

用户输入：

```text
主要是高数，我每天都刷题，但考试还是很差。
```

更新后的状态卡：

```json
{
  "conversation_id": "demo_multiturn_001",
  "turn_id": 2,
  "previous_turn_id": 1,
  "schema_version": "0.2",
  "dialogue_summary": "用户因高数学习挫败感到疲惫和自我怀疑，已说明每天刷题但考试仍差。",
  "state_update_type": "revised",
  "problem_summary": "用户高数每天刷题但考试结果仍不理想",
  "emotion": ["沮丧", "自我怀疑", "压力"],
  "emotion_intensity": 2,
  "need": ["被理解", "信息澄清", "解决方案"],
  "support_stage": "exploration",
  "risk_level": "low",
  "risk_signals": [],
  "evidence": ["主要是高数", "每天都刷题", "考试还是很差"],
  "unknowns": ["是否复盘错因不清楚", "错题类型和考试反馈不清楚"],
  "carried_over_facts": ["用户持续复习后没有看到预期结果", "用户有自我怀疑"],
  "new_evidence": ["困难科目是高数", "用户每天刷题但考试仍差"],
  "revised_fields": [
    {
      "field": "support_stage",
      "previous_value": "comforting",
      "current_value": "exploration",
      "reason": "用户补充了具体科目和刷题无效的信息，需要先澄清学习方法或错因。"
    },
    {
      "field": "need",
      "previous_value": ["被理解", "被肯定"],
      "current_value": ["被理解", "信息澄清", "解决方案"],
      "reason": "当前轮出现了更具体的问题线索，后续可能进入方法澄清或建议。"
    }
  ],
  "open_questions": ["刷题后是否复盘错因", "考试主要失分在哪类题"],
  "risk_memory": {
    "highest_risk_level": "low",
    "risk_signals_seen": [],
    "safety_followup_needed": false
  },
  "confidence": 0.9
}
```

## 策略决策卡 v0.2 新增字段

策略决策卡保留 v0.1 字段，并新增：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `state_basis_turn_id` | integer | 是 | 本轮策略依据的是哪一轮用户状态卡 |
| `state_change_summary` | string | 是 | 当前策略相对上一轮是否发生变化，以及为什么 |

示例：

```json
{
  "conversation_id": "demo_multiturn_001",
  "turn_id": 2,
  "schema_version": "0.2",
  "state_basis_turn_id": 2,
  "state_change_summary": "用户从泛泛表达挫败转为说明高数刷题无效，策略从直接安慰转为先澄清学习方法问题。",
  "support_intention": "clarify",
  "primary_strategy": "Restatement or Paraphrasing",
  "secondary_strategy": "Question",
  "response_timing": "ask_clarification",
  "response_intensity": "gentle",
  "response_goal": "先整理高数刷题无效的处境，再澄清错因复盘情况。",
  "reason": "用户新增了具体科目和刷题无效信息，当前需要先定位阻碍点，而不是继续泛泛安慰。",
  "esconv_example_ids": [],
  "constraints": ["先复述处境", "只问一个关键问题", "不直接给复杂学习方案"],
  "prohibited_actions": ["不要承诺成绩一定提升", "不要连续追问多个问题"],
  "safety_override": false
}
```

## 行为回应卡 v0.2 新增字段

行为回应卡保留 v0.1 字段，并新增：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `uses_previous_context` | boolean | 是 | 本轮回复是否使用了历史上下文 |
| `context_used` | string[] | 是 | 本轮回复用到的历史信息 |

示例：

```json
{
  "conversation_id": "demo_multiturn_001",
  "turn_id": 2,
  "schema_version": "0.2",
  "text_response": "原来主要卡在高数，而且你不是没投入，而是每天刷题后考试还是不理想，这确实会让人很挫败。为了先找准问题，你现在更像是错在概念理解，还是计算和题型迁移上？",
  "tone_style": "exploratory",
  "strategy_realization": [
    {
      "strategy": "Restatement or Paraphrasing",
      "text_span": "主要卡在高数，而且你不是没投入，而是每天刷题后考试还是不理想"
    },
    {
      "strategy": "Question",
      "text_span": "你现在更像是错在概念理解，还是计算和题型迁移上？"
    }
  ],
  "follow_up_question_count": 1,
  "facial_expression": null,
  "action": null,
  "safety_message_used": false,
  "uses_previous_context": true,
  "context_used": ["上一轮用户表达持续努力但成绩没有起色", "当前轮用户补充困难科目是高数"]
}
```

## 评价卡 v0.2 新增字段

评价卡保留 v0.1 字段，并新增：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `state_update_validity` | integer | 是 | 用户状态更新是否合理，1-5 分 |
| `context_continuity` | integer | 是 | 回复是否正确利用历史上下文，1-5 分 |
| `memory_issues` | string[] | 是 | 多轮记忆问题 |

`memory_issues` 可选值：

```json
[
  "ignored_new_evidence",
  "overweighted_old_state",
  "unsupported_revision",
  "missed_risk_signal",
  "forgot_relevant_context",
  "none",
  "other"
]
```

## v0.2 对第二部分的影响

第二部分仍然只负责策略决策，但输入应从“单轮用户状态卡”升级为“最新用户状态卡”。

<u>更准确地说，第二部分的实际请求对象是 `strategy_decision_request`。它不读取完整 `conversation_record`，也不重新总结完整历史；历史摘要和当前轮新增证据应已经包含在 `latest_user_state_card.dialogue_summary` 与 `latest_user_state_card.new_evidence` 中。</u>

```text
v0.1:
current_user_message + 当前用户状态卡
-> 策略决策卡

v0.2:
current_user_message + latest_user_state_card + optional strategy_references
-> 策略决策卡
```

第二部分不负责自己维护完整状态，但必须响应第一部分更新后的状态变化。例如：

- `support_stage` 从 `comforting` 变成 `exploration` 时，策略可能从情绪承接切换为澄清；
- `need` 从 `被理解/被肯定` 增加 `解决方案` 时，策略可能逐步靠近建议；
- `risk_level` 上升时，必须进入安全覆盖流程。

## 实现建议

1. v0.1 测试和报告可以保留，作为单轮基线。
2. 新增多轮测试集时，建议命名为 `examples/multiturn-test-cases-v0.2.json`。
3. 第一部分应优先实现状态更新 Prompt。
4. <u>第二部分只读取最新状态卡，不要绕过状态卡直接凭完整历史重判所有信息；若需要历史信息，应由第一部分先写入最新状态卡。</u>
5. 评价卡需要额外检查“状态更新是否合理”和“是否遗忘/误用历史信息”。

