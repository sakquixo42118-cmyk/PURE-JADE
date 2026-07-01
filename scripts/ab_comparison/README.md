# PURE-JADE A/B Comparison

这个目录用于比较：

```text
Direct API baseline（一调用）
vs
PURE-JADE v0.24 三段链路（三调用）
```

第一版只读取已有 `conversation_record_latest.json`，不会重新生成回复。

## 前端启动

项目根目录双击：

```text
launch_ab_comparison.pyw
```

如果 `.pyw` 没有关联 Python，可以双击：

```text
launch_ab_comparison.cmd
```

界面中选择：

- Direct record：`reports/direct_api_baseline/.../conversation_record_latest.json`
- PURE-JADE record：`reports/full_chain_v024/.../conversation_record_latest.json`
- Judge 模式：
  - `API 盲评`：调用 judge API，生成量化对比。
  - `只生成配对`：不调用 API，只检查两份 record 是否按轮次对齐。

## 命令行

```powershell
python scripts\ab_comparison\run_ab_comparison.py `
  --direct-record reports\direct_api_baseline\conversations\...\conversation_record_latest.json `
  --chain-record reports\full_chain_v024\conversations\...\conversation_record_latest.json `
  --judge-mode api
```

不想调用 API 时：

```powershell
python scripts\ab_comparison\run_ab_comparison.py `
  --direct-record ... `
  --chain-record ... `
  --judge-mode pair-only
```

## 输出文件

默认输出到：

```text
reports/ab_comparison/<comparison_id>/
```

关键文件：

- `paired_turns.json`：按轮次配好的 A/B 输入，包含盲评映射。
- `ab_judge_report.json`：每轮 judge 结果。
- `comparison_summary.json`：平均分、胜负统计、维度优势。
- `comparison_table.csv`：便于放进表格或答辩材料。
- `comparison_report.md`：简短 Markdown 版报告。

## 评价维度

共同维度，不用 PURE-JADE 策略卡惩罚 Direct API：

- 情绪承接与共情
- 上下文贴合度
- 具体帮助与下一步
- 自然度
- 安全与不编造
- 多轮连续性
- 避免过度推测
- 篇幅与信息密度平衡
- 总体质量
