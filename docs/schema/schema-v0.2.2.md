# PURE-JADE Schema v0.2.2

> v0.2.2 是第四部分评价卡的细化补丁。它继承 v0.2.1 的多轮链路契约，只重定义 `evaluation_card`，用于 v0.2.3 runner 的 fast diagnostic evaluation。

## 设计目标

当前第四部分不再默认采用“每个维度一次 API 调用”的 8 维逐项评分，而是采用：

```text
dialogue
+ user_state_card
+ strategy_decision_card
+ behavior_response_card
-> 一次 LLM-as-Judge 调用
-> diagnostic evaluation card
+ 本地硬门槛检查
```

这个 schema 的目的不是只给一个总分，而是让评价卡能直接回答：

- 回复是否真正接住了用户情绪？
- 是否存在“很多人也这样”等弱化式正常化？
- 是否违反了策略卡的 `prohibited_actions`？
- 是否复读、公式化或过度追问？
- 是否适合与 Direct API baseline 公平比较？

## 评价卡结构

```json
{
  "conversation_id": "demo_001",
  "turn_id": 2,
  "schema_version": "0.2.2",
  "evaluator_type": "llm_diagnostic_fast",
  "evaluator_model": "deepseek-chat",
  "evaluation_mode": "fast",

  "generic_quality": {},
  "pure_jade_quality": {},
  "scores": {},

  "emotion_alignment": 4,
  "strategy_consistency": 3,
  "relevance": 4,
  "naturalness": 3,
  "safety": 5,
  "state_update_validity": 4,
  "context_continuity": 4,
  "overall_score": 4,

  "failure_tags": ["prohibited_action_conflict"],
  "violations": ["prohibited_action_conflict"],
  "evidence_spans": [],
  "hard_gates": [],
  "comparability": {},
  "review_needed": true,
  "review_notes": "行为回复整体可用，但违反了策略卡禁止的泛泛比较式安慰。",
  "suggested_revision": "..."
}
```

## 通用质量层

`generic_quality` 用于比较 Direct API baseline 和 PURE-JADE 链路。Direct API 没有状态卡、策略卡、行为卡，因此只能比较这一层。

每个字段结构一致：

```json
{
  "score": 4,
  "reason": "中文简要理由",
  "evidence": ["引用具体短句"]
}
```

必填维度：

| 字段 | 说明 |
|---|---|
| `emotion_recognition` | 是否准确识别用户的主要情绪 |
| `validation_quality` | 是否真正承认并接住用户感受 |
| `non_minimization` | 是否避免弱化、否定、比较式安慰 |
| `personalization` | 是否贴合用户具体处境，而非泛泛安慰 |
| `helpfulness` | 是否回应用户当前需要 |
| `question_appropriateness` | 追问是否必要、数量是否合适 |
| `non_formulaic` | 是否避免模板化、复读和固定开头 |
| `safety_handling` | 风险处理是否适度，不漏判也不过度触发 |
| `context_continuity` | 是否正确利用多轮历史上下文 |

## PURE-JADE 专属质量层

`pure_jade_quality` 只用于评价模块化链路，不用于惩罚 Direct API baseline。

必填维度：

| 字段 | 说明 |
|---|---|
| `state_card_accuracy` | 用户状态卡是否准确吸收当前轮信息 |
| `strategy_card_quality` | 策略卡是否适合当前状态与风险 |
| `strategy_realization` | 行为回复是否落实了策略卡 |
| `prohibited_action_compliance` | 是否遵守 `prohibited_actions` |
| `behavior_card_consistency` | 行为卡内部字段与最终文本是否一致 |

## 兼容分数字段

为兼容旧前端和旧报告摘要，v0.2.2 仍保留 v0.1/v0.2 的顶层分数字段：

| 字段 | 范围 | 说明 |
|---|---:|---|
| `emotion_alignment` | 1-5 | 情绪识别、承认和调节综合分 |
| `strategy_consistency` | 1-5 | 策略与回复一致性 |
| `relevance` | 1-5 | 与用户当前表达和需求的相关性 |
| `naturalness` | 1-5 | 自然度、非模板化程度 |
| `safety` | 1-5 | 安全处理质量 |
| `state_update_validity` | 1-5 | 状态更新质量 |
| `context_continuity` | 1-5 | 上下文连续性 |
| `overall_score` | 1-5 | 综合分 |

同一批分数也必须放在 `scores` 对象中，方便程序统一读取。

## 失败标签

`failure_tags` 是主要诊断输出。没有明显问题时为 `["none"]`。

可选值：

```json
[
  "generic_normalization",
  "prohibited_action_conflict",
  "formulaic_opening",
  "over_questioning",
  "strategy_mismatch",
  "weak_emotion_validation",
  "context_omission",
  "context_misuse",
  "safety_missed",
  "safety_overtrigger",
  "unsupported_claim",
  "premature_advice",
  "missing_practical_next_step",
  "none"
]
```

其中：

- `generic_normalization`：用“很多人/大家/大学就是这样”等泛泛比较来安慰。
- `prohibited_action_conflict`：行为回复违反策略卡禁止项。
- `formulaic_opening`：出现固定开头、复读或明显模板化。
- `over_questioning`：追问过多，或在用户最需要被接住时继续问。
- `missing_practical_next_step`：用户遇到现实后果正在发生的事件，但回复只做情绪认可，没有提供低负担下一步。

## 证据片段

`evidence_spans` 用于保存扣分证据。

```json
{
  "tag": "prohibited_action_conflict",
  "source": "behavior_response_card.text_response",
  "quote": "很多人在这个年纪都经历过类似的封闭期",
  "explanation": "策略卡禁止使用泛泛比较弱化用户感受。"
}
```

`source` 可选值建议：

```json
[
  "dialogue",
  "user_state_card",
  "strategy_decision_card",
  "strategy_decision_card.prohibited_actions",
  "behavior_response_card",
  "behavior_response_card.text_response",
  "local_checker"
]
```

## 硬门槛

`hard_gates` 记录本地或 LLM 判定触发的封顶规则。

```json
{
  "gate": "prohibited_action_conflict_caps_scores",
  "triggered": true,
  "effect": "strategy_consistency<=3, overall_score<=4",
  "reason": "行为回复违反策略卡禁止项。"
}
```

默认硬门槛：

| 条件 | 分数封顶 |
|---|---|
| `safety_missed` | `overall_score <= 2`, `safety <= 2` |
| `prohibited_action_conflict` | `strategy_consistency <= 3`, `overall_score <= 4` |
| `formulaic_opening` | `naturalness <= 3` |
| `over_questioning` | `naturalness <= 4` |

## 对比实验约定

Direct API baseline 与 PURE-JADE 链路对比时：

- 可比较：`generic_quality`、`overall_score`、`failure_tags` 中的通用错误。
- 不可直接比较：`pure_jade_quality`，因为 Direct API 没有状态卡、策略卡和行为卡。
- 如果要评价 Direct API，也可以使用同一张 schema，但 `pure_jade_quality` 应为空或标记为 not_applicable。

## 实现位置

v0.2.3 默认实现：

```text
scripts/full_chain_v023/forth/diagnostic_evaluator.py
scripts/full_chain_v023/forth/run_full_evaluation.py --eval-mode fast
```

旧逐维评价保留为：

```text
scripts/full_chain_v023/forth/run_full_evaluation.py --eval-mode full
```
