# PURE-JADE 共情对话策略决策系统

面向中文共情支持对话的策略决策 pipeline，基于四卡协议（用户状态卡 → 策略决策卡 → 行为回应卡 → 评价卡）。

## 项目结构

```
├── run_strategy_pipeline.py          # 策略决策 pipeline（研究二）
├── test-cases-v0.1.json              # 单轮 golden 测试用例（3个）
│
├── config/
│   └── evaluation_dimensions.json    # EmpathyAgent 8维评估提示词 + v0.2 多轮维度
│
├── scripts/
│   ├── empathy_evaluator.py          # 8维评估引擎（研究三核心）
│   └── run_full_evaluation.py        # 一键端到端：pipeline → 评估
│
├── examples/
│   ├── eval-test-cases-v0.1.json     # 单轮评估测试用例
│   └── multiturn-test-cases-v0.2.json # 多轮评估测试用例
│
├── reports/evaluation/               # 评估报告输出目录
│
├── schema-v0.1.md                    # v0.1 四卡协议 JSON Schema
├── schema-v0.2.md                    # v0.2 多轮扩展协议
├── schema-v0.2.1.md                  # v0.2.1 实现契约补丁
│
├── .env                              # API 配置（需自行创建）
└── .env.example                      # API 配置模板
```

## 四卡协议

```
用户输入
  → 用户状态卡 (user_state_card)
  → 共情策略决策卡 (strategy_decision_card)
  → 行为回应卡 (behavior_response_card)
  → 评价卡 (evaluation_card)
```

## 评估系统（研究三）

复现 EmpathyAgent (arXiv:2503.16545v1) 的 8 维参考无关评估框架，适配为中文文本共情对话评估。

### 8 评估维度（1-10 分，LLM 评分）

| 维度 | 映射 v0.1 字段 |
|------|---------------|
| 内容-情绪关联度 | relevance |
| 连贯性 | strategy_consistency |
| 情绪沟通 | emotion_alignment |
| 个体化理解 | emotion_alignment |
| 情绪调节 | emotion_alignment |
| 帮助性 | relevance |
| 适应性 | naturalness |
| 约束合规性 | safety |

### v0.2 多轮专属维度

| 维度 | 说明 |
|------|------|
| 状态更新有效性 | 信息继承、证据吸收、字段修正 |
| 上下文连续性 | 历史引用、遗忘/误用检测 |
| 记忆问题检测 | 7 种自动检测类型 |

---

## 快速开始

### 1. 配置 API

```bash
# 复制模板
copy .env.example .env

# 编辑 .env，填入你的 API key
# 默认使用 DeepSeek，也支持任何 OpenAI 兼容 API
```

### 2. 运行评估

```bash
cd d:\liyutong\puyujihua

# === 场景 A：单轮对话评估（最常用） ===
python scripts\empathy_evaluator.py --mode api --format v0.1 --verbose

# === 场景 B：多轮对话评估 ===
python scripts\empathy_evaluator.py --mode api --cases examples\multiturn-test-cases-v0.2.json --stage multi_turn_state_update --format v0.2 --verbose

# === 场景 C：一键端到端 ===
python scripts\run_full_evaluation.py --mode api --verbose

# === 指定自定义测试用例 ===
python scripts\empathy_evaluator.py --mode api --cases your_cases.json --format v0.1

# === 切换模型 ===
python scripts\empathy_evaluator.py --mode api --api-model qwen-plus --api-url https://dashscope.aliyuncs.com/compatible-mode/v1
```

### 3. 查看报告

报告在 `reports/evaluation/` 目录：

```
reports/evaluation/
├── eval_v0_1_YYYYMMDD_HHMMSS.json   # v0.1 评价卡
├── eval_v0_2_YYYYMMDD_HHMMSS.json   # v0.2 评价卡（含多轮字段）
├── eval_8d_YYYYMMDD_HHMMSS.json     # 完整 8 维报告
└── full_eval_YYYYMMDD_HHMMSS.json   # 端到端报告
```

---

## 准备自己的测试数据

测试用例 JSON 格式（参考 `examples/eval-test-cases-v0.1.json`）：

```json
{
  "cases": [
    {
      "conversation_id": "my_case_001",
      "turn_id": 1,
      "schema_version": "0.2",
      "dialogue": [
        {"speaker": "user", "content": "用户说的话"}
      ],
      "user_state_card": {
        "problem_summary": "...",
        "emotion": ["沮丧", "疲惫"],
        "emotion_intensity": 2,
        "need": ["被理解", "被肯定"],
        "support_stage": "comforting",
        "risk_level": "low",
        ...
      },
      "strategy_decision_card": {
        "support_intention": "comfort",
        "primary_strategy": "Reflection of feelings",
        "secondary_strategy": "Affirmation and Reassurance",
        ...
      },
      "behavior_response_card": {
        "text_response": "系统生成的共情回复文本",
        "tone_style": "warm_and_calm",
        ...
      }
    }
  ]
}
```

多轮数据需额外提供 `previous_user_state_card`（参考 `examples/multiturn-test-cases-v0.2.json`）。

---

## 命令行参考

### empathy_evaluator.py

```
--mode {api,rules}         评估模式（默认 api）
--cases PATH               测试用例 JSON 路径
--dimensions PATH          评估维度配置文件路径
--stage STAGE              评估阶段：
                             empathetic_actions（默认推荐）
                             multi_turn_state_update（v0.2多轮）
                             scenario_understanding / empathetic_planning
--format {full,v0.1,v0.2,both}
                           输出格式（默认 full）
--output PATH              指定输出路径
--api-model MODEL          API 模型名
--api-url URL              API 地址
--verbose, -v              输出详细进度
```

### run_full_evaluation.py

```
--mode api                 评估模式
--cases PATH               测试用例路径
--eval-stage STAGE         评估阶段（默认 empathetic_actions）
--output PATH              报告输出路径
--verbose, -v              详细输出
```

---

## 依赖

- Python 3.10+
- PyMuPDF（仅 PDF 提取时需要，`pip install PyMuPDF`）
- 无其他第三方依赖（API 调用使用标准库 `urllib`）
- DeepSeek API key（或其他 OpenAI 兼容 API）
