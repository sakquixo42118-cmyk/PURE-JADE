# 璞玉计划 ×《人工智能创新导论》项目交接摘要

> 用途：将当前工作的上下文交接给云端 Codex。请云端 Codex 先完整阅读本文，再检查仓库中的现有文件，并在此基础上继续协助设计和实现。
>
> 更新时间：2026-06-19

## 1. 项目背景

团队同时面对两个任务：

1. 本学期末《人工智能创新导论》通识课答辩。
2. 下学期开学向璞玉计划导师进行成果汇报。

课程老师允许报名璞玉计划的学生直接使用璞玉计划成果作为课程答辩内容，因此团队决定把两个任务合并为一个项目。

团队共 7 人，按照导师的 4 个研究内容进行了 `2-2-2-1` 分组。用户本人属于“研究内容二”，主要负责心智/支持意图推断、需求映射和共情策略决策。

原始 ChatGPT 分享记录：

<https://chatgpt.com/share/6a34a331-4eb4-83ea-ab28-fc344ed1630d>

注意：分享记录中没有 7 位成员的姓名和个人负责人信息；后续需要团队补充。

## 2. 已经确定的项目方向

暂定项目名称：

**面向情绪支持场景的共情策略生成原型系统**

团队已经确认采用模块化 LLM 原型方案，不在第一阶段训练模型，也不进行完整论文复现。每个模块采用：

```text
输入 → 调用大模型 API → 输出结构化卡片
```

总体流程暂定为：

```text
用户输入/历史对话
→ 风险优先检测
→ 用户状态卡
→ 共情策略决策卡
→ 行为回应卡
→ 场景应用与评价卡
```

项目价值不应表述为“调用了大模型 API”，而应表述为：

> 将情绪支持过程拆解为可解释、可控制、可评估的状态感知、意图推断、策略决策和行为生成流程，并使用 ESConv 的策略体系、对话案例与测试数据增强系统。

## 3. 当前团队模块分工

这是团队采用的总体分工逻辑，具体成员姓名尚未补充：

| 研究方向 | 人数 | 模块 | 主要工作 | 预期交付物 |
|---|---:|---|---|---|
| 研究内容一 | 2 | 用户状态感知 | 识别事件、情绪、强度、需求、证据和风险 | 用户状态卡、状态分析 Prompt |
| 研究内容二 | 2 | 共情策略决策 | 支持意图推断、需求映射、策略选择、回应时机/强度/方式 | 策略决策卡、映射表、决策 Prompt |
| 研究内容三 | 2 | 行为回应生成 | 根据策略生成文本、语气以及可选的表情/动作 | 行为回应卡、生成 Prompt |
| 研究内容四 | 1 | 场景应用与评估 | 案例库、人工评分、对比实验、Demo 故事线 | 评价卡、实验结果、展示案例 |

用户本人当前最需要推进的是研究内容二。

## 4. 当前进度

已经完成：

- 全组确认采用“输入 + API + 输出卡片”的模块化模式。
- 确认希望将 ESConv 数据集融入项目。
- 初步确认第一阶段以可运行 Demo 为目标，不训练模型。

尚未开始或尚未确定：

- 各张卡片的最终字段和 JSON Schema。
- 用户需求到共情策略的映射表。
- 每个模块的 Prompt。
- ESConv 的具体数据处理、检索和评估方式。
- 统一的代码接口、模型/API 供应商和前端方案。
- 成员姓名、模块负责人和截止时间。
- 安全规则和高风险表达的具体处理方式。

## 5. 卡片设计建议（v0.1 草案）

重要原则：卡片既是答辩界面中展示的内容，也是模块之间的机器可读接口。应先冻结 Schema，再开始分别编写代码。

### 5.1 用户状态卡

```json
{
  "problem_summary": "学习努力后没有得到预期结果",
  "emotion": ["疲惫", "沮丧", "自我怀疑"],
  "emotion_intensity": 2,
  "need": ["被理解", "被肯定"],
  "support_stage": "exploration",
  "risk_level": "low",
  "evidence": ["感觉怎么努力都没有用"],
  "confidence": 0.84
}
```

建议约束：

- `emotion_intensity` 固定为 `0-3`。
- `support_stage` 固定为 `exploration / comforting / action`。
- `risk_level` 固定为 `low / medium / high`。
- `evidence` 必须引用用户原话，减少无依据推断。
- 不进行抑郁症等医学诊断。

### 5.2 共情策略决策卡

```json
{
  "support_intention": "comfort",
  "primary_strategy": "Reflection of feelings",
  "secondary_strategy": "Affirmation and Reassurance",
  "response_timing": "respond_now",
  "response_intensity": "gentle",
  "response_goal": "让用户感到情绪被理解和接住",
  "reason": "用户情绪较强，目前没有主动要求解决方案",
  "esconv_example_ids": ["train_0187", "train_0921"],
  "constraints": [
    "暂不直接给建议",
    "最多提出一个问题",
    "不得进行心理诊断"
  ]
}
```

策略卡需要实现：

- 输入：原始对话、用户状态卡、可选的 ESConv 相似案例。
- 输出：支持意图、主/辅策略、回应时机、强度、目标、依据和生成约束。
- 所有类别采用固定枚举，禁止模型自行创造标签。

### 5.3 行为回应卡

```json
{
  "text_response": "听起来你已经努力了很久，却一直没有看到期待的结果，这种无力感确实很磨人。最近是哪件事让这种感觉特别明显？",
  "tone": "温和、克制、非说教",
  "strategy_realization": [
    {
      "strategy": "Reflection of feelings",
      "text_span": "这种无力感确实很磨人"
    },
    {
      "strategy": "Question",
      "text_span": "最近是哪件事让这种感觉特别明显？"
    }
  ],
  "facial_expression": null,
  "action": null,
  "safety_message_used": false
}
```

`strategy_realization` 用来证明最终回复确实落实了策略卡，而不是一次与前面无关的自由生成。

如果最终 Demo 只做文本聊天，表情和动作字段可以暂时设为可选，不要为了字段齐全而虚构多模态能力。

### 5.4 评价卡

```json
{
  "emotion_alignment": 4,
  "strategy_consistency": 5,
  "relevance": 4,
  "naturalness": 4,
  "safety": 5,
  "violations": [],
  "review_needed": false
}
```

评分可由评审 LLM 初评，但必须加入人工评分或人工复核，避免仅使用“模型评价模型”。

## 6. ESConv 的正确融入方式

ESConv 不宜被强行塞进每一个模块。推荐在三个层级中使用。

### 6.1 策略标签体系

策略决策卡采用 ESConv 的 8 类支持策略作为固定策略空间：

1. `Question`
2. `Restatement or Paraphrasing`
3. `Reflection of feelings`
4. `Self-disclosure`
5. `Affirmation and Reassurance`
6. `Providing Suggestions`
7. `Information`
8. `Others`

`Others` 只作为兜底，不应成为常用结果。

必须准确表述：ESConv 主要提供情绪支持对话和支持策略标注，并不直接提供本项目所需的全部“需求、风险、回应时机和回应强度”字段。这些字段属于团队基于导师研究框架自行设计的状态与决策模型。

### 6.2 相似案例检索（推荐的核心融合方式）

将 ESConv 中支持者的每个回复及其上下文处理为类似结构：

```json
{
  "example_id": "train_0187",
  "context": "当前支持者回复之前的若干轮对话",
  "strategy": "Reflection of feelings",
  "supporter_response": "数据集中的支持者回复"
}
```

运行时建议：

1. 使用当前对话检索 2-3 个相似 ESConv 案例。
2. 可按照候选策略过滤或重排案例。
3. 将案例作为 few-shot 示例提供给策略决策或行为生成模块。
4. 在策略卡输出 `esconv_example_ids`，便于答辩展示数据集的实际参与路径。
5. 提示模型学习策略与表达模式，不得直接复制原始回复。

第一版不需要立即建设复杂向量数据库。可以先人工筛选每类策略 5-10 个典型案例，作为固定示例；流程跑通后再加入 Embedding 与向量检索。

ESConv 以英文为主。如果 Demo 主要处理中文，可选择以下一种方案：

- 人工筛选并翻译约 80-150 条典型案例，再由组员校对。
- 使用多语言 Embedding 检索英文原例，要求模型输出中文。
- 第一阶段只做小规模双语案例库，后续再扩大。

### 6.3 数据集评估

至少进行三组对比：

1. `Baseline`：用户输入直接生成回复。
2. `Pipeline`：状态卡 + 策略卡 + 行为卡，不检索 ESConv。
3. `Pipeline + ESConv`：完整卡片流程并检索 ESConv 示例。

建议评价指标：

- 情绪匹配/共情程度。
- 策略选择合理性。
- 策略与最终回复的一致性。
- 回复相关性与自然度。
- 安全性与是否说教。

注意：给定相同上下文时可能存在多个合理策略，因此不能只用严格的单标签准确率。可以同时报告 Top-2 命中率、混淆矩阵和人工合理性评分。

训练集用于建立案例库或检索，开发集用于调试，测试集应尽量只用于最终评估，避免数据泄漏。

## 7. 策略映射表 v0.1

| 用户状态/需求 | 支持阶段 | 主策略 | 可选辅助策略 | 约束 |
|---|---|---|---|---|
| 信息不足、表达模糊 | Exploration | Question | Restatement or Paraphrasing | 一次最多问一个核心问题 |
| 希望被理解、情绪较强 | Exploration/Comforting | Reflection of feelings | Affirmation and Reassurance | 先共情，不急于建议 |
| 自我否定、需要肯定 | Comforting | Affirmation and Reassurance | Reflection of feelings | 不做空泛夸奖 |
| 需要一定的陪伴或正常化 | Comforting | Self-disclosure | Affirmation and Reassurance | 自我披露必须简短且服务于用户 |
| 主动询问解决办法 | Action | Providing Suggestions | Question | 给低门槛、可选择的建议 |
| 询问事实、知识或资源 | Action | Information | Providing Suggestions | 不编造资源和专业结论 |
| 无法归入已有策略 | 任意 | Others | 无 | 记录原因，后续人工检查 |
| 出现高风险表达 | Safety override | 不走普通 ESConv 决策 | 安全引导 | 进入独立安全流程 |

高风险处理应是独立且优先级最高的安全分支，不能硬套进 ESConv 八类策略。项目必须声明自己是情绪支持研究原型，不是医疗或心理诊断工具。

## 8. 工程实现建议

- 所有模块共享 `conversation_id`、`turn_id` 和 `schema_version`。
- 下一模块必须同时接收原始用户输入和上一模块卡片，避免信息在级联中丢失。
- 为每张卡定义 JSON Schema，并对 API 输出做校验、重试和默认值处理。
- 风险检测最好独立于普通情绪识别，并拥有最高路由优先级。
- 准备真实 API 模式和预设案例回放模式，避免答辩现场因网络、额度或 JSON 解析失败而中断。
- 保留每一轮的模型、Prompt 版本、检索案例 ID 和输出，便于复现实验。
- Prompt、策略标签和 Schema 应集中管理，不要散落在各模块代码中。

## 9. 建议的近期工作顺序

1. 全组冻结统一字段、枚举值和模块输入输出格式，形成 `Schema v0.1`。
2. 研究内容二两位成员完成策略卡、支持意图分类和映射表 v0.1。
3. 从 ESConv 中为每个策略人工挑选 5-10 个典型案例。
4. 使用学习挫败、亲子沟通、孤独陪伴三个自建案例串通所有卡片。
5. 为每个模块编写 Prompt，并验证能稳定输出合法 JSON。
6. 实现完整 API 流程和简单界面。
7. 加入 ESConv 相似案例检索。
8. 完成三组对比实验与人工评分。
9. 最后制作答辩 PPT、流程图和备用回放演示。

## 10. 云端 Codex 接手后的优先任务

云端 Codex 不应立即大规模写代码。建议先：

1. 检查仓库中是否已经存在需求、PPT、数据集或代码。
2. 根据本文生成一份正式的模块接口文档与 JSON Schema。
3. 优先设计研究内容二的策略决策 Prompt 和映射表。
4. 检查 ESConv 官方数据文件的实际字段，编写最小数据预处理方案。
5. 给出可运行的最小项目骨架，再逐模块实现。

实现过程中如发现本文建议与导师 PPT 原文冲突，应以导师要求和团队最新决定为准，并在修改前说明差异。

## 11. 主要参考资料

- ESConv 论文：<https://aclanthology.org/2021.acl-long.269/>
- ESConv 官方仓库：<https://github.com/thu-coai/Emotional-Support-Conversation>
- IntentionESC：<https://aclanthology.org/2025.findings-acl.1358/>
- MultiESC：<https://aclanthology.org/2022.emnlp-main.195/>
- TransESC：<https://aclanthology.org/2023.findings-acl.420/>
- Streamlit 文档：<https://docs.streamlit.io/>

## 12. 一句话交接结论

当前项目已经完成方向确认，但还处于协议设计阶段；下一步最重要的不是写界面，而是先冻结四张卡的 Schema、策略映射表以及 ESConv 的检索与评估路径，然后再实现 API 流程。
