# Few-shot 案例筛选方案 v0.1

## 文档目的

本文定义如何从 ESConv 中筛选 few-shot 参考案例，并说明这些案例如何进入 PURE-JADE 的共情策略决策 Prompt。

结论先行：

- ESConv few-shot 主要服务研究内容二，也就是“用户状态 -> 共情策略决策”。
- few-shot 案例不进入最终回复生成 Prompt。
- few-shot 案例不保留 ESConv 原始支持者回复全文，只保留策略判断摘要。
- 首批案例只覆盖常见、低风险、边界清晰的策略场景。

## 为什么不直接使用 80 条自动抽样

`data/processed/esconv_examples_sample.jsonl` 是每类策略自动取 10 条得到的候选池。它适合做初筛，但不适合直接放进 Prompt，原因包括：

- 存在开场寒暄、结束语、survey 操作提示等低价值片段。
- 有些上下文太短，看不出用户状态。
- 有些样例虽然有策略标签，但策略和内容并不典型。
- 有些原始回复包含过强建议、过时信息或不适合中文 Demo 的表达。
- 如果把原始回复全文放进最终生成 Prompt，模型可能复用数据集措辞。

因此需要把 ESConv 案例转成“策略卡参考案例”。

## 筛选标准

### 入选标准

优先选择满足以下条件的案例：

| 标准 | 说明 |
|---|---|
| 上下文清楚 | 至少能看出用户的事件、情绪或需求 |
| 策略典型 | ESConv 标签和对话走向匹配，适合作为该策略示例 |
| 低风险 | 不涉及自伤、自杀、暴力、医疗诊断等高风险处理 |
| 可迁移 | 能迁移到中文情绪支持 Demo，而不是强依赖英文文化或政策背景 |
| 可解释 | 能写出“为什么选这个策略”的理由 |
| 不依赖原文 | 即使不看原始回复，也能总结出策略模式 |

### 剔除标准

以下案例不进入首批 few-shot：

- 纯寒暄，例如 “Hello, how are you?”。
- 结束语或任务平台提示，例如要求用户点击 survey。
- `Others` 标签案例，因为它是兜底类，容易污染策略判断。
- 涉及危险行为、医疗建议、法律建议或专业结论的案例。
- 策略含混，难以说明为什么选该策略的案例。
- 需要复制原始回复才能发挥作用的案例。

## 首批覆盖策略

首批 few-shot 覆盖 7 类策略：

| 策略 | 数量 | 说明 |
|---|---:|---|
| `Question` | 2 | 信息不足或需要识别下一步资源时使用 |
| `Restatement or Paraphrasing` | 2 | 用户表达复杂，需要整理和确认时使用 |
| `Reflection of feelings` | 2 | 情绪强、需要先承接时使用 |
| `Affirmation and Reassurance` | 2 | 用户自我否定或羞耻时使用 |
| `Providing Suggestions` | 2 | 用户主动寻求办法，适合给低门槛建议时使用 |
| `Information` | 2 | 用户需要事实、资源方向或可查信息时使用 |
| `Self-disclosure` | 2 | 用简短自我披露降低孤立感，但必须服务用户 |

`Others` 暂不纳入首批 few-shot。后续只在人工复核和错误分析中使用。

## 参考案例格式

首批 few-shot 存放在：

```text
examples/strategy-references-v0.1.json
```

每条案例使用以下结构：

```json
{
  "example_id": "esconv_0176_t012",
  "source": "ESConv",
  "source_policy": "summary_only_no_original_response",
  "problem_type": "problems with friends",
  "emotion_type": "sadness",
  "situation_summary_zh": "用户因疫情防护无法参与朋友活动，感到被朋友疏远。",
  "inferred_user_state": {
    "emotion": ["孤独", "沮丧"],
    "need": ["信息澄清", "解决方案"],
    "support_stage": "exploration"
  },
  "strategy_reference": {
    "support_intention": "clarify",
    "primary_strategy": "Question",
    "strategy_reason": "用户已经表达困境，但还不清楚是否有其他可支持的人际资源。",
    "response_pattern": "先承接用户的孤立感，再提出一个关于可用支持资源的开放问题。"
  },
  "prompt_use_notes": [
    "只学习策略判断逻辑，不学习原始措辞。",
    "适合用于孤独、朋友疏远、信息不足的场景。"
  ]
}
```

## 如何放进策略决策 Prompt

策略决策 Prompt 的输入结构建议为：

```text
[原始对话]
{{dialogue}}

[用户状态卡]
{{user_state_card_json}}

[ESConv 策略参考案例]
{{strategy_references_json}}

[要求]
请输出 strategy_decision_card。参考案例只用于判断策略，不得复制或改写 ESConv 原始回复。
```

注意：

- 每次只放 2-3 个最相关案例。
- 案例只进入策略决策 Prompt，不进入行为回应 Prompt。
- 如果没有合适案例，使用空数组，不要强行匹配。
- 当前用户状态卡与参考案例冲突时，优先服从当前用户状态卡和安全规则。

## 检索与匹配规则 v0.1

第一版可以不用向量数据库，先使用规则匹配：

1. 如果 `risk_level = high`，不使用 ESConv few-shot，直接进入安全流程。
2. 先按 `support_stage` 过滤案例。
3. 再按 `need` 和 `emotion` 选择相近案例。
4. 如果用户主动询问“怎么办”，优先给 `Providing Suggestions` 或 `Information` 案例。
5. 如果用户主要表达难过、压力、羞耻、自我怀疑，优先给 `Reflection of feelings` 或 `Affirmation and Reassurance` 案例。
6. 如果用户表达复杂且信息不足，优先给 `Question` 或 `Restatement or Paraphrasing` 案例。

## 答辩表述

可以这样说明：

> 我们没有直接复制 ESConv 的回复，也没有把 ESConv 当作最终答案库。我们将 ESConv 中具有代表性的对话片段转写为策略参考案例，只保留用户状态、策略标签、策略理由和回应模式，用于辅助共情策略决策模块选择更合理的策略。

## 后续工作

- 人工复核首批 14 条策略参考案例。
- 为中文 Demo 补充 3 个自建测试案例。
- 编写简单规则检索函数，从 14 条案例中选择最相关的 2-3 条。
- 在策略决策 Prompt 中比较无 few-shot 和有 few-shot 的输出差异。
