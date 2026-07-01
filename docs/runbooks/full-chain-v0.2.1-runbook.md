# v0.2.1 完整链路运行说明

本文档说明如何运行当前推荐的 PURE-JADE 完整链路。

## 链路范围

当前 runner 串联四个部分：

```text
first_v021_boundary_copy
-> run_strategy_pipeline_v021.py
-> third/behavior_generator_api_schema_aligned.py
-> forth/run_full_evaluation.py
```

对应文件：

- `scripts/first_v021_boundary_copy/main.py`
- `scripts/run_strategy_pipeline_v021.py`
- `scripts/third/behavior_generator_api_schema_aligned.py`
- `scripts/forth/run_full_evaluation.py`
- `scripts/run_full_chain_v021.py`

`scripts/run_full_chain_v021.py` 是独立编排层，不内嵌四部分核心逻辑。运行时仍然需要上述原有代码文件存在。

## 环境配置

根目录 `.env` 使用第二部分统一 API 配置：

```text
PURE_JADE_API_URL=https://api.deepseek.com
PURE_JADE_API_KEY=replace-with-your-api-key
PURE_JADE_API_MODEL=deepseek-v4-pro
PURE_JADE_API_TEMPERATURE=0.2
PURE_JADE_API_TIMEOUT_SECONDS=120
PURE_JADE_API_MAX_RETRIES=1
PURE_JADE_API_JSON_MODE=1
```

注意：

- 不要提交 `.env`。
- `.env.example` 只能放占位符。
- 如果 API provider 不支持 JSON mode，把 `PURE_JADE_API_JSON_MODE` 设为 `0`。

## 安装依赖

完整链路会 import `first_v021_boundary_copy/main.py`，因此需要 first v0.2.1 副本的依赖：

```powershell
python -m pip install -r scripts\first_v021_boundary_copy\requirements.txt
```

如果当前网络环境使用 SOCKS 代理，`socksio` 必须存在；`first_v021_boundary_copy/requirements.txt` 已包含它。

## 快速无评估验证

使用已有 conversation record，跳过 first，策略用本地规则，行为生成只 dry-run，不调用第四部分评估：

```powershell
python -B scripts\run_full_chain_v021.py `
  --record examples\conversation-record-v0.2.1.json `
  --strategy-mode rules `
  --behavior-mode dry-run `
  --skip-evaluation `
  --run-id local_dry_run
```

这个命令主要验证编排、工作副本、策略卡回填和第三部分输入构造是否正常。

## 从用户输入开始跑完整链路

```powershell
python -B scripts\run_full_chain_v021.py `
  --message "我最近复习很累，感觉怎么努力都没用。" `
  --strategy-mode api `
  --behavior-mode api `
  --eval-stage empathetic_actions `
  --run-id demo_final_cn
```

这会真实调用 API，并执行第四部分评估。评估阶段耗时和 API 消耗明显高于前几段。

## 使用已有 record 跑完整链路

```powershell
python -B scripts\run_full_chain_v021.py `
  --record examples\conversation-record-v0.2.1.json `
  --strategy-mode api `
  --behavior-mode api `
  --eval-stage empathetic_actions `
  --run-id demo_record_api
```

`--record` 模式会跳过 first 阶段，直接从已有 v0.2.1 `conversation_record` 开始。

## 图形前端

推荐双击项目根目录的无命令行启动入口：

```text
launch_full_chain_demo.pyw
```

如果 `.pyw` 没有关联到 Python，使用备用入口：

```text
launch_full_chain_demo.cmd
```

也可以用命令行启动独立 Tkinter 前端：

```powershell
python -B scripts\full_chain_frontend\app.py
```

该前端不会 import 或修改 `scripts/first/`、`scripts/first_v021_boundary_copy/`、`scripts/third/`、`scripts/forth/` 的核心代码，只会以 subprocess 调用 `scripts/run_full_chain_v021.py`。界面支持新对话、继续对话和仅重跑 record。为了避免误点消耗 API 余额，界面默认使用 `rules + dry-run + skip evaluation`，需要完整 API 链路时再手动切换为 `api + api` 并打开评估。

## 输出文件

默认输出目录：

```text
reports/full_chain_v021/conversations/<conversation_id>/<run_id>/
```

同一场对话的多轮运行会归到同一个 `<conversation_id>` 文件夹下；该文件夹还会维护：

```text
conversation_record_latest.json
latest_run_summary.json
```

关键文件：

- `conversation_record_v021_chain.json`：完整链路工作副本，不覆盖原始 record。
- `01_first_state_report.json`：first 阶段状态卡生成报告，仅 `--message` 模式存在。
- `02_strategy_report.json`：第二部分策略决策报告。
- `03_behavior_report.json`：第三部分行为响应报告。
- `04_evaluation_cases.json`：给 forth 评估使用的最新轮 cases 文件。
- `05_evaluation_report.json`：最新轮卡片评估报告。
- `06_all_turn_evaluation_cases.json`：所有已完成轮次的评估输入。
- `07_all_turn_evaluation_report.json`：所有已完成轮次的卡片评估报告。
- `08_conversation_summary_report.json`：本地结构化汇总报告。
- `09_dialogue_review_report.json`：本地全对话复盘报告，不额外调用 API。
- `full_chain_summary.json`：runner 汇总结果。

## 评估扩展

当前有两类评估扩展：

1. 卡片评估：继续调用 `scripts/forth/run_full_evaluation.py`，可通过 `--eval-scope current-turn|all-turns|both` 控制评估最新轮、全部已完成轮次或两者。
2. 全对话复盘：runner 根据 `dialogue_log`、状态轨迹、策略轨迹和已有评估报告生成 `09_dialogue_review_report.json`，不额外调用模型，不修改 forth。

## 常用参数

- `--message`：从一条用户输入开始跑 first。
- `--record`：使用已有 v0.2.1 conversation record，跳过 first。
- `--strategy-mode rules|mock|api`：第二部分模式。
- `--behavior-mode dry-run|mock|api`：第三部分模式。
- `--skip-evaluation`：跳过第四部分评估。
- `--eval-scope current-turn|all-turns|both`：控制卡片评估范围。
- `--env-file .env`：指定 API 配置文件，默认根目录 `.env`。
- `--api-url` / `--api-model`：临时覆盖 `.env` 中的 API 地址和模型。
- `--run-id`：指定输出目录名，便于答辩或复现实验。

## 设计边界

- runner 只负责编排、复制工作 record、回填中间卡片、生成评估输入和汇总报告。
- runner 不修改 `scripts/first/` 原始核心代码。
- runner 不修改 `scripts/forth/` 评估源码。
- 第二、三部分的 schema 校验仍由各自脚本负责。
- 第四部分仍通过 `scripts/forth/run_full_evaluation.py` 执行。

## 已验证命令

已验证通过：

```powershell
python -B scripts\run_full_chain_v021.py `
  --record examples\conversation-record-v0.2.1.json `
  --strategy-mode rules `
  --behavior-mode dry-run `
  --skip-evaluation `
  --run-id codex_chain_dry_run
```

已验证完整 API 链路通过：

```powershell
python -B scripts\run_full_chain_v021.py `
  --record examples\conversation-record-v0.2.1.json `
  --strategy-mode api `
  --behavior-mode api `
  --eval-stage empathetic_actions `
  --run-id codex_chain_api_record
```

该次完整 API 链路输出的 fourth 评估结果为 `v0.1=5/5`，无 violations。
