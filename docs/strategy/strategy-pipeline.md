# 研究内容二 Pipeline v0.1

## 目的

本文件说明如何只实现和展示“研究内容二：用户状态到共情策略的映射”。

当前第二部分 pipeline 的边界是：

```text
原始对话
+ 用户状态卡
+ ESConv 策略参考案例摘要
-> 共情策略决策卡
```

它不负责生成最终回复，也不负责生成评价卡。最终回复和评价可以作为后续模块或答辩中的下游展示，但不是本模块的主要产出。

## 为什么可以只做第二部分

可以。因为研究内容二本身就是一个独立模块：它解决的问题不是“怎么把话说出来”，而是“在当前用户状态下，系统应该采用什么支持意图、什么共情策略、什么回应时机和强度”。

因此答辩时可以把重点放在：

- 输入：用户状态卡；
- 依据：策略映射规则和 ESConv few-shot 策略参考；
- 输出：共情策略决策卡；
- 校验：策略是否与 golden case 的预期策略一致。

## 当前脚本

运行：

```powershell
python scripts\run_strategy_pipeline.py
```

默认输入：

```text
examples/test-cases-v0.1.json
examples/strategy-references-v0.1.json
```

扩展测试集：

```text
examples/strategy-test-cases-expanded-v0.1.json
```

这份文件只用于第二部分策略决策测试，不包含行为回应卡和评价卡。运行时用 `--cases` 指定即可：

```powershell
python scripts\run_strategy_pipeline.py --cases examples\strategy-test-cases-expanded-v0.1.json
```

默认输出：

```text
reports/final/local/strategy_pipeline_report.json
```

脚本默认使用 `rules` 模式，即用本地规则模拟第二部分策略决策逻辑：

```powershell
python scripts\run_strategy_pipeline.py --mode rules
```

也可以使用 `mock` 模式，直接回放 golden case 中人工标注的策略决策卡：

```powershell
python scripts\run_strategy_pipeline.py --mode mock
```

`mock` 的作用是稳定演示接口和校验流程，不代表模型真的完成了推理。后续接入 API 时，只需要把 `rules/mock` 的输出替换成模型输出，校验逻辑仍然可以复用。

## API 模式

API 模式用于让大模型实际完成第二部分策略决策：

```text
原始对话
+ 用户状态卡
+ ESConv 策略参考摘要
-> API
-> 共情策略决策卡
-> 本地校验
```

API 配置、HTTP 请求和 JSON 解析已封装在 `scripts/pure_jade_api.py`；组员可先按 `docs/operations/api-integration.md` 运行 `scripts/api_smoke_test.py` 检查配置和连通性。

运行：

```powershell
python scripts\run_strategy_pipeline.py --mode api
```

需要先在仓库根目录配置 `.env`，格式见 `.env.example`：

```text
PURE_JADE_API_URL=https://api.openai.com/v1/chat/completions
PURE_JADE_API_KEY=replace-with-your-api-key
PURE_JADE_API_MODEL=replace-with-your-model
```

脚本使用 OpenAI-compatible chat-completions 请求格式。不同 API 供应商通常只需要替换 `PURE_JADE_API_URL` 和 `PURE_JADE_API_MODEL`。

`PURE_JADE_API_URL` 可以写完整 endpoint，也可以写 base URL。比如：

```text
https://api.openai.com/v1/chat/completions
https://api.deepseek.com
```

如果只写 base URL，脚本会自动追加 `/chat/completions`。

如果供应商不支持 JSON mode，可以在 `.env` 中关闭：

```text
PURE_JADE_API_JSON_MODE=0
```

API 输出仍然会被本地校验器检查：

- 是否是合法 JSON；
- 是否包含策略决策卡必填字段；
- 枚举值是否符合 Schema；
- 高风险场景是否进入 `safety_override`；
- `esconv_example_ids` 是否来自本次 prompt 提供的策略参考案例；
- 核心策略字段是否与 golden case 预期一致。

API 模式不要求 `esconv_example_ids` 与 golden case 完全同一组。原因是 ESConv 参考案例的选择属于上游检索/筛选过程；第二部分 API 的主要评价对象是 `support_intention`、`primary_strategy`、`secondary_strategy`、`response_timing`、`response_intensity` 和 `safety_override` 这些核心策略字段。

API 模式失败时，报告中会保留每次尝试的原始输出和错误原因，方便调整 prompt。

如果要展示“没有 ESConv 策略参考”的对照结果，可以运行：

```powershell
python scripts\run_strategy_pipeline.py --no-references --report reports\final\local\strategy_pipeline_no_references_report.json
```

API 模式同样支持这个对照：

```powershell
python scripts\run_strategy_pipeline.py --mode api --no-references --report reports\final\api\strategy_pipeline_api_no_references_report.json
```

扩展测试集的 API 对照命令：

```powershell
python scripts\run_strategy_pipeline.py --mode api --cases examples\strategy-test-cases-expanded-v0.1.json --report reports\final\api\strategy_pipeline_api_expanded_report.json

python scripts\run_strategy_pipeline.py --mode api --no-references --cases examples\strategy-test-cases-expanded-v0.1.json --report reports\final\api\strategy_pipeline_api_expanded_no_references_report.json
```

## 只看第二部分时展示什么

每个 case 展示四块即可：

1. 用户原始输入；
2. 用户状态卡；
3. 选入 prompt 的 ESConv 策略参考摘要；
4. 第二部分输出的共情策略决策卡。

行为回应卡可以放在“下游模块示例”里，不要把它说成第二部分自己的主要成果。

## ESConv 在这里的作用

ESConv 不直接提供最终回复。它在本模块中只提供策略参考：

- 哪类用户状态常对应哪类支持策略；
- 什么情况下先澄清，什么情况下先安抚；
- 什么情况下适合建议或信息支持；
- 哪些策略容易不合适，例如过早建议、连续追问、空泛安慰。

因此 prompt 中放入的是“策略参考案例摘要”，不是 ESConv 原始回复全文。

## 与完整系统的关系

完整系统可以长这样：

```text
用户输入
-> 用户状态卡
-> 共情策略决策卡
-> 行为回应卡
-> 评价卡
```

但当前可先只完成并验证：

```text
用户状态卡
-> 共情策略决策卡
```

这样范围更清晰，也更符合当前分工。

## v0.2 多轮输入

`docs/schema/schema-v0.2.md` 增加了多轮状态更新字段。第二部分的职责不变，仍然是输出共情策略决策卡；变化在于输入应使用“最新用户状态卡”，而不是只看当前一句话。

多轮时推荐输入：

```text
历史摘要
+ 最新 user_state_card v0.2
+ 当前用户输入
+ ESConv 策略参考摘要
-> strategy_decision_card v0.2
```

第二部分需要响应第一部分更新后的状态变化，例如：

- `support_stage` 从 `comforting` 变成 `exploration` 时，策略可从直接安慰切到澄清；
- `need` 新增 `解决方案` 或 `事实资源` 时，策略可逐步靠近建议或信息支持；
- `risk_level` 上升时，必须进入 `safety_override`。

v0.1 测试仍保留为单轮基线；v0.2 后续应新增多轮测试集，参考 `examples/multiturn-test-cases-v0.2.json`。

`docs/schema/schema-v0.2.1.md` 进一步明确了多轮实现契约：

```text
第一部分状态更新 API:
previous_state_snapshot + recent_dialogue_window + current_user_message
-> updated_user_state_card

第二部分策略决策 API:
latest_user_state_card + current_user_message + strategy_references
-> strategy_decision_card
```

程序还需要本地维护 `conversation_record`，保存完整 `dialogue_log`、每轮 `turn_records` 和下一轮要读取的 `current_state`。示例见 `examples/conversation-record-v0.2.1.json`。

<u>这里的 `current_state` 是本地缓存，不是 API key 自带记忆；下一轮应从它构造 `previous_state_snapshot`，再和最近对话窗口、当前用户输入一起组成状态更新请求。</u>

## v0.2.1 第二部分脚本

`scripts/run_strategy_pipeline_v021.py` 用于先跑通多轮协议下的第二部分策略决策。它不生成用户状态卡，也不生成最终回复或评价卡；它只从 `conversation_record` 中读取目标轮次的最新状态卡，并构造：

<u>该脚本验证的是第二部分读取方式：`strategy_decision_request` 只包含当前用户原话、最新用户状态卡和可选策略参考，不直接把完整 `conversation_record` 传给模型。</u>

```text
current_user_message
+ latest_user_state_card
+ strategy_references
-> strategy_decision_card v0.2
```

默认运行第 2 轮示例：

```powershell
python scripts\run_strategy_pipeline_v021.py
```

默认输入：

```text
examples/conversation-record-v0.2.1.json
examples/strategy-references-v0.1.json
```

默认输出：

```text
reports/final/local/strategy_pipeline_v021_rules_turn2_report.json
```

默认报告名会自动带上 `mode` 和 `turn_id`。例如第 1 轮和第 2 轮会分别写入：

```text
reports/final/local/strategy_pipeline_v021_rules_turn1_report.json
reports/final/local/strategy_pipeline_v021_rules_turn2_report.json
```

也可以直接回放 record 中已有的策略卡：

```powershell
python scripts\run_strategy_pipeline_v021.py --mode mock --report reports\final\local\strategy_pipeline_v021_mock_report.json
```

如果要指定轮次或手动指定 ESConv 参考案例：

```powershell
python scripts\run_strategy_pipeline_v021.py --turn-id 2 --reference-id esconv_1230_t006
```

API 模式沿用 `.env` 中的 OpenAI-compatible 配置：

```powershell
python scripts\run_strategy_pipeline_v021.py --mode api
```

API 模式同样会自动按轮次命名报告：

```text
reports/final/api/strategy_pipeline_v021_api_turn2_report.json
```

这一步的意义是先证明第二部分已经能接 v0.2.1 的 `conversation_record`，而不是继续依赖 v0.1 的单轮 golden case 文件。
