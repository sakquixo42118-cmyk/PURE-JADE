# ESConv 使用方案 v0.1

## 数据来源

ESConv 官方仓库：

<https://github.com/thu-coai/Emotional-Support-Conversation>

本项目第一阶段使用以下文件：

| 文件 | 作用 | 本地位置 |
|---|---|---|
| `ESConv.json` | 主数据集，包含情绪支持对话、问题类型、情绪类型和逐轮策略标注 | `data/raw/esconv/ESConv.json` |
| `strategy.json` | ESConv 8 类支持策略标签 | `data/raw/esconv/strategy.json` |

原始数据仅用于学术研究和课程项目。仓库通过 `.gitignore` 忽略 `data/raw/`，避免误提交原始数据。

## 下载方式

在仓库根目录运行：

```powershell
New-Item -ItemType Directory -Force -Path data\raw\esconv
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/thu-coai/Emotional-Support-Conversation/main/ESConv.json" -OutFile "data\raw\esconv\ESConv.json"
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/thu-coai/Emotional-Support-Conversation/main/strategy.json" -OutFile "data\raw\esconv\strategy.json"
```

## 实际字段结构

本地检查结果：

- 对话数量：`1300`
- 顶层字段：
  - `experience_type`
  - `emotion_type`
  - `problem_type`
  - `situation`
  - `survey_score`
  - `dialog`
  - `seeker_question1`
  - `seeker_question2`
  - `supporter_question1`
  - `supporter_question2`
- `dialog` 内每轮字段：
  - `speaker`
  - `annotation`
  - `content`

支持者回复中的策略标注位于：

```json
{
  "speaker": "supporter",
  "annotation": {
    "strategy": "Question"
  },
  "content": "Hello, what would you like to talk about?"
}
```

## ESConv 8 类策略

`strategy.json` 中的策略为：

```json
[
  "[Question]",
  "[Restatement or Paraphrasing]",
  "[Reflection of feelings]",
  "[Self-disclosure]",
  "[Affirmation and Reassurance]",
  "[Providing Suggestions]",
  "[Information]",
  "[Others]"
]
```

在本项目卡片中统一去掉方括号，使用：

```json
[
  "Question",
  "Restatement or Paraphrasing",
  "Reflection of feelings",
  "Self-disclosure",
  "Affirmation and Reassurance",
  "Providing Suggestions",
  "Information",
  "Others"
]
```

## 第一阶段使用方式

ESConv 不直接替代项目的状态卡、策略卡或评价卡。它主要提供三类支持：

1. 固定策略空间：策略决策卡的主策略和辅助策略采用 ESConv 8 类策略。
2. 典型案例库：从支持者回复中抽取“上下文 + 策略 + 支持者回复”。
3. 后续评估：用于构造 Pipeline、Pipeline + ESConv 与 Baseline 的对比实验。

第一版不做复杂向量数据库。先抽取一个均衡样例库，每类策略 5-10 条，供 Prompt few-shot 和答辩展示使用。

## 抽取后的案例格式

抽取脚本输出 JSON Lines，每行一个案例：

```json
{
  "example_id": "esconv_0000_t001",
  "source": "ESConv",
  "conversation_index": 0,
  "turn_index": 1,
  "emotion_type": "anxiety",
  "problem_type": "job crisis",
  "situation": "用户提供的背景描述",
  "survey_score": {},
  "context": [
    {
      "speaker": "seeker",
      "content": "Hello"
    }
  ],
  "strategy": "Question",
  "supporter_response": "Hello, what would you like to talk about?"
}
```

## 抽取命令

生成每类最多 10 条的均衡样例库：

```powershell
python scripts\extract_esconv_examples.py --max-per-strategy 10 --output data\processed\esconv_examples_sample.jsonl
```

生成完整案例库：

```powershell
python scripts\extract_esconv_examples.py --output data\processed\esconv_examples_full.jsonl
```

输出目录 `data/processed/` 默认忽略，不提交到 git。

## 与策略卡的关系

当策略决策模块实际使用某些 ESConv 案例时，策略卡应在 `esconv_example_ids` 中写入对应案例 ID，例如：

```json
{
  "esconv_example_ids": ["esconv_0000_t001", "esconv_0042_t007"]
}
```

如果没有检索或没有人工匹配案例，必须输出：

```json
{
  "esconv_example_ids": []
}
```

## Few-shot 参考案例

首批人工筛选的 few-shot 策略参考案例见：

- `docs/few-shot-selection.md`
- `examples/strategy-references-v0.1.json`

这些案例只保留中文摘要、推断用户状态、策略理由和回应模式，不保留 ESConv 原始支持者回复全文。它们只能进入策略决策 Prompt，不进入最终行为回应生成 Prompt。

## 注意事项

- 不要直接复制 ESConv 原始回复作为最终回复。
- ESConv 主要提供对话和策略标签，不提供本项目的全部字段，例如 `support_intention`、`response_timing` 和 `response_intensity`。
- 如果 Demo 主要使用中文，可以先人工翻译少量典型案例，并在答辩中说明翻译和筛选过程。
- 最终实验应避免把测试用例提前放入 Prompt，减少数据泄漏。
