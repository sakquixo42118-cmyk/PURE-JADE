# PURE-JADE Schema v0.2.4

> v0.2.4 是对 v0.2.1 多轮链路的增量补丁，目标是减少“用户原话 -> 状态卡 -> 策略卡”之间的现实任务信息丢失。它不推翻原四段式结构，也不改变行为卡和评价卡的基本 schema。

## 设计目标

v0.2.1/v0.2.3 中，用户说“错过期末考试，我现在感觉要炸了”时，状态卡可能只保留：

```text
risk_level = low
need = ["情绪陪伴"]
support_stage = exploration
```

这会让策略卡滑向 pure comfort，甚至生成“不能提供任何补考或具体行动建议”这类错误禁止项。

v0.2.4 在状态卡和策略请求中增加一个现实任务层：

```text
情绪支持需求 + 现实后果紧急度 + 可行动性
```

## 状态卡增量字段

状态卡仍输出 `schema_version = "0.2"`，但 v0.2.4 runner 会额外保留以下字段：

```json
{
  "practical_urgency": "none | low | medium | high",
  "real_world_consequence": true,
  "consequence_domain": "none | exam | deadline | administrative | interview | appointment | transport | medical | legal | finance | relationship | other",
  "actionability": "not_actionable | unclear | later_action_possible | immediate_action_possible"
}
```

字段含义：

| 字段 | 含义 |
|---|---|
| `practical_urgency` | 现实任务/现实后果的紧急度，不等同于自伤安全风险 |
| `real_world_consequence` | 当前表达是否涉及正在发生或已经发生的现实后果 |
| `consequence_domain` | 现实后果所属领域，如考试、DDL、行政流程、面试、预约、交通 |
| `actionability` | 当前是否适合提供一个现实下一步 |

## need 增量

v0.2.4 允许 `need` 出现：

```text
现实补救
```

典型混合需求：

```json
["情绪陪伴", "现实补救", "信息澄清"]
```

这表示回复不应该在“安慰”和“建议”之间二选一，而应该采用：

```text
简短承接情绪 + 一个低负担现实下一步
```

## 策略请求增量

第二部分 `strategy_decision_request` 新增：

```json
{
  "schema_version": "0.2.4",
  "practical_context": {
    "real_world_consequence": true,
    "practical_urgency": "high",
    "consequence_domain": "exam",
    "actionability": "immediate_action_possible",
    "support_need": ["情绪陪伴", "现实补救", "信息澄清"],
    "source": "state_card"
  }
}
```

如果旧 record 没有 v0.2.4 状态字段，策略模块会根据当前用户原话做窄推断，`source` 标为 `local_inference`。

## 策略约束

当满足：

```text
practical_context.real_world_consequence = true
practical_context.practical_urgency in {medium, high}
```

策略卡不建议是 pure comfort。理想情况下应满足至少一项：

```text
support_intention in {advise, inform}
primary_strategy 或 secondary_strategy 包含 Providing Suggestions / Information
response_timing = offer_next_step
```

合理禁止项是：

```text
不要责备用户
不要保证结果
不要编造学校/机构政策
```

不合理禁止项是：

```text
不能提供任何补考或具体行动建议
禁止联系老师/教务/辅导员
只能先做情绪认可
```

这些属于语义质量判断。v0.2.4 runner 会把疑似问题记录为 `semantic warning`，但不再直接中断主链路；是否扣分或标记失败交给第四部分诊断评价和人工复核。

## 典型样例

用户：

```text
我不小心错过了期末考试，我现在感觉要炸了
```

状态卡应保留：

```json
{
  "need": ["情绪陪伴", "现实补救", "信息澄清"],
  "support_stage": "action",
  "risk_level": "low",
  "practical_urgency": "high",
  "real_world_consequence": true,
  "consequence_domain": "exam",
  "actionability": "immediate_action_possible"
}
```

策略卡目标：

```text
先稳定用户的强烈情绪，再提供一个不承诺结果的现实补救下一步。
```
