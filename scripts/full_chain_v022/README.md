# PURE-JADE full_chain_v022

这是 v0.2.2 优化链路的隔离副本目录，用于和现有 v0.2.1 链路对比测试。

## 目录

- `run_full_chain_v022.py`：v0.2.2 完整链路 runner。
- `first/`：第一部分 v0.2.1 边界副本的再副本。
- `strategy/run_strategy_pipeline_v022.py`：第二部分策略决策副本，提示词减少“默认追问/默认复述”的硬规则。
- `behavior/behavior_generator_api_schema_aligned_v022.py`：第三部分行为回应副本，减少本地固定模板覆盖；安全场景允许一个必要的安全确认问题。
- `forth/`：第四部分评估副本。
- `pure_jade_api.py`、`run_strategy_pipeline.py`：v0.2.2 副本链路使用的共享依赖。

## 运行示例

```powershell
python -B scripts\full_chain_v022\run_full_chain_v022.py `
  --record examples\conversation-record-v0.2.1.json `
  --strategy-mode rules `
  --behavior-mode dry-run `
  --skip-evaluation `
  --run-id local_v022_dry_run
```

输出目录：

```text
reports/full_chain_v022/conversations/<conversation_id>/<run_id>/
```

## 设计边界

v0.2.2 不修改现有 `scripts/run_full_chain_v021.py`、`scripts/first_v021_boundary_copy/`、`scripts/third/` 或 `scripts/forth/`。如果要比较两版表现，请通过 `scripts/full_chain_frontend/app.py` 的“链路版本”下拉框切换。
