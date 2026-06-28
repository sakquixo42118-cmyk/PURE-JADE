# 自建测试案例 v0.1

## 文档目的

本文定义 PURE-JADE 第一批自建测试案例，用于验证卡片流程是否能稳定串通：

```text
用户输入
-> 用户状态卡
-> 共情策略决策卡
-> 行为回应卡
-> 评价卡
```

这些案例是中文 Demo 的自建样本，不来自 ESConv。ESConv 只通过 few-shot 策略参考案例辅助“用户状态 -> 策略决策”这一步。

机器可读版本位于：

```text
examples/test-cases-v0.1.json
```

## 使用方式

每个测试案例包含：

| 字段 | 说明 |
|---|---|
| `dialogue` | 原始用户输入 |
| `expected_user_state_card` | 预期用户状态卡 |
| `strategy_reference_ids` | 建议放入策略决策 Prompt 的 few-shot 参考案例 ID |
| `expected_strategy_decision_card` | 预期策略决策卡 |
| `expected_behavior_response_card` | 预期行为回应卡 |
| `expected_evaluation_card` | 预期评价卡和人工复核重点 |

推荐测试顺序：

1. 不使用 few-shot，只用原始用户输入生成用户状态卡和策略卡。
2. 使用 `strategy_reference_ids` 对应案例，再生成策略卡。
3. 比较两次输出在策略选择、约束完整性和安全边界上的差异。
4. 最后再生成行为回应卡，检查是否落实策略卡，而不是自由发挥。

## 案例 1：学习挫败场景

用户输入：

```text
我最近真的很累，明明每天都在复习，但成绩还是没有起色。我感觉怎么努力都没有用。
```

预期用户状态：

- 情绪：`疲惫`、`沮丧`、`自我怀疑`
- 需求：`被理解`、`被肯定`
- 支持阶段：`comforting`
- 风险等级：`low`

建议 few-shot：

- `esconv_1181_t009`
- `esconv_0570_t014`
- `esconv_1181_t011`

预期策略：

- `support_intention`: `comfort`
- `primary_strategy`: `Reflection of feelings`
- `secondary_strategy`: `Affirmation and Reassurance`
- `response_timing`: `respond_now`
- `response_intensity`: `gentle`

检查重点：

- 是否先承接努力无效带来的无力感。
- 是否具体肯定持续复习的投入。
- 是否避免直接给学习方法。
- 是否最多提出一个问题。

## 案例 2：亲子沟通场景

用户输入：

```text
我跟我妈一说话就吵，她总觉得我不够努力。我也不知道怎么跟她解释，越说越烦。
```

预期用户状态：

- 情绪：`愤怒`、`困惑`、`压力`
- 需求：`被理解`、`信息澄清`、`表达空间`
- 支持阶段：`exploration`
- 风险等级：`low`

建议 few-shot：

- `esconv_1230_t006`
- `esconv_0842_t020`
- `esconv_0176_t012`

预期策略：

- `support_intention`: `clarify`
- `primary_strategy`: `Restatement or Paraphrasing`
- `secondary_strategy`: `Question`
- `response_timing`: `ask_clarification`
- `response_intensity`: `gentle`

检查重点：

- 是否先复述“被误解 + 沟通受阻”的模式。
- 是否避免替用户或母亲站队。
- 是否避免评价家长人格。
- 是否只问一个关键问题。

## 案例 3：孤独陪伴场景

用户输入：

```text
室友周末都有安排，我一个人待在宿舍，感觉大家都有自己的生活，只有我特别多余。
```

预期用户状态：

- 情绪：`孤独`、`沮丧`、`自我怀疑`
- 需求：`被理解`、`情绪陪伴`、`被肯定`
- 支持阶段：`comforting`
- 风险等级：`low`

建议 few-shot：

- `esconv_0176_t012`
- `esconv_0570_t014`
- `esconv_1181_t011`

预期策略：

- `support_intention`: `comfort`
- `primary_strategy`: `Reflection of feelings`
- `secondary_strategy`: `Affirmation and Reassurance`
- `response_timing`: `respond_now`
- `response_intensity`: `gentle`

检查重点：

- 是否先陪伴和承接孤独感。
- 是否避免直接要求用户主动社交。
- 是否降低“独处 = 多余”的自我判断。
- 是否最多提出一个问题。

## 与 ESConv few-shot 的关系

这 3 个案例本身是自建中文测试案例，不用于训练模型，也不从 ESConv 复制内容。

它们使用的 ESConv few-shot 只来自：

```text
examples/strategy-references-v0.1.json
```

few-shot 的作用是帮助策略决策模块判断：

- 当前更适合先澄清，还是先安慰。
- 是否应该选择 `Reflection of feelings`、`Question`、`Restatement or Paraphrasing` 等策略。
- 生成约束中是否应加入“不要急于建议”“最多一个问题”“不站队”等限制。

few-shot 不应进入最终行为回应 Prompt，避免模型复用 ESConv 数据集中的原始表达。

## 后续评估

后续最小实验可以使用三组对比：

| 组别 | 输入 | 目的 |
|---|---|---|
| Baseline | 只给用户输入，直接生成回复 | 观察普通 API 回复质量 |
| Pipeline | 用户输入 + 卡片流程，不使用 few-shot | 验证结构化流程本身的收益 |
| Pipeline + ESConv few-shot | 用户输入 + 卡片流程 + 策略参考案例 | 验证 ESConv 对策略决策的辅助作用 |

评价指标沿用 `expected_evaluation_card`：

- 情绪匹配
- 策略一致性
- 相关性
- 自然度
- 安全性
- 是否存在说教、过度建议、策略不一致等问题
