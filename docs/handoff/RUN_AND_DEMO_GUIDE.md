# PURE-JADE 运行、截图与测试引用指南

这份文档给负责录视频、截图、整理测试结果的组员使用。

## 运行前检查

请确认项目根目录是：

```text
D:\garage\Pure jade Project
```

建议使用 PowerShell，在项目根目录运行命令。

不要把 `.env` 或 API Key 发到群里，也不要录进视频。

## 启动前端

命令：

```powershell
python scripts\full_chain_frontend\app.py
```

如果系统 Python 环境异常，可以尝试：

```powershell
py scripts\full_chain_frontend\app.py
```

前端推荐选择：

```text
链路版本：v0.2.6 证据内展开版
策略模式：API（真实调用）
行为模式：API（真实调用）
评价模式：Fast（一次 API 诊断评价）
评价范围：只评估最新一轮
```

如果只是演示对话，不想等评价，可以勾选：

```text
跳过评价
```

## API 设置

前端左侧可以输入：

- API Key
- API URL
- 模型名称

API URL 示例：

```text
https://api.deepseek.com/chat/completions
```

模型示例：

```text
deepseek-v4-pro
```

如果报错：

```text
HTTP 401 / invalid api key
```

说明 API Key 错了，和系统代码无关。

如果报错：

```text
The read operation timed out
```

说明 API 请求超时，不一定是代码错。可以重跑，或在命令行加：

```powershell
--api-timeout 180 --api-max-retries 1
```

## 推荐演示输入

短输入 1：

```text
我这周一直在改小组展示，但老师说逻辑还是散，我有点崩。
```

短输入 2：

```text
我明知道比较没用，但还是忍不住一直刷他们的进度，越看越慌。
```

短输入 3：

```text
我现在只想先稳住情绪，但又怕明天还是交不出东西。
```

不建议现场演示很长对话，因为多阶段 API 会慢，视频里可以展示已经生成的 reports。

## 前端需要截图的位置

建议截图：

1. 前端整体界面：能看到输入区、链路版本、API 设置。
2. 对话日志 tab：展示用户输入和助手回复。
3. 状态卡 tab：展示情绪、需求、风险等字段。
4. 策略卡 tab：展示 support_intention、primary_strategy、constraints。
5. 行为卡 tab：展示 text_response 和 strategy_realization。
6. 汇总 JSON tab：展示输出文件路径。
7. A/B comparison 报告：展示 Direct API vs PURE-JADE 的结果。

## 命令行运行 v0.26

单轮新对话：

```powershell
python -B scripts\full_chain_v026\run_full_chain_v026.py `
  --message "我这周一直在改小组展示，但老师说逻辑还是散，我有点崩。" `
  --conversation-id demo_video_v026 `
  --run-id demo_turn1 `
  --strategy-mode api `
  --behavior-mode api `
  --eval-mode fast `
  --api-timeout 180 `
  --api-max-retries 1
```

如果只想快一点、不做评价：

```powershell
python -B scripts\full_chain_v026\run_full_chain_v026.py `
  --message "我这周一直在改小组展示，但老师说逻辑还是散，我有点崩。" `
  --conversation-id demo_video_v026 `
  --run-id demo_turn1 `
  --strategy-mode api `
  --behavior-mode api `
  --skip-evaluation `
  --api-timeout 180 `
  --api-max-retries 1
```

## 运行 Direct API Baseline

Direct Baseline 是一次 API 直接回复，不经过 PURE-JADE 四阶段理论链路。

```powershell
python -B scripts\direct_api_baseline\run_direct_api_baseline.py `
  --message "我这周一直在改小组展示，但老师说逻辑还是散，我有点崩。" `
  --conversation-id demo_direct `
  --run-id demo_direct_turn1 `
  --baseline-mode minimal-support `
  --api-timeout 180 `
  --api-max-retries 1
```

论文中可以解释：

```text
Direct API Baseline 用于回答：如果不使用 PURE-JADE 的状态卡、策略卡和行为卡，同一个模型会如何直接回应用户。
```

## 运行 A/B Comparison

已有推荐结果，不一定需要重跑。

推荐直接引用：

```text
reports/ab_comparison/ab_short6_v026_vs_direct_20260701_2130/
```

如果要重跑，需要准备：

- Direct record
- PURE-JADE record

命令示例：

```powershell
python -B scripts\ab_comparison\run_ab_comparison.py `
  --direct-record reports\direct_api_baseline\conversations\codex_short6_direct_20260701_2130\conversation_record_latest.json `
  --chain-record reports\full_chain_v026\conversations\codex_short6_v026_20260701_2130\conversation_record_latest.json `
  --comparison-id ab_short6_v026_vs_direct_rerun `
  --judge-mode api `
  --max-turns 6 `
  --api-timeout 180 `
  --api-max-retries 1
```

## 推荐引用的报告文件

用于论文/视频：

```text
reports/ab_comparison/ab_short6_v026_vs_direct_20260701_2130/comparison_summary.json
reports/ab_comparison/ab_short6_v026_vs_direct_20260701_2130/comparison_report.md
reports/ab_comparison/ab_short6_v026_vs_direct_20260701_2130/paired_turns.json
```

用于展示 Direct API 记录：

```text
reports/direct_api_baseline/conversations/codex_short6_direct_20260701_2130/conversation_record_latest.json
```

用于展示 PURE-JADE v0.26 记录：

```text
reports/full_chain_v026/conversations/codex_short6_v026_20260701_2130/conversation_record_latest.json
```

## 推荐结果表

可以直接放进论文：

| 指标 | Direct API | PURE-JADE v0.26 |
|---|---:|---:|
| Judge 胜场 | 3 | 3 |
| Score 胜场 | 3 | 3 |
| Overall 均分 | 4.500 | 4.333 |
| Empathy 均分 | 4.667 | 4.333 |
| Relevance 均分 | 4.667 | 4.500 |
| Actionability 均分 | 4.500 | 4.167 |
| Naturalness 均分 | 4.500 | 4.667 |
| Safety 均分 | 5.000 | 5.000 |
| Contextual Continuity 均分 | 4.500 | 4.667 |
| Over-inference Control 均分 | 4.833 | 5.000 |
| Conciseness Balance 均分 | 4.167 | 4.833 |

## 常见问题

### 1. 为什么 PURE-JADE 没有全面赢 Direct API？

这是正常结果。2026 年的大模型本身情绪支持能力已经很强，Direct API 在自然表达上有优势。PURE-JADE 的价值是过程可解释、可记录、可审计，而不是每一句都压过 Direct API。

### 2. 为什么系统这么慢？

因为 PURE-JADE 不是一次调用，而是多阶段调用：

```text
状态卡 -> 策略卡 -> 行为卡 -> 评价卡
```

如果再跑 A/B comparison，还会额外调用 judge API。

### 3. 长对话能不能测？

能测，但不推荐作为视频主展示。长对话更慢，也更容易超时。视频中建议演示单轮或短多轮，论文中引用已经跑好的 6 轮短对话。

### 4. 报告里要不要说系统有缺点？

要说。建议写：

```text
系统牺牲了速度，换来了更强的过程可解释性；Direct API 在自然共情方面仍有优势。
```

这比硬说 PURE-JADE 全面更好更可信。

## 最省心截图流程

1. 打开前端，截图主界面。
2. 输入一条推荐演示语句，运行 v0.26。
3. 截图对话日志。
4. 截图状态卡、策略卡、行为卡。
5. 打开 `comparison_report.md`，截图 A/B 结果。
6. 把截图放进论文和视频。
