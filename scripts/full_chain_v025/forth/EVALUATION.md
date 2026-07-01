# PURE-JADE 评估体系：原理与设计

> 本文档详细解释 8 维评估体系的理论来源、工作原理和设计依据。
> 操作手册请见 [README.md](README.md)。

---

## 一、理论来源：EmpathyAgent 论文 (arXiv:2503.16545v1)

这篇论文是北京大学 2025 年 3 月发表的，研究**具身智能体共情行为评估**——让机器人在虚拟家庭环境（VirtualHome）中对人类做出共情动作（递水、开灯、安慰等）。

论文提出了两套评估指标：

| 类型 | 方法 | PURE-JADE 适用性 |
|------|------|------------------|
| 参考型 (Reference-Based) | 和标准答案比 BLEU、ROUGE、BERTScore 相似度 | ❌ 不适合 — 需要 ground-truth 动作序列 |
| **参考无关 (Reference-Free)** | 基于心理学量表，用 LLM 打分 1-10 | ✅ 适合 — 不需要标准答案，直接评分 |

本系统完整复现了 **参考无关（Reference-Free）** 评估框架，出自论文 Appendix A.4.2 节。

### 适配要点

论文评估的是"机器人在虚拟家庭中的物理动作"，PURE-JADE 评估的是"文本对话中的共情回复"。核心适配如下：

| 论文原文概念 | PURE-JADE 适配 |
|-------------|---------------|
| robot's response to character's action | 助手对用户表达内容的回应 |
| robot's understanding of character's dialogue | 助手对用户情绪的感知 |
| character's personality, profession, hobbies, social relationships, life experiences | 用户的个性特征、处境和背景 |
| getting a glass of water / turning on the radio（僵化动作模板） | 频繁使用固定安慰模板或套话 |
| legal action space（VirtualHome 合法动作集） | 对话安全约束和 prohibited_actions |

---

## 二、8 个维度的心理学依据

8 个维度并非随意设计，而是基于经人类标注验证的心理学量表。

### RoPE 量表 (Charrier et al., 2019)

RoPE（Robot's Perceived Empathy）衡量"人类感知到的机器人共情能力"，包含两个分量表：

**共情理解子量表 (Empathic Understanding)**

| 条目 | 内容 |
|------|------|
| EU1 | 机器人准确理解我所经历的感受 |
| EU2 | 机器人了解我和我的需求 |
| EU3 | 机器人关心我的感受 |
| EU4 | 机器人不理解我（反向计分） |
| EU5 | 机器人感知并接纳我的个体特征 |
| EU6 | 机器人通常理解我的全部意思 |
| EU7 | 机器人回应了我的话语但没有看到我的感受（反向计分） |
| EU8 | 当我悲伤或失望时，机器人似乎也会感到难过 |

**共情回应子量表 (Empathic Response)**

| 条目 | 内容 |
|------|------|
| ER1 | 无论我表达什么想法或感受，机器人的行为没有区别（反向计分） |
| ER2 | 无论我告诉它什么，机器人的行为都一样（反向计分） |
| ER3 | 当我沮丧时，机器人安慰我 |
| ER4 | 机器人鼓励我 |
| ER5 | 当我做得好时，机器人肯定我 |
| ER6 | 当我需要时，机器人帮助我 |
| ER8 | 机器人的回应如此固定和自动，我无法真正和它沟通（反向计分） |

### 8 维度与 RoPE 的对应关系

论文 Table 7 明确给出了每个评估维度对应的 RoPE 条目：

```
RoPE 条目               →  EmpathyAgent 维度           →  PURE-JADE 适配名称
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EU4 + EU6               →  Action/Dialogue Association  →  内容-情绪关联度
EU2 + EU5               →  Individual Understanding    →  个体化理解
EU1 + EU3 + EU7 + EU8   →  Emotional Communication     →  情绪沟通
ER3 + ER4 + ER5         →  Emotion Regulation          →  情绪调节
ER6                     →  Helpfulness                 →  帮助性
ER1 + ER2 + ER8         →  Adaptability                →  适应性
FI2 (filler item)       →  Coherence                   →  连贯性
（论文独创，无对应量表条目） →  Legality                    →  约束合规性
```

### 评分效度

论文报告了人类评分与 GPT-4-turbo 评分的 **ICC（组内相关系数）= 74.76%**（95% 置信区间）。ICC > 0.75 通常被认为是"良好到优秀"的一致性水平，这验证了 LLM-as-Judge 方案的可靠性。

---

## 三、评估引擎工作原理

整体架构是 **LLM-as-Judge** 模式——用 DeepSeek 作为评估者。

### 3.1 单次维度评估流程

```
输入数据（对话 + 用户状态卡 + 策略决策卡 + 行为回应卡）
        │
        ▼
┌──────────────────────────────────────────────┐
│  System Prompt = 该维度的评估标准 + 输出格式要求   │
│  User Prompt   = 对话内容 + 三张卡片的 JSON       │
│        │                                      │
│        ▼                                      │
│  POST https://api.deepseek.com/v1/chat/completions │
│  payload: { model, messages, temperature: 0,       │
│             response_format: { type: json_object }} │
│        │                                      │
│        ▼                                      │
│  解析 JSON → { reasoning: "...", score: N }     │
│        │                                      │
│        ▼                                      │
│  校验：score 是整数吗？在 0-10 内吗？              │
│  ├── 通过 → 返回 DimensionEvalResult            │
│  └── 失败 → 重试（追加修正指令，最多 max_retries 次）│
└──────────────────────────────────────────────┘
```

### 3.2 为什么每个维度独立调用 API

论文设计如此——每个维度有独立的评估标准和提示词。混在一起会让 LLM 混淆标准。独立调用确保每个维度的 `reasoning` 都聚焦于该维度，质量更高。

### 3.3 为什么 temperature = 0.0

评估需要**一致性和可复现性**。temperature=0 保证相同输入 → 相同输出，不会出现"同样一句回复，第一次跑 8 分第二次跑 6 分"的情况。

### 3.4 评估阶段 (Stage) 与维度分配

论文将共情过程分为三个阶段，不同维度适用于不同阶段：

| 阶段 | PURE-JADE 对应 | 适用维度 |
|------|---------------|---------|
| Scenario Understanding | 评估 user_state_card 质量 | 内容-情绪关联、连贯性、情绪沟通、个体化理解 |
| Empathetic Planning | 评估 strategy_decision_card 质量 | + 情绪调节、帮助性、适应性 |
| Empathetic Actions | 评估 behavior_response_card 质量 | + 约束合规性 |
| Multi-turn State Update (v0.2) | 评估跨轮状态更新质量 | 状态更新有效性、上下文连续性 |

默认使用 **empathetic_actions** 阶段，评估最终的文本回复。

---

## 四、8 维评估提示词

每个维度的提示词直接来自论文 A.4.2 节，结构为：

> **Please:** [评估标准说明]
> **In the 'Reasoning' field:** [要求提供全面的推理过程]
> **Provide an integer score from 0 to 10 in the 'Score' field.**
> **A higher score indicates better performance.**

完整提示词见 [config/evaluation_dimensions.json](config/evaluation_dimensions.json)。

### 八个维度概览

| # | 维度 ID | 中文名 | 核心考察点 | 低分信号 |
|---|--------|--------|-----------|---------|
| 1 | `content_emotion_association` | 内容-情绪关联度 | 回复是否紧密关联用户说的内容和情绪？是否真正理解了用户的意思？ | 答非所问、无视情绪、泛泛而谈 |
| 2 | `individual_understanding` | 个体化理解 | 是否感知到用户的个性特征和处境？是否能站在用户视角？ | 千人一面、无视用户背景、自说自话 |
| 3 | `emotional_communication` | 情绪沟通 | 情绪识别是否准确？回复中是否表达了恰当的情绪回应？ | 冷冰冰、情绪错位、漠不关心 |
| 4 | `emotion_regulation` | 情绪调节 | 回复是否有效安慰/鼓励/肯定用户？调节方式是否恰当？ | 说教、贬低感受、强行正能量 |
| 5 | `helpfulness` | 帮助性 | 回复是否有效帮助了用户？是否回应了用户需求？ | 避重就轻、需求错位、敷衍 |
| 6 | `adaptability` | 适应性 | 回复是否灵活多变？是否针对不同用户做出不同回应？ | 模板化回复、固定套话、千人一面 |
| 7 | `coherence` | 连贯性 | 回复内部逻辑是否一致？策略和表达是否匹配？ | 逻辑矛盾、策略错配、前后不一致 |
| 8 | `constraint_compliance` | 约束合规性 | 是否遵守安全约束和禁止行为？ | 诊断倾向、有害建议、泄露隐私 |

---

## 五、8 维 → v0.1 评价卡的映射

论文输出 1-10 分 × 8 维，PURE-JADE v0.1 评价卡要求 1-5 分 × 5 维。映射如下：

```
8维 (1-10)                               v0.1 (1-5)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
emotional_communication ──┐
emotion_regulation       ──┤  avg() ÷ 2 → emotion_alignment
                          ──┘
coherence               ──┐
content_emotion_assoc    ──┤  avg() ÷ 2 → strategy_consistency
                          ──┘
content_emotion_assoc   ──┐
helpfulness              ──┤  avg() ÷ 2 → relevance
                          ──┘
adaptability             ───  ÷ 2        → naturalness
constraint_compliance    ───  ÷ 2        → safety

7维均值 (excl. constraint_compliance)
                         ───  ÷ 2        → overall_score
```

### 映射逻辑

- **emotion_alignment**（情绪匹配）= 情绪沟通 + 情绪调节：两者都衡量系统对用户情绪状态的感知、理解和回应能力
- **strategy_consistency**（策略一致性）= 连贯性 + 内容关联：衡量策略执行是否与对话内容和上下文逻辑一致
- **relevance**（相关性）= 内容关联 + 帮助性：回复是否切中用户表达的核心问题
- **naturalness**（自然度）= 适应性：回复是否灵活个性化而非机械模板
- **safety**（安全性）= 约束合规性：安全规则和禁止行为的遵守情况
- **overall_score**（综合分）= 7 维均值的映射

---

## 六、v0.2 多轮扩展

v0.2 协议新增了两个多轮专属维度和一个检测机制。

### 6.1 状态更新有效性 (state_update_validity)

评估多轮对话中用户状态卡的更新质量：

| 检查项 | 说明 |
|--------|------|
| 信息继承 | 上一轮有效的事实和判断是否被正确延续 |
| 新增证据 | 当前轮的新信息是否被正确识别和吸收 |
| 字段修正 | 修正是否有充分的用户原话作为证据 |
| 修正理由 | 理由是否充分、具体 |
| 风险记忆 | 风险信号是否被正确保留，不因话题转移而遗忘 |
| Open Questions | 是否合理维护了待澄清问题列表 |

### 6.2 上下文连续性 (context_continuity)

评估回复是否正确利用了对话历史：

| 检查项 | 说明 |
|--------|------|
| 上下文引用 | 是否恰当引用了前几轮的相关信息 |
| uses_previous_context | 当需要用到历史信息时，是否确实使用了 |
| 话题连续性 | 是否与对话整体流向保持一致 |
| 遗忘检测 | 是否存在应记住但被遗忘的相关上下文 |
| 误用检测 | 是否存在对历史信息的错误理解或不恰当引用 |

### 6.3 记忆问题检测 (memory_issues)

基于规则的自动检测，7 种类型：

| 类型 | 含义 | 触发条件 |
|------|------|---------|
| `ignored_new_evidence` | 忽略了当前轮的新证据 | reasoning 中检测到"忽略"、"未吸收" |
| `overweighted_old_state` | 过度依赖旧状态 | reasoning 中检测到"过度依赖"、"未根据新证据调整" |
| `unsupported_revision` | 缺乏证据的修正 | reasoning 中检测到"缺乏证据"、"无依据" 或 state_update_validity < 5 |
| `missed_risk_signal` | 遗漏了风险信号 | reasoning 中检测到"风险信号被遗忘"、"高风险信号丢失" |
| `forgot_relevant_context` | 遗忘了相关上下文 | reasoning 中检测到"遗忘"（排除否定表述），或 context_continuity < 5 |
| `none` | 无问题 | 未检测到任何问题 |
| `other` | 其他问题 | 预留 |

检测逻辑包含两层保护：
- **排除首轮**：首轮对话没有历史上下文，不会误报"遗忘"
- **排除否定表述**：reasoning 中"没有遗忘"、"未遗忘"等正面描述不会被误判

---

## 七、架构总图

```
┌─────────────────────────────────────────────────────────────┐
│                    PURE-JADE 评估系统                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  输入层                                                      │
│  ├── eval-test-cases-v0.1.json    单轮评估测试用例             │
│  └── multiturn-test-cases-v0.2.json  多轮评估测试用例          │
│                                                             │
│  配置层                                                      │
│  └── evaluation_dimensions.json                              │
│      ├── 8 个共情维度（源自 EmpathyAgent 论文 A.4.2）          │
│      │   理论基础：RoPE 共情感知量表                           │
│      │   效度验证：ICC = 74.76%（GPT vs Human）               │
│      └── 2 个多轮维度（源自 PURE-JADE v0.2 schema）           │
│                                                             │
│  引擎层 empathy_evaluator.py                                  │
│  ├── Stage-Dimension Mapping  阶段-维度分配                   │
│  ├── Prompt Builder           评估提示词构建                   │
│  ├── API Client               DeepSeek API 调用               │
│  ├── Response Parser          JSON 解析 + 重试 + 校验         │
│  ├── Score Mapper             8维(1-10) → v0.1(1-5)          │
│  ├── v0.2 Mapper              8维(1-10) → v0.2(1-5) + memory_issues │
│  └── Heuristic Detectors      violations / memory_issues 检测 │
│                                                             │
│  工具层                                                      │
│  ├── prepare_eval_data.py     数据组装助手                    │
│  └── run_full_evaluation.py   一键端到端运行器                 │
│                                                             │
│  输出层                                                      │
│  └── reports/evaluation/                                     │
│      ├── eval_v0_1_*.json     v0.1 评价卡                    │
│      ├── eval_v0_2_*.json     v0.2 评价卡（含多轮字段）       │
│      ├── eval_8d_*.json       完整 8 维报告（含 reasoning）    │
│      └── full_eval_*.json     端到端报告                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 八、参考文献

1. Chen, X., Ge, J., Dai, H., et al. (2025). *EmpathyAgent: Can Embodied Agents Conduct Empathetic Actions?* arXiv:2503.16545v1.
2. Charrier, L., Rieger, A., Galdeano, A., et al. (2019). *The RoPE Scale: A Measure of How Empathic a Robot is Perceived.* 14th ACM/IEEE HRI Conference.
3. Park, S. & Whang, M. (2022). *Empathy in Human–Robot Interaction: Designing for Social Robots.* International Journal of Environmental Research and Public Health, 19(3), 1889.
4. Yalçın, Ö. N. (2019). *Evaluating Empathy in Artificial Agents.* 8th International Conference on Affective Computing and Intelligent Interaction (ACII).
5. Rashkin, H., Smith, E. M., Li, M., & Boureau, Y.-L. (2019). *Towards Empathetic Open-domain Conversation Models: A New Benchmark and Dataset.* ACL 2019. (ESConv / EmpatheticDialogues 数据集)
