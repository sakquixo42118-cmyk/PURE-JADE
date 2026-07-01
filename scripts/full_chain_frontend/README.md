# 完整链路图形前端

这是 v0.2.1 完整链路 runner 的独立 Tkinter 前端。推荐从项目根目录双击启动：

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

前端只以 subprocess 调用：

```text
scripts/run_full_chain_v021.py
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

## 默认模式

为了避免误点消耗 API 余额，界面默认使用：

```text
strategy=rules
behavior=dry-run
skip evaluation=true
```

需要完整 API 链路时，把策略模式和行为模式切换为 `API（真实调用）`，并取消勾选“跳过评估”。
