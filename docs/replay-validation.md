# 回放与校验 v0.1

## 文档目的

本文说明如何使用本地脚本回放 `examples/test-cases-v0.1.json` 中的标准测试案例，并检查卡片流程是否符合当前协议。

当前脚本不调用大模型 API。它只验证我们已经人工设计好的 golden cases 是否完整、可复用、可作为后续 Pipeline 的基准。

## 运行命令

在仓库根目录运行：

```powershell
python scripts\replay_test_cases.py
```

默认输入：

```text
examples/test-cases-v0.1.json
examples/strategy-references-v0.1.json
```

默认输出：

```text
reports/final/local/replay_report.json
```

`reports/*.json` 是本地生成报告，已在 `.gitignore` 中忽略。

## 校验内容

脚本会逐个 case 检查：

| 检查项 | 说明 |
|---|---|
| JSON 可解析 | 测试案例和 few-shot 参考案例必须是合法 JSON |
| 必填字段 | 用户状态卡、策略卡、行为回应卡、评价卡必须包含必填字段 |
| 统一字段 | `conversation_id`、`turn_id`、`schema_version` 必须一致 |
| 枚举值 | 情绪、需求、策略、回应时机、回应强度等必须使用固定枚举 |
| few-shot 引用 | `strategy_reference_ids` 和 `esconv_example_ids` 必须能在策略参考案例库中找到 |
| 安全规则 | 高风险案例必须进入 `safety_override`，普通案例不得误用安全流程 |
| 行为落实 | 行为回应卡必须落实策略卡中的主策略和辅助策略 |
| 问题数量 | 每条回应最多包含一个追问 |
| text_span | `strategy_realization.text_span` 必须出现在最终回复文本中 |
| 评价分数 | 评价卡分数必须在 1-5 范围内 |

## 当前结果

当前 3 个自建测试案例应全部通过：

```text
PASS case_learning_frustration_001
PASS case_parent_child_conflict_001
PASS case_lonely_companionship_001
```

如果后续改 Prompt、改 Schema 或改案例导致失败，脚本会输出具体错误，例如：

```text
FAIL case_learning_frustration_001
  ERROR behavior does not realize strategy: Affirmation and Reassurance
```

## 与后续 API Pipeline 的关系

当前阶段：

```text
读取人工标准卡片
-> 校验字段、枚举、引用和策略一致性
```

后续接入 API 后：

```text
用户输入
-> API 生成用户状态卡
-> API 生成策略决策卡
-> API 生成行为回应卡
-> 使用同一套回放脚本校验输出
```

也就是说，回放脚本先验证“协议和测试样本是稳定的”。等 API 接入后，只需要把人工标准卡片替换为模型输出，校验逻辑可以继续使用。

## 自定义路径

如果需要指定文件路径：

```powershell
python scripts\replay_test_cases.py --cases examples\test-cases-v0.1.json --references examples\strategy-references-v0.1.json --report reports\final\local\replay_report.json
```

## 后续扩展

- 增加 `--actual` 参数，用于校验 API 实际输出。
- 增加 Baseline / Pipeline / Pipeline + ESConv few-shot 三组结果对比。
- 增加 Markdown 或 CSV 报告，方便放入答辩材料。
- 将当前文档中的规则拆成可复用的 Python 校验模块。
