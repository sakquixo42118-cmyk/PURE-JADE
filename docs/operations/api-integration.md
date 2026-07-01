# API 接入说明

## 当前封装

API 接入已经从具体 pipeline 中抽出来，统一放在：

```text
scripts/pure_jade_api.py
```

它负责：

1. 读取 `.env` 和命令行参数；
2. 规范化 OpenAI-compatible `chat/completions` URL；
3. 组装 HTTP 请求；
4. 提取模型回复文本；
5. 从模型回复中解析 JSON 对象；
6. 在输出不合法时生成重试提示。

具体业务脚本只负责：

```text
构造 prompt
-> 调用 pure_jade_api
-> 校验返回卡片
-> 写报告
```

## 配置 `.env`

从 `.env.example` 复制一份 `.env`，填入真实配置：

```text
PURE_JADE_API_URL=https://api.deepseek.com
PURE_JADE_API_KEY=replace-with-your-api-key
PURE_JADE_API_MODEL=replace-with-your-model

PURE_JADE_API_TEMPERATURE=0.2
PURE_JADE_API_TIMEOUT_SECONDS=60
PURE_JADE_API_MAX_RETRIES=1
PURE_JADE_API_JSON_MODE=1
```

`PURE_JADE_API_URL` 可以写 base URL，也可以写完整 endpoint：

```text
https://api.deepseek.com
https://api.deepseek.com/chat/completions
https://api.openai.com/v1/chat/completions
```

如果只写 base URL，代码会自动追加 `/chat/completions`。

## 先做 dry-run

dry-run 不会联网，只会检查 `.env` 是否能读取，并把将要发送的 smoke-test messages 写入报告：

```powershell
python scripts\api_smoke_test.py
```

默认报告：

```text
reports/final/local/api_smoke_test_dry_run_report.json
```

## 测试 API 连通性

确认允许联网后，运行：

```powershell
python scripts\api_smoke_test.py --send
```

这个 smoke test 不发送项目样例，只发送一个最小 JSON 测试请求，确认：

- `.env` 配置正确；
- endpoint 能访问；
- model 能返回内容；
- JSON mode 是否可用；
- 返回文本能否被解析为 JSON。

报告：

```text
reports/final/api/api_smoke_test_report.json
```

## 跑 v0.1 第二部分 API

```powershell
python scripts\run_strategy_pipeline.py --mode api
```

输入：

```text
examples/test-cases-v0.1.json
examples/strategy-references-v0.1.json
```

输出：

```text
reports/final/api/strategy_pipeline_api_report.json
```

## 跑 v0.2.1 第二部分 API

v0.2.1 不再从单轮 case 文件读取状态，而是从本地 `conversation_record` 读取最新用户状态卡：

```powershell
python scripts\run_strategy_pipeline_v021.py --mode api --turn-id 2
```

输入：

```text
examples/conversation-record-v0.2.1.json
```

脚本会构造：

```text
current_user_message
+ latest_user_state_card
+ strategy_references
-> strategy_decision_card v0.2
```

默认报告：

```text
reports/final/api/strategy_pipeline_v021_api_turn2_report.json
```

报告名会自动带上 `mode` 和 `turn_id`，所以第 1 轮和第 2 轮不会互相覆盖：

```text
reports/final/api/strategy_pipeline_v021_api_turn1_report.json
reports/final/api/strategy_pipeline_v021_api_turn2_report.json
```

## 处理流程

真实 API 模式的流程是：

```text
1. 读取 .env
2. 规范化 API URL
3. 构造 messages
4. POST 到 chat/completions
5. 读取 choices[0].message.content
6. 解析 JSON 对象
7. 校验卡片字段、枚举值和核心策略
8. 如果解析或校验失败，带错误信息重试
9. 写入 reports/
```

## 注意事项

- `.env` 不能提交到仓库。
- API 模式会把测试样例内容发送到配置的 endpoint。
- `api_smoke_test.py --send` 只测试连通性，不发送项目样例。
- 如果供应商不支持 JSON mode，把 `.env` 中的 `PURE_JADE_API_JSON_MODE` 改成 `0`。
- 如果 API 输出不是合法 JSON，报告里会保留 raw output 和校验错误，方便调整 prompt。
