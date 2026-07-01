# PURE-JADE full_chain_v025

这是 v0.2.5 情绪深度与微行动版的隔离副本目录，用于和 v0.2.4、Direct API Baseline 做对比测试。

v0.2.5 不推翻 v0.2.4 的现实任务敏感逻辑，而是在最终回复质量上做一层收束：低风险情绪支持不再只追求短句和快速建议，而是要求更饱满的情绪承接、轻度重构、一个低负担微行动或温和探索入口。

## 目录

- `run_full_chain_v025.py`：v0.2.5 完整链路 runner。
- `first/`：第一部分状态卡副本，保留现实后果、现实紧急度和可行动性字段。
- `strategy/run_strategy_pipeline_v025.py`：第二部分策略决策副本，在 v0.2.4 的 `practical_context` 基础上增加回复质量约束，避免 comfort-only、过早建议和“禁止微行动”的滑坡。
- `behavior/behavior_generator_api_schema_aligned_v025.py`：第三部分行为回应副本，把普通低风险回复目标放宽到通常 3-6 句、约 180-320 字，最大 520 字。
- `forth/`：第四部分评估副本，默认使用一次 API 的 v0.2.2 细化诊断评价卡；旧 8 维逐项评价保留为 `--eval-mode full`。
- `pure_jade_api.py`、`run_strategy_pipeline.py`：v0.2.5 副本链路使用的共享依赖。

## 运行示例

```powershell
python -B scripts\full_chain_v025\run_full_chain_v025.py `
  --record examples\conversation-record-v0.2.1.json `
  --strategy-mode rules `
  --behavior-mode dry-run `
  --skip-evaluation `
  --run-id local_v025_dry_run
```

输出目录：

```text
reports/full_chain_v025/conversations/<conversation_id>/<run_id>/
```

## v0.2.5 关键变化

- 状态卡继续保留 `practical_urgency`, `real_world_consequence`, `consequence_domain`, `actionability`。
- 策略卡新增质量目标：普通低风险情绪支持应包含情绪承接、轻度重构、微行动或温和探索入口、温和收束。
- `support_intention=comfort/affirm/normalize` 不再自动滑坡成“不能提供任何帮助”；禁止项会避开沉重方案和过早解决，而不是禁止所有微行动。
- 行为卡放宽长度：普通低风险场景通常 3-6 句、约 180-320 字；最大 520 字。
- 对考试、DDL、预约等现实后果场景，仍保留 v0.2.4 的现实补救方向，但要求先充分承接情绪，再给 1-2 个低负担下一步。

典型目标输出：

```text
接住最强情绪 + 轻度重构 + 一个小到能做的微行动/探索入口 + 降低自责的收束
```

## 第四部分评价

v0.2.5 默认评价模式：

```powershell
python -B scripts\full_chain_v025\run_full_chain_v025.py `
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
python -B scripts\full_chain_v025\run_full_chain_v025.py `
  --record examples\conversation-record-v0.2.1.json `
  --strategy-mode api `
  --behavior-mode api `
  --eval-mode full
```

## 设计边界

v0.2.5 是独立副本，不修改 v0.2.4 的 runner 和四个阶段代码。前端可通过“链路版本”下拉框切换 v0.2.4、v0.2.5 或 Direct API Baseline。
