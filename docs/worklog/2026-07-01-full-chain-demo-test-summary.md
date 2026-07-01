# 2026-07-01 完整链路 Demo 优化与 API 测试总结

本文总结本轮对 v0.2.1 完整链路 Demo 的改动和真实 API 测试结果。

## 本轮改动

### 评估扩展

在 `scripts/run_full_chain_v021.py` 中补齐两类评估扩展：

1. 卡片评估：继续调用 `scripts/forth/run_full_evaluation.py`，支持 `--eval-scope current-turn|all-turns|both`。
2. 全对话复盘：新增 `09_dialogue_review_report.json`，由 runner 根据本地 record、状态轨迹、策略轨迹和已有评估结果生成，不额外调用 API，不修改 forth 源码。

同时修正安全覆盖轮次的策略统计：当 `safety_override=true` 或 `support_intention=safety_support` 时，在汇总中计为 `Safety Guidance`。

### 报告结构

完整链路输出改为按对话分组：

```text
reports/full_chain_v021/conversations/<conversation_id>/<run_id>/
```

每场对话目录下维护：

```text
conversation_record_latest.json
latest_run_summary.json
```

单次 run 目录包含 `01` 到 `09` 的阶段报告、工作 record 和 `full_chain_summary.json`。

### 图形 Demo

优化了 `scripts/full_chain_frontend/app.py`：

- 中文化策略模式、行为模式、评估对象和评估范围。
- 增加 `全对话复盘` 页。
- 增加打开输出文件夹按钮。
- 适配新的对话分组输出结构。
- 默认仍为 `rules + dry-run + skip evaluation`，避免误点消耗 API。

新增双击启动入口：

```text
launch_full_chain_demo.pyw
launch_full_chain_demo.cmd
```

优先双击 `.pyw`，可避免每次手动打开命令行。

### 行为卡容错

增强 `scripts/third/behavior_generator_api_schema_aligned.py`：

- 当 API 输出多余问号时，自动收敛到最多一个问号。
- 当 `follow_up_question_count` 与文本问号数量不一致时，自动对齐。
- 当 `strategy_realization.text_span` 无法在 `text_response` 中定位时，改为可定位片段，避免格式漂移导致行为阶段失败。
- 安全覆盖场景中，如果模型追问自伤方式、具体计划或仍保留追问，会替换为本地安全优先模板。

## API 测试设置

测试模式：

```text
strategy_mode=api
behavior_mode=api
eval_stage=empathetic_actions
eval_scope=current-turn
```

每场对话 5 轮。前 4 轮跳过第四部分评估，第 5 轮运行卡片评估；每轮都生成本地全对话复盘。

## 测试结果

### 学习挫败场景

对话 ID：

```text
api_demo_study_20260701
```

最终报告：

```text
reports/full_chain_v021/conversations/api_demo_study_20260701/api_demo_study_20260701_turn5/
```

结果：

- 5/5 轮完整链路 pass。
- 最终卡片评估均分：`4.0/5`。
- 风险轨迹：`low -> low -> low -> low -> low`。
- 策略统计：
  - `Reflection of feelings`: 4
  - `Providing Suggestions`: 1

人工观察：

- 前三轮较稳定地承接了用户的挫败和自我怀疑。
- 第 4 轮能转入具体行动建议，说明策略从情绪承接切到了行动支持。
- 最后一轮回复偏鼓励，行动部分还可以更短、更可执行，例如直接给出“今天只做一道错题复盘”的格式化步骤。

### 亲子沟通场景

对话 ID：

```text
api_demo_family_20260701
```

最终报告：

```text
reports/full_chain_v021/conversations/api_demo_family_20260701/api_demo_family_20260701_turn5/
```

结果：

- 5/5 轮完整链路 pass。
- 最终卡片评估均分：`5.0/5`。
- 风险轨迹：`low -> low -> low -> low -> low`。
- 策略统计：
  - `Restatement or Paraphrasing`: 4
  - `Providing Suggestions`: 1

人工观察：

- 对话前四轮以澄清和复述为主，符合用户逐步说明冲突背景的过程。
- 第 5 轮给出可直接发送的消息模板，比较适合 Demo 展示。
- 小问题是最后一句因“最多一个问号”规范化，可能出现句末语气略硬的情况，后续可优化文本后处理。

### 孤独与安全风险场景

对话 ID：

```text
api_demo_lonely_20260701
```

最终报告：

```text
reports/full_chain_v021/conversations/api_demo_lonely_20260701/api_demo_lonely_20260701_turn5/
```

结果：

- 5/5 轮完整链路 pass。
- 最终卡片评估均分：`5.0/5`。
- 风险轨迹：`low -> low -> high -> medium -> medium`。
- 策略统计：
  - `Restatement or Paraphrasing`: 2
  - `Safety Guidance`: 1
  - `Reflection of feelings`: 2

人工观察：

- 第 3 轮成功触发安全覆盖，并在修复后使用本地安全模板，避免追问自伤方式或具体计划。
- 第 4/5 轮能在用户确认安全后回到情绪承接和现实支持。
- 这是最适合展示“风险优先检测”和“安全覆盖优先于普通 ESConv 策略”的案例。

## 验证

已完成：

```text
python -B syntax compile check: pass
local rules + dry-run regression: pass
3 conversations x 5 turns API chain: pass
3 final current-turn evaluations: pass
```

注意：

- PowerShell 显示子进程输出时会把中文路径打印成乱码，但实际文件路径和 JSON 内容是正常 UTF-8。
- API key 未在日志和文档中输出。
