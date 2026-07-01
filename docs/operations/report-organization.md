# 报告目录说明

`reports/` 存放本地运行生成的 JSON 报告，默认不提交到 git。

## 目录结构

```text
reports/
├── full_chain_v021/
│   └── conversations/
│       └── <conversation_id>/
│           ├── conversation_record_latest.json
│           ├── latest_run_summary.json
│           └── <run_id>/
├── final/
│   ├── api/
│   └── local/
└── debug/
    ├── single-case/
    └── failed-runs/
```

## full_chain_v021/conversations

当前完整链路 runner 的主输出目录。原则是“每场对话一个文件夹”，同一场对话的多轮运行都放在同一个 `<conversation_id>` 目录下。

单次运行目录包含：

| 文件 | 内容 |
|---|---|
| `01_first_state_report.json` | 第一部分状态卡报告 |
| `02_strategy_report.json` | 第二部分策略卡报告 |
| `03_behavior_report.json` | 第三部分行为卡报告 |
| `04_evaluation_cases.json` | 最新轮评估输入 |
| `05_evaluation_report.json` | 最新轮卡片评估 |
| `06_all_turn_evaluation_cases.json` | 全部已完成轮次评估输入 |
| `07_all_turn_evaluation_report.json` | 全部已完成轮次卡片评估 |
| `08_conversation_summary_report.json` | 本地结构化对话汇总 |
| `09_dialogue_review_report.json` | 本地全对话复盘，不额外调用 API |
| `conversation_record_v021_chain.json` | 本次运行使用的工作 record |
| `full_chain_summary.json` | runner 总结 |

对话目录下的 `conversation_record_latest.json` 和 `latest_run_summary.json` 指向最新一次运行，便于继续对话。

## final/api

用于答辩和阶段性汇报的 API 最终结果。

| 文件 | 内容 |
|---|---|
| `strategy_pipeline_api_report.json` | 基础 3 个 case，使用 ESConv 参考 |
| `strategy_pipeline_api_no_references_report.json` | 基础 3 个 case，不使用 ESConv 参考 |
| `strategy_pipeline_api_expanded_report.json` | 扩展 8 个 case，使用 ESConv 参考 |
| `strategy_pipeline_api_expanded_no_references_report.json` | 扩展 8 个 case，不使用 ESConv 参考 |

## final/local

用于本地备用演示和非 API 校验。

| 文件 | 内容 |
|---|---|
| `replay_report.json` | 完整 golden cases 回放校验 |
| `strategy_pipeline_report.json` | 基础 3 个 case，rules 模式 |
| `strategy_pipeline_no_references_report.json` | 基础 3 个 case，rules 模式，不使用 ESConv 参考 |
| `strategy_pipeline_rules_expanded_report.json` | 扩展 8 个 case，rules 模式 |
| `strategy_pipeline_mock_report.json` | 基础 3 个 case，mock 模式 |
| `strategy_pipeline_mock_no_references_report.json` | 基础 3 个 case，mock 模式，不使用 ESConv 参考 |
| `strategy_pipeline_mock_expanded_report.json` | 扩展 8 个 case，mock 模式 |

## debug

调试用，不建议放入答辩结论。

| 目录 | 内容 |
|---|---|
| `debug/single-case/` | 单个 case 的调试运行结果 |
| `debug/failed-runs/` | prompt 调整过程中的失败或中间结果 |

## 使用建议

答辩中优先引用：

```text
reports/final/api/strategy_pipeline_api_report.json
reports/final/api/strategy_pipeline_api_expanded_report.json
```

对照实验引用：

```text
reports/final/api/strategy_pipeline_api_no_references_report.json
reports/final/api/strategy_pipeline_api_expanded_no_references_report.json
```

如果现场 API 不可用，使用 `reports/final/local/` 中的 rules 或 mock 报告作为备用演示依据。
