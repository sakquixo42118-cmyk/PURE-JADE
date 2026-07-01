# PURE-JADE full_chain_v023

这是 v0.2.3 优化链路的隔离副本目录，用于和现有 v0.2.1 链路对比测试。

## 目录

- `run_full_chain_v023.py`：v0.2.3 完整链路 runner。
- `first/`：第一部分 v0.2.1 边界副本的再副本。
- `strategy/run_strategy_pipeline_v023.py`：第二部分策略决策副本，提示词减少“默认追问/默认复述”的硬规则。
- `behavior/behavior_generator_api_schema_aligned_v023.py`：第三部分行为回应副本，减少本地固定模板覆盖；安全场景允许一个必要的安全确认问题。
- `forth/`：第四部分评估副本，默认使用一次 API 的 v0.2.2 细化诊断评价卡；旧 8 维逐项评价保留为 `--eval-mode full`。
- `pure_jade_api.py`、`run_strategy_pipeline.py`：v0.2.3 副本链路使用的共享依赖。

## 运行示例

```powershell
python -B scripts\full_chain_v023\run_full_chain_v023.py `
  --record examples\conversation-record-v0.2.1.json `
  --strategy-mode rules `
  --behavior-mode dry-run `
  --skip-evaluation `
  --run-id local_v023_dry_run
```

输出目录：

```text
reports/full_chain_v023/conversations/<conversation_id>/<run_id>/
```

## 第四部分评价

v0.2.3 默认评价模式：

```powershell
python -B scripts\full_chain_v023\run_full_chain_v023.py `
  --message "我感觉大学生活和想象中完全不一样，越来越没劲。" `
  --strategy-mode api `
  --behavior-mode api `
  --eval-mode fast
```

`fast` 模式每个 case 只调用一次 judge API，输出 `schema_version = 0.2.2` 的诊断评价卡，包含：

- `generic_quality`：可与 Direct API baseline 公平比较的通用情绪支持质量。
- `pure_jade_quality`：状态卡、策略卡、行为卡之间的一致性。
- `failure_tags`：如 `prohibited_action_conflict`、`generic_normalization`、`formulaic_opening`、`over_questioning`。
- `evidence_spans`：扣分证据片段。
- `hard_gates`：安全失败、违反禁止项、模板化、过度追问等封顶规则。

旧版逐维 LLM-as-Judge 仍可离线运行：

```powershell
python -B scripts\full_chain_v023\run_full_chain_v023.py `
  --record examples\conversation-record-v0.2.1.json `
  --strategy-mode api `
  --behavior-mode api `
  --eval-mode full
```

## 设计边界

v0.2.3 不修改现有 `scripts/run_full_chain_v021.py`、`scripts/first_v021_boundary_copy/`、`scripts/third/` 或 `scripts/forth/`。如果要比较两版表现，请通过 `scripts/full_chain_frontend/app.py` 的“链路版本”下拉框切换。
