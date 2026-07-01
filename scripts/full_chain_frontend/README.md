# 完整链路图形前端

这是完整链路 runner 的独立 Tkinter 前端。当前支持在界面中选择 v0.2.1 当前版、v0.2.2 优化版、v0.2.3 诊断评价版或 v0.2.4 现实任务敏感版，并可临时输入 API Key，不必修改根目录 `.env`。推荐从项目根目录双击启动：

```text
launch_full_chain_demo.pyw
```

如果 Windows 没有关联 `.pyw`，可双击备用入口：

```text
launch_full_chain_demo.cmd
```

仍然可以用命令行启动：

```powershell
python -B scripts\full_chain_frontend\app.py
```

## 边界

前端只以 subprocess 调用所选 runner：

```text
scripts/run_full_chain_v021.py
scripts/full_chain_v022/run_full_chain_v022.py
scripts/full_chain_v023/run_full_chain_v023.py
scripts/full_chain_v024/run_full_chain_v024.py
scripts/direct_api_baseline/run_direct_api_baseline.py
```

它不会 import 或修改 `scripts/first/`、`scripts/first_v021_boundary_copy/`、`scripts/third/`、`scripts/forth/` 的核心代码。

## 输入方式

- `新对话`：输入一条用户消息，从第 1 轮开始运行。
- `继续对话`：选择上一轮输出的 `conversation_record_v021_chain.json`，再输入下一轮用户消息。
- `仅重跑 record`：跳过 first 阶段，只对已有 record 的当前轮重跑后续阶段。

## 输出结构

输出按“每场对话一个文件夹”组织：

```text
reports/full_chain_v021/conversations/<conversation_id>/
├── conversation_record_latest.json
├── latest_run_summary.json
└── <run_id>/
    ├── 01_first_state_report.json
    ├── 02_strategy_report.json
    ├── 03_behavior_report.json
    ├── 04_evaluation_cases.json
    ├── 05_evaluation_report.json
    ├── 06_all_turn_evaluation_cases.json
    ├── 07_all_turn_evaluation_report.json
    ├── 08_conversation_summary_report.json
    ├── 09_dialogue_review_report.json
    ├── conversation_record_v021_chain.json
    └── full_chain_summary.json
```

其中：

- `05_evaluation_report.json`：最新一轮卡片评估。
- `07_all_turn_evaluation_report.json`：所有已完成轮次的卡片评估。
- `09_dialogue_review_report.json`：全对话复盘，不额外调用 API。

## 链路版本

- `v0.2.1 当前版`：调用原完整链路 runner，保留现有规则和报告结构。
- `v0.2.2 优化版`：调用 `scripts/full_chain_v022/` 下的副本 runner 和四阶段副本代码，减少本地规则对 API 回复的机械覆盖。
- `v0.2.3 诊断评价版`：调用 `scripts/full_chain_v023/`，第四部分默认使用一次 API 的 v0.2.2 细化诊断评价卡。
- `v0.2.4 现实任务敏感版`：调用 `scripts/full_chain_v024/`，在状态卡和策略请求之间显式保留现实后果、紧急度和可行动性，避免“错过考试/DDL”等场景被压成纯情绪安抚。
- `Direct API Baseline（Minimal Support，一次 API）`：调用 `scripts/direct_api_baseline/`，只给一个很薄的情绪支持助手角色提示，不进入 PURE-JADE 理论链路。
- `Direct API Baseline（Raw，一次 API）`：调用同一个 baseline runner，不加系统提示，只把对话历史和当前用户输入发给 API。

## 评价模式

v0.2.3 和 v0.2.4 支持前端传入“评价模式”：

- `Fast（一次 API 诊断评价）`：默认模式，每个评价 case 只调用一次 judge API，输出 `schema_version = 0.2.2` 的诊断评价卡。
- `Full（旧版逐维评价）`：保留旧 8 维逐项 LLM-as-Judge，用于少量离线 case 或最终报告，不建议在线调试时默认开启。

## API 设置

界面中的 `API Key`、`API URL`、`模型` 会作为子进程环境变量传给 runner，不会写回 `.env`，也不会出现在 runner 命令行日志里。留空时继续使用根目录 `.env` 或系统环境变量。

## 默认模式

为了避免误点消耗 API 余额，界面默认使用：

```text
strategy=rules
behavior=dry-run
skip evaluation=true
```

需要完整 API 链路时，把策略模式和行为模式切换为 `API（真实调用）`，并取消勾选“跳过评估”。
