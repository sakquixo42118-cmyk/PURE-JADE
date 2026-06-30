# Schema v0.2 – v0.2.1 合并

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

Schema v0.2.1 是 v0.2 的补丁版本，重点补齐多轮对话的实现契约：

1. `dialogue_summary` 应该由谁生成；
2. 第二轮及后续轮次输入给状态更新 API 的内容；
3. 程序本地需要保存的 conversation record 结构；
4. 第二部分策略决策如何读取最新状态，而不是自己重建全部历史。

v0.2.1 不推翻 v0.2 的卡片字段。它把 v0.2 中"多轮状态更新"的概念落成可实现的数据结构。

## 版本关系

| 版本 | 作用 |
|---|---|
| v0.1 | 单轮四卡协议，服务 golden cases 和第二部分策略测试 |
| v0.2 | 增加多轮状态更新字段 |
| v0.2.1 | 增加状态更新请求、滚动摘要来源、本地 conversation record |

v0.2 是对 v0.1 的增量扩展，不推翻 v0.1。

| 项目 | v0.1 | v0.2 |
|---|---|---|
| 主要场景 | 单轮 case / golden case 回放 | 多轮对话 |
| 用户状态卡 | 描述当前状态 | 描述当前状态 + 解释状态如何更新 |
| 策略决策卡 | 基于当前状态选策略 | 基于最新状态选策略，并记录依据来自哪一轮状态 |
| 行为回应卡 | 落实策略 | 落实策略，并说明是否使用历史上下文 |
| 评价卡 | 评价单轮回复 | 增加状态更新和上下文连续性评价 |

## 多轮记忆分层

多轮对话不应该只依赖模型自由记忆上下文，也不应该每轮都把完整历史塞进 prompt。

v0.2.1 推荐四层记忆：

| 层级 | 内容 | 是否长期保存 | 用途 |
|---|---|---|---:|---|
| 原始对话日志 | 每一轮用户和系统原文 | 是 | 追溯、复核、调试 |
| 每轮卡片记录 | 每轮四张卡或已完成的部分卡 | 是 | 展示、评估、回放 |
| 当前状态快照 | 最新摘要、最新用户状态卡、风险记忆、未解问题 | 是 | 下一轮快速读取 |
| 最近对话窗口 | 最近 1-3 轮原始对话 | 否，可重建 | 给状态更新 API 保留局部语境 |

关系如下：

```text
完整历史不直接全量进 prompt
-> 先沉淀为 dialogue_log + turn_records
-> 再维护 current_state
-> 下一轮输入 current_state + recent_dialogue_window + 当前用户输入
```

## 多轮状态更新原则

每一轮都应维护一张最新用户状态卡。不要只依赖模型自由记忆上下文。

状态更新输入：

```text
previous_user_state_card
+ dialogue_summary
+ current_user_message
-> updated_user_state_card
```

更新时必须区分：

- 哪些信息从上一轮延续；
- 哪些信息是当前轮新增；
- 哪些字段被修正；
- 哪些问题仍然未知；
- 风险信号是否需要持续保留。

## `dialogue_summary` 的来源

`dialogue_summary` 由第一部分状态更新模块生成，不由第二部分策略决策模块生成。

生成依据：

```text
previous_dialogue_summary
+ previous_user_state_card
+ current_user_message
+ recent_dialogue_window
-> updated_dialogue_summary
```

summary 必须满足：

- 基于用户原话和已确认状态，不编造；
- 保留长期相关事实；
- 吸收当前轮新增信息；
- 如果当前轮修正了上一轮判断，summary 要反映修正后的状态；
- 风险信号不能因为用户转移话题就被直接删除；
- 保持短摘要，不写完整聊天记录。

不推荐：

```text
第二部分策略 API 自己临时总结历史
```

原因是第二部分只负责策略决策。如果让第二部分自己总结历史，会造成状态来源不稳定，也不利于回放和调试。

## 用户状态卡 v0.2 字段定义

### v0.1 保留字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `conversation_id` | string | 会话唯一标识 |
| `turn_id` | integer | 当前用户轮次 |
| `schema_version` | string | schema 版本号 |
| `problem_summary` | string | 问题摘要 |
| `emotion` | string[] | 用户情绪标签 |
| `emotion_intensity` | integer | 情绪强度 |
| `need` | string[] | 用户需求 |
| `support_stage` | string | 当前应处的支持阶段 |
| `risk_level` | string | 风险等级 |
| `risk_signals` | string[] | 风险信号列表 |
| `evidence` | string[] | 用于支撑判断的用户原话证据 |
| `unknowns` | string[] | 尚未明确的未知信息 |
| `confidence` | number | 对当前判断的置信度 |

### v0.2 新增字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
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

## 用户状态卡示例

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

## 状态更新请求：`state_update_request`

第二轮及后续轮次输入给第一部分状态更新 API 的内容应统一成 `state_update_request`。

### 必填字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `conversation_id` | string | 会话唯一标识 |
| `turn_id` | integer | 当前用户轮次 |
| `schema_version` | string | 当前为 `"0.2.1"` |
| `current_user_message` | string | 当前轮用户原话 |
| `previous_state_snapshot` | object/null | 上一轮状态快照；首轮为 `null` |
| `recent_dialogue_window` | object[] | 最近 1-3 轮原始对话 |
| `update_policy` | object | 状态更新策略 |

### 示例：第 2 轮状态更新请求

```json
{
  "conversation_id": "demo_multiturn_001",
  "turn_id": 2,
  "schema_version": "0.2.1",
  "current_user_message": "主要是高数，我每天都刷题，但考试还是很差。",
  "previous_state_snapshot": {
    "turn_id": 1,
    "dialogue_summary": "用户因持续复习但成绩没有起色而感到疲惫、沮丧和自我怀疑。",
    "user_state_card": {
      "conversation_id": "demo_multiturn_001",
      "turn_id": 1,
      "schema_version": "0.2",
      "problem_summary": "用户觉得持续复习没有带来成绩提升",
      "emotion": ["疲惫", "沮丧", "自我怀疑"],
      "emotion_intensity": 2,
      "need": ["被理解", "被肯定"],
      "support_stage": "comforting",
      "risk_level": "low",
      "risk_signals": [],
      "evidence": ["明明每天都在复习", "成绩还是没有起色", "怎么努力都没有用"],
      "unknowns": ["具体科目不清楚", "是否复盘错因不清楚"],
      "confidence": 0.88
    },
    "risk_memory": {
      "highest_risk_level": "low",
      "risk_signals_seen": [],
      "safety_followup_needed": false
    },
    "open_questions": ["是哪一科或哪类反馈让用户最受挫"]
  },
  "recent_dialogue_window": [
    {
      "turn_id": 1,
      "speaker": "user",
      "content": "我最近真的很累，明明每天都在复习，但成绩还是没有起色。我感觉怎么努力都没有用。"
    },
    {
      "turn_id": 1,
      "speaker": "assistant",
      "content": "听起来你已经绷着坚持了很久，却一直没有看到期待的结果，这种无力感真的会很磨人。"
    },
    {
      "turn_id": 2,
      "speaker": "user",
      "content": "主要是高数，我每天都刷题，但考试还是很差。"
    }
  ],
  "update_policy": {
    "max_summary_chars": 180,
    "max_recent_turns": 3,
    "preserve_risk_memory": true,
    "require_evidence_for_revision": true
  }
}
```

### previous_state_snapshot 结构

| 字段 | 类型 | 说明 |
|---|---|---|
| `turn_id` | integer | 该快照对应的轮次 |
| `dialogue_summary` | string | 到该轮为止的摘要 |
| `user_state_card` | object | 该轮生成的用户状态卡（沿用 v0.2 字段） |
| `risk_memory` | object | 该轮的风险记忆 |
| `open_questions` | string[] | 该轮结束时尚未澄清的问题 |

### 状态更新 API 输出

状态更新 API 输出 `updated_user_state_card`，字段沿用 v0.2 用户状态卡。

输出必须解释：

- 哪些事实被继承；
- 当前轮新增了什么证据；
- 哪些字段被修正；
- 为什么修正；
- 还有哪些 open questions；
- 风险记忆是否变化。

## 策略决策请求：`strategy_decision_request`

第二部分 API 不维护完整历史。它读取第一部分输出的最新状态卡。

输入结构：

```json
{
  "conversation_id": "demo_multiturn_001",
  "turn_id": 2,
  "schema_version": "0.2.1",
  "current_user_message": "主要是高数，我每天都刷题，但考试还是很差。",
  "latest_user_state_card": {
    "conversation_id": "demo_multiturn_001",
    "turn_id": 2,
    "schema_version": "0.2",
    "dialogue_summary": "用户因高数学习挫败感到疲惫和自我怀疑，已说明每天刷题但考试仍差。",
    "support_stage": "exploration",
    "need": ["被理解", "信息澄清", "解决方案"],
    "new_evidence": ["困难科目是高数", "用户每天刷题但考试仍差"],
    "revised_fields": [
      {
        "field": "support_stage",
        "previous_value": "comforting",
        "current_value": "exploration",
        "reason": "用户补充了具体科目和刷题无效的信息，需要先澄清学习方法或错因。"
      }
    ],
    "risk_memory": {
      "highest_risk_level": "low",
      "risk_signals_seen": [],
      "safety_followup_needed": false
    }
  },
  "strategy_references": []
}
```

第二部分输出 `strategy_decision_card`，并使用：

```text
state_basis_turn_id = latest_user_state_card.turn_id
state_change_summary = 根据 revised_fields 和 dialogue_summary 说明本轮策略是否变化
```

第二部分不负责自己维护完整状态，但必须响应第一部分更新后的状态变化。例如：

- `support_stage` 从 `comforting` 变成 `exploration` 时，策略可能从情绪承接切换为澄清；
- `need` 从 `被理解/被肯定` 增加 `解决方案` 时，策略可能逐步靠近建议；
- `risk_level` 上升时，必须进入安全覆盖流程。

## 本地会话记录：`conversation_record`

程序需要把每轮对话和卡片记录到本地。最终 demo 的完整记录不应只保存前两步，而应把四张卡都放进 `turn_records`。骨架如下：

```json
{
  "conversation_id": "demo_multiturn_001",
  "schema_version": "0.2.1",
  "current_turn_id": 2,
  "dialogue_log": [
    {
      "turn_id": 1,
      "speaker": "user",
      "content": "我最近真的很累，明明每天都在复习，但成绩还是没有起色。我感觉怎么努力都没有用。"
    },
    {
      "turn_id": 1,
      "speaker": "assistant",
      "content": "听起来你已经绷着坚持了很久，却一直没有看到期待的结果，这种无力感真的会很磨人。能每天复习到现在，说明你其实很在乎这件事，也付出了不少。最近是哪一次成绩或反馈让你特别觉得"努力没用"？"
    },
    {
      "turn_id": 2,
      "speaker": "user",
      "content": "主要是高数，我每天都刷题，但考试还是很差。"
    },
    {
      "turn_id": 2,
      "speaker": "assistant",
      "content": "原来主要卡在高数，而且你不是没投入，而是每天刷题后考试还是不理想，这确实会让人很挫败。为了先找准问题，你现在更像是错在概念理解，还是计算和题型迁移上？"
    }
  ],
  "turn_records": [
    {
      "turn_id": 1,
      "user_state_card": {},
      "strategy_decision_card": {},
      "behavior_response_card": {
        "text_response": "听起来你已经绷着坚持了很久，却一直没有看到期待的结果，这种无力感真的会很磨人。能每天复习到现在，说明你其实很在乎这件事，也付出了不少。最近是哪一次成绩或反馈让你特别觉得"努力没用"？",
        "strategy_realization": [],
        "uses_previous_context": false,
        "context_used": []
      },
      "evaluation_card": {
        "strategy_consistency": 5,
        "state_update_validity": 5,
        "context_continuity": 5,
        "memory_issues": ["none"]
      }
    },
    {
      "turn_id": 2,
      "state_update_request": {},
      "user_state_card": {},
      "strategy_decision_card": {},
      "behavior_response_card": {
        "text_response": "原来主要卡在高数，而且你不是没投入，而是每天刷题后考试还是不理想，这确实会让人很挫败。为了先找准问题，你现在更像是错在概念理解，还是计算和题型迁移上？",
        "strategy_realization": [],
        "uses_previous_context": true,
        "context_used": ["上一轮用户表达持续努力但成绩没有起色", "当前轮用户补充困难科目是高数"]
      },
      "evaluation_card": {
        "strategy_consistency": 5,
        "state_update_validity": 5,
        "context_continuity": 5,
        "memory_issues": ["none"]
      }
    }
  ],
  "current_state": {
    "dialogue_summary": "用户因高数学习挫败感到疲惫和自我怀疑，已说明每天刷题但考试仍差。",
    "user_state_card": {},
    "risk_memory": {
      "highest_risk_level": "low",
      "risk_signals_seen": [],
      "safety_followup_needed": false
    },
    "open_questions": ["刷题后是否复盘错因", "考试主要失分在哪类题"]
  }
}
```

### 数据结构格式说明

| 顶层字段 | 类型 | 说明 |
|---|---|---|
| `conversation_id` | string | 会话唯一标识 |
| `schema_version` | string | schema 版本号 |
| `current_turn_id` | integer | 当前已推进到的轮次 |
| `dialogue_log` | object[] | 完整原始对话，每条含 `turn_id`、`speaker`、`content` |
| `turn_records` | object[] | 每轮生成的卡片，每条含 `turn_id` 及该轮已完成卡 |
| `current_state` | object | 下一轮要读取的最新摘要和状态 |

### current_state 结构

| 字段 | 类型 | 说明 |
|---|---|---|
| `dialogue_summary` | string | 到当前轮为止的短摘要 |
| `user_state_card` | object | 最新用户状态卡 |
| `risk_memory` | object | 当前风险记忆 |
| `open_questions` | string[] | 尚未澄清的问题 |

## 本地保存原则

必须保存：

- `dialogue_log`：完整原始对话；
- `turn_records`：每轮生成的卡片；
- `current_state`：下一轮要读取的最新摘要和状态；
- 风险相关字段。

不能只保存：

```text
dialogue_summary
```

原因是 summary 会压缩和丢失细节。如果 summary 生成错误，必须能回到原始对话和每轮卡片进行复核。

## 最近窗口与长期记忆

v0.2.1 推荐：

```text
短期输入：最近 1-3 轮原始对话
长期输入：dialogue_summary + current_user_state_card + risk_memory + open_questions
```

这意味着系统不是真的只看两轮，而是：

```text
当前轮原话提供新信息
上一轮状态快照压缩更早历史
最近对话窗口补局部语境
原始日志保留完整可追溯历史
```
