# Direct API Baseline

这个目录提供 PURE-JADE 的原生大模型对照组：

```text
对话历史 / 当前用户输入
→ 直接发送给同一个 OpenAI-compatible API
→ 得到助手回复
```

它不会生成状态卡、策略卡、行为卡，也不会注入 PURE-JADE 理论链路。默认会强制关闭 JSON mode，避免模型被结构化输出限制住。

## 运行方式

```bash
python scripts/direct_api_baseline/run_direct_api_baseline.py ^
  --message "我刚刚错过期末考试了，我感觉我要炸了" ^
  --baseline-mode minimal-support ^
  --skip-evaluation
```

常用模式：

- `minimal-support`：只给一个很薄的情绪支持助手角色提示，适合作为主要对照组。
- `raw`：不加系统提示，只把对话历史和用户输入发给 API，适合观察模型最原始的回复倾向。

输出目录默认为：

```text
reports/direct_api_baseline/conversations/<conversation_id>/<run_id>/
```

关键输出文件：

- `01_direct_request_report.json`
- `03_behavior_report.json`
- `conversation_record_direct_baseline.json`
- `full_chain_summary.json`

## 前端入口

在 `scripts/full_chain_frontend/app.py` 的“链路版本”下拉框中选择：

- `Direct API Baseline（Minimal Support，一次 API）`
- `Direct API Baseline（Raw，一次 API）`

即可用同一个前端输入和 API Key 设置运行 baseline。
