# 报告目录说明

`reports/` 存放本地运行生成的 JSON 报告，默认不提交到 git。

## 目录结构

```text
reports/
├── final/
│   ├── api/
│   └── local/
└── debug/
    ├── single-case/
    └── failed-runs/
```

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
