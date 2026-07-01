# PURE-JADE full_chain_v026

这是 v0.2.6 evidence-grounded expansion（证据内展开版）的隔离副本目录，基于 `scripts/full_chain_v025/` 创建，用于和 v0.25 以及 Direct API Baseline 做对比测试。

v0.2.6 不改变 PURE-JADE 的四阶段架构，也不推翻 v0.24/v0.25 的安全边界。它主要解决 v0.25 的三个问题：回复过短、过度克制、模板化。

核心原则：

```text
克制不是短，克制是不编造。
允许模型基于用户已经说出的事实展开心理张力、情绪处境和轻度重构；
禁止添加未经证实的新事实、心理诊断、动机判断或责任归因。
```

## 目录

- `run_full_chain_v026.py`：v0.2.6 完整链路 runner。
- `first/`：第一部分状态卡副本，保留 v0.25 的状态继承和现实任务字段。
- `strategy/run_strategy_pipeline_v026.py`：第二部分策略决策副本，加入 evidence-grounded expansion 原则，并避免在 constraints 中写成品句。
- `behavior/behavior_generator_api_schema_aligned_v026.py`：第三部分行为回应副本，允许基于 `recent_dialogue_window` 做自然展开，并增加过短回复的一次 retry。
- `forth/`：第四部分评估副本，沿用 v0.25 的 fast/full 评价模式。
- `pure_jade_api.py`、`run_strategy_pipeline.py`：v0.2.6 副本链路使用的共享依赖。

## 运行示例

```powershell
python -B scripts\full_chain_v026\run_full_chain_v026.py `
  --record examples\conversation-record-v0.2.1.json `
  --strategy-mode rules `
  --behavior-mode dry-run `
  --skip-evaluation `
  --run-id local_v026_dry_run
```

输出目录：

```text
reports/full_chain_v026/conversations/<conversation_id>/<run_id>/
```

## v0.2.6 关键变化

- 策略 prompt 明确允许 `evidence-grounded elaboration`：可以基于用户原话展开心理负担、关系压力、自责机制和轻度重构。
- 策略 prompt 明确禁止在 `constraints` 中写成品句或固定示例句，减少第三部分照抄模板。
- 行为 prompt 要求普通低风险场景使用“具体化情绪张力 + 轻度重构 + 1 个微行动/探索入口 + 降低自责收束”的结构。
- 行为 prompt 强调：安全克制不是短句模板；只要内容来自已有对话事实，就允许自然展开。
- API 行为生成增加最低信息量机制：非安全场景下，如果 `support_intention` 属于 `comfort / affirm / normalize / advise / inform` 且 `text_response` 少于 160 个非空白字符，会触发一次扩展 retry。
- 如果 retry 后仍然过短，报告中保留 `minimum_information_warning`，但不让主链路因为这一点硬失败。

## 评测目标

v0.26 的目标不是“更长版”，而是：

```text
让 PURE-JADE 在保持安全、可解释、少编造的前提下，
恢复大模型基于上下文自然展开情绪支持的能力。
```

建议下一轮评测：

```text
Direct API Baseline vs PURE-JADE v0.2.6
```

重点观察：

- empathy 是否提升；
- contextual_continuity 是否提升；
- naturalness 是否不再像策略卡填空；
- over_inference_control 是否仍能保持不输 Direct API；
- actionability 是否不会因为展开而变成沉重建议。

## 设计边界

v0.2.6 是独立副本，不修改 v0.25。当前版本关系：

```text
v0.24：短、克制、安全，但帮助不足
v0.25：尝试增加字数和微行动，但仍然僵硬
v0.26：允许证据内展开，恢复自然表达能力
```
