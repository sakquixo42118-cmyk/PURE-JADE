# Schema v0.2.1

## 文档目的

Schema v0.2.1 是 v0.2 的补丁版本，重点补齐多轮对话的实现契约：

1. `dialogue_summary` 应该由谁生成；
2. 第二轮及后续轮次输入给状态更新 API 的内容；
3. 程序本地需要保存的 conversation record 结构；
4. 第二部分策略决策如何读取最新状态，而不是自己重建全部历史。

v0.2.1 不推翻 v0.2 的卡片字段。它把 v0.2 中“多轮状态更新”的概念落成可实现的数据结构。

## 版本关系

| 版本 | 作用 |
|---|---|
| v0.1 | 单轮四卡协议，服务 golden cases 和第二部分策略测试 |
| v0.2 | 增加多轮状态更新字段 |
| v0.2.1 | 增加状态更新请求、滚动摘要来源、本地 conversation record |

## 多轮记忆分层

多轮对话不应该只依赖模型自由记忆上下文，也不应该每轮都把完整历史塞进 prompt。

v0.2.1 推荐四层记忆：

| 层级 | 内容 | 是否长期保存 | 用途 |
|---|---|---:|---|
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

## <u>数据对象边界</u>

<u>`conversation_record` 是本地长期记录，负责保存完整原始对话、每轮卡片和最新状态缓存；`current_state` 是其中给下一轮快速读取的最新状态缓存；`state_update_request` 是发给第一部分状态更新 API 的临时请求；`strategy_decision_request` 是发给第二部分策略决策 API 的临时请求。</u>

<u>两类 API 都不会因为使用同一个 API key 自动继承上一轮记忆。所有跨轮信息必须由程序从本地 `conversation_record` 中抽取，并显式放入请求对象。</u>

## `dialogue_summary` 的来源

`dialogue_summary` 由第一部分状态更新模块生成，不由第二部分策略决策模块生成。

<u>首轮可以把 v0.1 式的 `problem_summary` 作为状态卡字段保留，但从多轮协议开始，跨轮摘要应统一使用 `dialogue_summary`，并由第一部分状态更新模块维护。</u>

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

## 状态更新请求：`state_update_request`

第二轮及后续轮次输入给第一部分状态更新 API 的内容应统一成 `state_update_request`。

<u>`state_update_request` 不是完整记忆库，而是每轮从本地 `conversation_record.current_state`、最近对话窗口和当前用户原话中抽取出来的最小必要输入。</u>

### 必填字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `conversation_id` | string | 会话唯一标识 |
| `turn_id` | integer | 当前用户轮次 |
| `schema_version` | string | 当前为 `"0.2.1"` |
| `current_user_message` | string | 当前轮用户原话 |
| `previous_state_snapshot` | object/null | <u>上一轮状态快照；来源于 `conversation_record.current_state`；首轮为 `null`</u> |
| `recent_dialogue_window` | object[] | 最近 1-3 轮原始对话 |
| `update_policy` | object | 状态更新策略 |

### <u>`previous_state_snapshot` 结构</u>

<u>`previous_state_snapshot` 必须根据上一轮结束时的 `conversation_record.current_state` 生成，不应临时让模型猜。非首轮时建议至少包含 `turn_id`、`dialogue_summary`、完整或足够完整的上一轮 `user_state_card`、`risk_memory` 和 `open_questions`。</u>

```json
{
  "turn_id": 1,
  "dialogue_summary": "上一轮结束后的滚动摘要",
  "user_state_card": {
    "...": "上一轮完整 v0.2 用户状态卡"
  },
  "risk_memory": {
    "highest_risk_level": "low",
    "risk_signals_seen": [],
    "safety_followup_needed": false
  },
  "open_questions": []
}
```

### 示例：第 2 轮状态更新请求

<u>下面示例中的 `previous_state_snapshot.user_state_card` 应保留上一轮状态卡的关键 v0.2 字段，以支持“继承、修正、新增证据”的可解释判断。</u>

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

<u>第二部分的输入边界是 `current_user_message + latest_user_state_card + optional strategy_references`。其中 `latest_user_state_card` 已经携带 `dialogue_summary`、`new_evidence`、`revised_fields` 和 `risk_memory`，因此第二部分不应该再读取完整 `conversation_record` 或自己生成滚动摘要。</u>

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

## 本地会话记录：`conversation_record`

程序需要把每轮对话和卡片记录到本地。最终 demo 的完整记录不应只保存前两步，而应把四张卡都放进 `turn_records`。完整可运行示例见 `examples/conversation-record-v0.2.1.json`，骨架如下：

<u>`conversation_record.current_state.user_state_card` 应优先保存最新完整 v0.2 用户状态卡；如果为了界面展示另做精简视图，应另设派生字段，避免影响下一轮 `previous_state_snapshot` 的构造。</u>

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
      "content": "听起来你已经绷着坚持了很久，却一直没有看到期待的结果，这种无力感真的会很磨人。能每天复习到现在，说明你其实很在乎这件事，也付出了不少。最近是哪一次成绩或反馈让你特别觉得“努力没用”？"
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
        "text_response": "听起来你已经绷着坚持了很久，却一直没有看到期待的结果，这种无力感真的会很磨人。能每天复习到现在，说明你其实很在乎这件事，也付出了不少。最近是哪一次成绩或反馈让你特别觉得“努力没用”？",
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

## 本地保存原则

必须保存：

- `dialogue_log`：完整原始对话；
- `turn_records`：每轮生成的卡片；
- <u>`current_state`：下一轮构造 `previous_state_snapshot` 时要读取的最新摘要、完整最新状态卡、风险记忆和未解问题；</u>
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

## 对现有代码的影响

当前已有：

```text
scripts/run_strategy_pipeline.py
scripts/run_strategy_pipeline_v021.py
scripts/replay_test_cases.py
```

其中 `run_strategy_pipeline.py` 和 `replay_test_cases.py` 仍服务 v0.1 单轮/第二部分测试；`run_strategy_pipeline_v021.py` 已用于从 v0.2.1 `conversation_record` 中读取最新用户状态卡，并跑通第二部分策略决策。

v0.2.1 后续仍需要新增或扩展：

```text
scripts/run_multiturn_demo.py
scripts/replay_multiturn_cases.py
```

建议最小实现顺序：

1. 先实现本地 `conversation_record` 的读写；
2. 再实现状态更新 mock/rules 模式；
3. 再接入状态更新 API；
4. 最后把第二部分策略 API 接到最新 `user_state_card` 后面。

当前 `run_strategy_pipeline_v021.py` 已经覆盖第 4 步中的第二部分读取方式，但还没有实现第 1-3 步的完整 record 读写和状态更新生成。
