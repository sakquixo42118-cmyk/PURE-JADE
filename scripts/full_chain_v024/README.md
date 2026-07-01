# PURE-JADE full_chain_v024

这是 v0.2.4 现实任务敏感链路的隔离副本目录，用于和 v0.2.2/v0.2.3 对比测试。

## 目录

- `run_full_chain_v024.py`：v0.2.4 完整链路 runner。
- `first/`：第一部分状态卡副本，新增现实后果、现实紧急度和可行动性字段，并对“错过考试/DDL/预约”等明显事件做本地归一化。
- `strategy/run_strategy_pipeline_v024.py`：第二部分策略决策副本，向 raw request 显式加入 `practical_context`，避免现实事件被压成 pure comfort。
- `behavior/behavior_generator_api_schema_aligned_v024.py`：第三部分行为回应副本，继续要求 `offer_next_step` / `Providing Suggestions` / `Information` 必须落到一个具体、低负担下一步。
- `forth/`：第四部分评估副本，默认使用一次 API 的 v0.2.2 细化诊断评价卡；旧 8 维逐项评价保留为 `--eval-mode full`。
- `pure_jade_api.py`、`run_strategy_pipeline.py`：v0.2.4 副本链路使用的共享依赖。

## 运行示例

```powershell
python -B scripts\full_chain_v024\run_full_chain_v024.py `
  --record examples\conversation-record-v0.2.1.json `
  --strategy-mode rules `
  --behavior-mode dry-run `
  --skip-evaluation `
  --run-id local_v024_dry_run
```

输出目录：

```text
reports/full_chain_v024/conversations/<conversation_id>/<run_id>/
```

## v0.2.4 关键变化

v0.2.4 不是大重构，而是修正“用户原话 -> 状态卡 -> 策略卡”的信息压缩问题：

- 状态卡增加 `practical_urgency`, `real_world_consequence`, `consequence_domain`, `actionability`。
- `need` 允许包含 `现实补救`，不再把考试/截止类事件只归为 `情绪陪伴`。
- 策略请求增加 `practical_context`，旧 record 重跑时也会根据当前用户原话做窄推断。
- 对 `practical_context.real_world_consequence=true` 且 `practical_urgency=medium/high` 的场景，prompt 会引导策略卡避免 comfort-only 和禁止现实帮助；本地只记录 semantic warning，不再让主链路 hard fail。

典型目标输出不是直接解决全部问题，而是：

```text
简短承接情绪 + 一个不承诺结果的现实下一步
```

## 第四部分评价

v0.2.4 默认评价模式：

```powershell
python -B scripts\full_chain_v024\run_full_chain_v024.py `
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
python -B scripts\full_chain_v024\run_full_chain_v024.py `
  --record examples\conversation-record-v0.2.1.json `
  --strategy-mode api `
  --behavior-mode api `
  --eval-mode full
```

## 设计边界

v0.2.4 不修改现有 `scripts/run_full_chain_v021.py`、`scripts/first_v021_boundary_copy/`、`scripts/third/` 或 `scripts/forth/`。如果要比较两版表现，请通过 `scripts/full_chain_frontend/app.py` 的“链路版本”下拉框切换。
