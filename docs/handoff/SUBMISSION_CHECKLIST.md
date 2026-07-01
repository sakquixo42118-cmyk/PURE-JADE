# PURE-JADE 最终提交检查表

这份文档给负责最终打包和提交的组员使用。

## 课程提交要求对照

| 要求 | 当前准备情况 | 是否完成 |
|---|---|---|
| 项目系统/代码 | `scripts/`, `docs/`, `examples/` | □ |
| 演示视频 | 需要组员录制 5-8 分钟 | □ |
| 配套论文/报告 | 需要组员根据写作包完成 | □ |
| 测试材料 | `reports/ab_comparison/ab_short6_v026_vs_direct_20260701_2130/` | □ |
| 成员分工说明 | 需小组填写真实贡献 | □ |
| AI 工具使用声明 | 可使用文档中模板 | □ |

## 推荐提交包结构

建议最终压缩包结构：

```text
课程名_期末大作业_组号_项目名称.zip
├─ code/
│  ├─ scripts/
│  ├─ docs/
│  └─ examples/
├─ reports_selected/
│  └─ ab_short6_v026_vs_direct_20260701_2130/
├─ paper/
│  └─ 项目报告.docx 或 项目报告.pdf
├─ video/
│  └─ 演示视频.mp4
└─ README_运行说明.md
```

如果不想重新整理目录，也可以直接提交项目压缩包，但必须删除敏感文件。

## 必须删除或排除

不要提交：

- `.env`
- 任何 API Key
- `__pycache__/`
- `.pyc`
- 临时测试文件
- 无关历史报告
- 微信原始文件路径下的私人文件

建议运行检查：

```powershell
Get-ChildItem -Recurse -Force -Include .env,*.pyc | Select-Object FullName
Get-ChildItem -Recurse -Directory -Force -Filter __pycache__ | Select-Object FullName
```

如果要删除缓存：

```powershell
Get-ChildItem -Recurse -Directory -Force -Filter __pycache__ | Remove-Item -Recurse -Force
Get-ChildItem -Recurse -Force -Filter *.pyc | Remove-Item -Force
```

删除前确认路径在项目目录内。

## README 运行说明模板

可以在提交包里放一个简单 README：

```text
# PURE-JADE 运行说明

1. 进入项目根目录。
2. 安装/准备 Python 环境。
3. 运行前端：

python scripts/full_chain_frontend/app.py

4. 在前端选择 v0.2.6 证据内展开版。
5. 输入 API Key、API URL 和模型名称。
6. 输入用户消息并运行完整链路。

注意：本提交包不包含 API Key。如需真实运行，请使用自己的 API Key。
```

## 论文检查表

论文提交前检查：

- □ 字数满足课程要求；
- □ 有题目、摘要、关键词；
- □ 有项目背景；
- □ 有模型选择和技术路线；
- □ 有系统架构图；
- □ 有前端截图；
- □ 有状态卡/策略卡/行为卡说明；
- □ 有 Direct API baseline 对比；
- □ 有 A/B comparison 结果表；
- □ 有失败案例和局限；
- □ 有成员分工；
- □ 有 AI 工具使用声明；
- □ 有参考资料。

## 视频检查表

视频提交前检查：

- □ 时长约 5-10 分钟；
- □ 说明了项目背景；
- □ 展示了前端界面；
- □ 展示了至少一次输入和输出；
- □ 说明了调用哪个公开 LLM；
- □ 展示了 Direct API vs PURE-JADE 对比；
- □ 说明了成员分工；
- □ 没有露出 API Key；
- □ 画面和声音清晰。

## 测试材料检查表

建议论文和提交包至少包含：

- □ `comparison_summary.json`
- □ `comparison_report.md`
- □ `paired_turns.json`
- □ Direct API conversation record
- □ PURE-JADE v0.26 conversation record

推荐路径：

```text
reports/ab_comparison/ab_short6_v026_vs_direct_20260701_2130/
```

## 成员分工模板

请改成真实姓名和真实贡献：

| 成员 | 贡献 |
|---|---|
| 成员 1 | 需求分析、系统设计、技术路线整理 |
| 成员 2 | 前端演示、运行截图、视频录制 |
| 成员 3 | 测试样例整理、A/B 结果分析 |
| 成员 4 | 论文撰写、排版、提交包整理 |

不要填写没有实际完成的贡献。

## AI 工具使用声明模板

```text
本项目在开发和文档整理过程中使用了大语言模型工具辅助，包括代码实现、Prompt 优化、调试、测试用例设计、实验结果分析和论文初稿整理。系统运行阶段调用公开 LLM API 生成用户状态卡、共情策略卡、行为回应卡和评价报告。所有项目结果均由小组成员人工检查，报告中如实说明了系统优势、局限和失败案例。
```

## 最终提交前一句话检查

提交前请确认：

```text
系统能演示，论文能说明，视频能看懂，报告有测试，压缩包没有 API Key。
```
