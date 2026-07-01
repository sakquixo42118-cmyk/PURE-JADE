# PURE-JADE

## 项目简介

PURE-JADE 是一个面向情绪支持场景的共情策略生成原型系统项目。

本项目同时服务于：

1. 《人工智能创新导论》课程期末答辩；
2. 璞玉计划阶段性成果汇报。

项目当前目标不是训练一个新的大模型，也不是完整复现论文，而是构建一个基于大模型 API 的模块化原型系统。系统将情绪支持过程拆解为可解释、可控制、可评估的多个阶段，并通过结构化卡片连接各个模块。

## 暂定项目名称

**面向情绪支持场景的共情策略生成原型系统**

## 核心思路

项目采用模块化 LLM Pipeline：

```text
用户输入 / 历史对话
→ 风险优先检测
→ 用户状态卡
→ 共情策略决策卡
→ 行为回应卡
→ 场景应用与评价卡
```

## 当前阶段

当前已经有 v0.2.1 完整链路 runner 和图形 Demo。主链路会串联：

```text
first_v021_boundary_copy
→ run_strategy_pipeline_v021.py
→ third/behavior_generator_api_schema_aligned.py
→ forth/run_full_evaluation.py
```

runner 只做编排、报告组织和工作 record 回填，不修改组员原始 `scripts/first/` 和 `scripts/forth/` 核心源码。

## 运行 Demo

推荐在 Windows 上双击项目根目录：

```text
launch_full_chain_demo.pyw
```

如果 `.pyw` 没有关联到 Python，可使用：

```text
launch_full_chain_demo.cmd
```

命令行方式：

```powershell
python -B scripts\full_chain_frontend\app.py
```

界面默认使用 `rules + dry-run + skip evaluation`，不会误调 API。需要完整 API 链路时，再把策略模式和行为模式切换为 `API（真实调用）`，并取消勾选“跳过评估”。

## 关键文档

- [`docs/README.md`](docs/README.md)：文档总索引和分类入口。
- [`docs/planning/tasks.md`](docs/planning/tasks.md)：项目任务清单和 7 天工作计划。
- [`docs/schema/schema-v0.1.md`](docs/schema/schema-v0.1.md)：四张卡片的统一字段、枚举和 JSON Schema。
- [`docs/schema/schema-v0.2.md`](docs/schema/schema-v0.2.md)：面向多轮对话的状态更新字段、风险记忆和上下文连续性评价。
- [`docs/schema/schema-v0.2.1.md`](docs/schema/schema-v0.2.1.md)：多轮状态更新请求、滚动摘要来源和本地 conversation record 契约。
- [`docs/operations/api-integration.md`](docs/operations/api-integration.md)：OpenAI-compatible API 配置、封装脚本和运行方式。
- [`docs/runbooks/full-chain-v0.2.1-runbook.md`](docs/runbooks/full-chain-v0.2.1-runbook.md)：完整链路 runner、图形 Demo 和评估扩展说明。
- [`docs/strategy/strategy-mapping.md`](docs/strategy/strategy-mapping.md)：研究内容二的策略映射、决策逻辑和 Prompt v0.1。
- [`docs/strategy/strategy-pipeline.md`](docs/strategy/strategy-pipeline.md)：只实现研究内容二 pipeline 的边界、脚本和展示方式。
- [`docs/strategy/strategy-test-results.md`](docs/strategy/strategy-test-results.md)：研究内容二基础与扩展测试的当前结果。
- [`docs/data-and-tests/esconv-usage.md`](docs/data-and-tests/esconv-usage.md)：ESConv 数据集字段、案例抽取和项目融入方式。
- [`docs/data-and-tests/few-shot-selection.md`](docs/data-and-tests/few-shot-selection.md)：few-shot 案例筛选标准和首批策略参考案例说明。
- [`docs/data-and-tests/test-cases-v0.1.md`](docs/data-and-tests/test-cases-v0.1.md)：3 个自建中文测试案例和预期卡片。
- [`docs/data-and-tests/replay-validation.md`](docs/data-and-tests/replay-validation.md)：本地回放校验脚本的运行方式和检查项。
- [`docs/operations/report-organization.md`](docs/operations/report-organization.md)：`reports/` 生成报告目录的整理方式。
- [`OTHER/CODEX_CLOUD_HANDOFF.md`](OTHER/CODEX_CLOUD_HANDOFF.md)：云端 Codex 交接摘要。

## 报告结构

完整链路报告按“每场对话一个文件夹”组织：

```text
reports/full_chain_v021/conversations/<conversation_id>/<run_id>/
```

同一场对话的最新 record 会同步到：

```text
reports/full_chain_v021/conversations/<conversation_id>/conversation_record_latest.json
```

## 仓库结构

```text
PURE-JADE/
├── docs/
│   ├── tasks.md
│   ├── schema-v0.1.md
│   ├── schema-v0.2.md
│   ├── schema-v0.2.1.md
│   ├── api-integration.md
│   ├── strategy-mapping.md
│   ├── strategy-pipeline.md
│   ├── strategy-test-results.md
│   ├── esconv-usage.md
│   ├── few-shot-selection.md
│   ├── test-cases-v0.1.md
│   ├── replay-validation.md
│   └── report-organization.md
├── examples/
│   ├── conversation-record-v0.2.1.json
│   ├── multiturn-test-cases-v0.2.json
│   ├── strategy-references-v0.1.json
│   ├── strategy-test-cases-expanded-v0.1.json
│   └── test-cases-v0.1.json
├── scripts/
│   ├── api_smoke_test.py
│   ├── extract_esconv_examples.py
│   ├── pure_jade_api.py
│   ├── run_strategy_pipeline.py
│   ├── run_strategy_pipeline_v021.py
│   └── replay_test_cases.py
├── .env.example
├── data/
│   ├── raw/
│   └── processed/
├── OTHER/
│   └── CODEX_CLOUD_HANDOFF.md
└── PAPER/
    └── 参考论文与翻译材料
```

## 安全边界

本项目是情绪支持场景下的研究原型，不是医疗、心理诊断或危机干预工具。涉及自伤、自杀、伤害他人或即时危险时，系统应进入安全优先流程，并建议联系现实中的可信任人员或当地紧急服务。
