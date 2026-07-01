# PURE-JADE 文档索引

本文档是 `docs/` 的入口索引。原先所有文档都放在同一层，现在按用途分为几类。

## 运行与交付

- [v0.2.1 完整链路运行说明](runbooks/full-chain-v0.2.1-runbook.md)
- [Full-chain 图形前端说明](../scripts/full_chain_frontend/README.md)
- [2026-06-30 工作过程总结](worklog/2026-06-30-codex-work-summary.md)
- [2026-07-01 完整链路 Demo 优化与 API 测试总结](worklog/2026-07-01-full-chain-demo-test-summary.md)

## 规划

- [任务清单与阶段计划](planning/tasks.md)

## Schema 与协议

- [Schema v0.1](schema/schema-v0.1.md)
- [Schema v0.2](schema/schema-v0.2.md)
- [Schema v0.2.1](schema/schema-v0.2.1.md)
- [Schema v0.2.2](schema/schema-v0.2.2.md)
- [Schema v0.2.4](schema/schema-v0.2.4.md)

## 策略决策模块

- [策略映射说明](strategy/strategy-mapping.md)
- [策略 pipeline 说明](strategy/strategy-pipeline.md)
- [策略测试结果](strategy/strategy-test-results.md)

## 数据、案例与验证

- [ESConv 使用说明](data-and-tests/esconv-usage.md)
- [Few-shot 案例筛选说明](data-and-tests/few-shot-selection.md)
- [自建测试案例 v0.1](data-and-tests/test-cases-v0.1.md)
- [回放验证说明](data-and-tests/replay-validation.md)

## 运行配置与报告

- [API 接入说明](operations/api-integration.md)
- [报告目录整理说明](operations/report-organization.md)
- [硬编码推理规则审计](operations/hard-coded-inference-rules.md)

## 当前推荐主链路

```text
scripts/first_v021_boundary_copy/main.py
-> scripts/run_strategy_pipeline_v021.py
-> scripts/third/behavior_generator_api_schema_aligned.py
-> scripts/forth/run_full_evaluation.py
```

推荐使用统一 runner：

```powershell
python -B scripts\run_full_chain_v021.py `
  --message "我最近复习很累，感觉怎么努力都没用。" `
  --strategy-mode api `
  --behavior-mode api `
  --eval-stage empathetic_actions `
  --eval-scope current-turn
```

图形 Demo 推荐双击项目根目录：

```text
launch_full_chain_demo.pyw
```

完整链路输出按对话分组：

```text
reports/full_chain_v021/conversations/<conversation_id>/<run_id>/
```

## 维护约定

- `scripts/first/` 保留组员原始 first 核心版本，不作为整合链路的修改点。
- `scripts/forth/` 保留组员原始 forth 评估源码，不作为整合链路的修改点。
- 新增整合逻辑优先放在独立 runner 或副本目录中。
- `.env`、`*.env`、真实 API key 不应提交到 Git。
