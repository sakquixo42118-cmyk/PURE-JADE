# PURE-JADE 组员零背景接手说明

更新时间：2026-07-01

这份文档是给“之前没有参与系统调试、但需要接手论文/视频/提交整理”的组员看的。请先读这份，再按分工去看同目录下的论文写作包、视频脚本和运行指南。

## 先给结论

PURE-JADE 的系统实现部分已经可以用于期末大作业提交。后续不要把主要时间继续花在调模型回复质量上，应该进入收尾阶段：

```text
论文/报告 + 演示视频 + 测试结果整理 + 提交包检查
```

课程要求的提交截止日期是 2026-07-10。当前最重要的是把已经完成的系统和实验讲清楚，而不是继续改代码。

## 项目一句话

```text
PURE-JADE 是一个面向大学生情绪支持场景的模块化 LLM 原型系统。
它把大模型的情绪支持过程拆成用户状态识别、共情策略决策、行为回应生成和评价对比四个环节，
并通过 Direct API Baseline 观察模块化链路相对于原生大模型回复的优势和代价。
```

## 这个项目不是普通聊天机器人

普通聊天机器人通常是：

```text
用户输入 -> 直接发给大模型 -> 得到回复
```

PURE-JADE 的设计是：

```text
用户输入 / 历史对话
-> 第一部分：用户状态卡
-> 第二部分：共情策略卡
-> 第三部分：行为回应卡
-> 第四部分：评价卡 / A-B 对比
```

也就是说，我们不是只追求“生成一句安慰”，而是让模型的回应过程可以被拆解、记录、解释和评价。

## 为什么这个选题符合课程要求

课程要求强调：

- 使用公开 LLM；
- 有明确应用场景；
- 有系统流程；
- 有界面；
- 有测试与效果分析；
- 有论文和演示视频。

PURE-JADE 对应关系：

| 课程要求 | PURE-JADE 对应内容 |
|---|---|
| 公开 LLM | 使用 DeepSeek / OpenAI-compatible Chat Completions API |
| 明确应用场景 | 大学生情绪支持、学业压力、小组协作压力、低风险心理支持 |
| 系统流程 | 状态卡 -> 策略卡 -> 行为卡 -> 评价卡 |
| 界面 | Tkinter 桌面前端 |
| 测试材料 | `reports/` 中有多轮对话记录和 A/B comparison |
| 效果分析 | Direct API Baseline vs PURE-JADE v0.26 |
| 可解释性 | 每一轮都有状态、策略、行为和评价 JSON 报告 |

## 当前推荐演示版本

前端里推荐选择：

```text
v0.2.6 证据内展开版
```

原因：

- v0.24 更偏安全和现实任务，但回复偏短。
- v0.25 尝试增加情绪深度和微行动，但仍有模板化问题。
- v0.26 加入 evidence-grounded expansion，即“证据内展开”：允许模型基于用户原话展开情绪张力，但不允许编造新事实。

论文中可以写：

```text
最终演示版本采用 v0.2.6。该版本在 v0.25 的基础上进一步缓解过度压缩和模板化问题，强调基于用户已提供信息进行证据内展开。
```

## 当前最重要的测试结果

推荐引用这组短对话 A/B 对比：

```text
reports/ab_comparison/ab_short6_v026_vs_direct_20260701_2130/
```

结果：

| 指标 | Direct API | PURE-JADE v0.26 |
|---|---:|---:|
| Judge 胜场 | 3 | 3 |
| Score 胜场 | 3 | 3 |
| Overall 均分 | 4.500 | 4.333 |
| Safety 均分 | 5.000 | 5.000 |
| Naturalness 均分 | 4.500 | 4.667 |
| Contextual Continuity 均分 | 4.500 | 4.667 |
| Over-inference Control 均分 | 4.833 | 5.000 |
| Conciseness Balance 均分 | 4.167 | 4.833 |

解释方式：

```text
PURE-JADE v0.26 并没有在总体均分上完全超过 Direct API，但它在安全性、上下文连续性、避免过度推测和篇幅控制上表现更稳。
Direct API 在共情深度、相关性和即时行动帮助上仍有优势。
这说明模块化系统的价值不只是最终回复分数，而是可解释、可审计、可分析和可迭代。
```

## 组员分工建议

请按下面分工直接领任务，不要再重新讨论系统要不要改。

| 任务 | 负责人 | 产出 |
|---|---|---|
| 论文背景与问题分析 | 待填写 | 背景、场景、痛点、研究意义 |
| 技术路线与系统架构 | 待填写 | 模块图、流程图、版本说明 |
| 实验测试与效果分析 | 待填写 | A/B 对比表、结果解释、局限 |
| 视频录制与剪辑 | 待填写 | 5-8 分钟演示视频 |
| 最终排版与提交包 | 待填写 | 报告 PDF/Docx、视频、代码包 |

成员姓名和贡献请小组自行填写，不要虚构。

## 组员应该先看哪些文件

建议阅读顺序：

1. `README_FOR_GROUPMATES.md`：先理解项目全貌。
2. `PAPER_WRITING_PACKAGE.md`：写论文的人看。
3. `VIDEO_STORYBOARD_AND_SCRIPT.md`：录视频的人看。
4. `RUN_AND_DEMO_GUIDE.md`：需要跑系统/截图的人看。
5. `SUBMISSION_CHECKLIST.md`：最终打包的人看。

## 关键路径速查

前端入口：

```text
scripts/full_chain_frontend/app.py
```

最终推荐链路：

```text
scripts/full_chain_v026/
```

Direct API baseline：

```text
scripts/direct_api_baseline/
```

A/B 对比工具：

```text
scripts/ab_comparison/
```

推荐测试报告：

```text
reports/ab_comparison/ab_short6_v026_vs_direct_20260701_2130/
```

示例数据：

```text
examples/
```

## 重要注意事项

不要提交：

- `.env`
- API Key
- `__pycache__/`
- `.pyc`
- 没有筛选的大量历史 reports

可以提交：

- `scripts/`
- `docs/`
- `examples/`
- 精选 `reports/`
- 论文/报告
- 演示视频

## 如果时间很紧

最低限度完成下面四件事：

1. 用 `PAPER_WRITING_PACKAGE.md` 写出报告。
2. 用 `VIDEO_STORYBOARD_AND_SCRIPT.md` 录 5-8 分钟视频。
3. 把 `ab_short6_v026_vs_direct_20260701_2130` 的结果截图/整理进报告。
4. 打包前确认没有 `.env` 和 API Key。

到这一步，期末大作业的核心要求就能覆盖住。
