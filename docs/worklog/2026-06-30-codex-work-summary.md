# 2026-06-30 Codex 工作过程总结

本文档总结本轮在 Codex 桌面端完成的主要排查、修复、测试和边界约定。由于另有一台电脑上的对话不在当前上下文中，本文只覆盖本线程中可见和已执行的工作。

## 起因

本轮开始时，仓库已经更新了四个部分的脚本，但尚未做完整链条测试。同时发现上传时误把 API key 相关文件提交到了仓库，导致组员余额被消耗。

核心目标逐步变为：

1. 排查 API key 为什么被提交。
2. 防止后续继续提交 `.env` / `*.env`。
3. 验证四部分脚本是否能单独跑通。
4. 在不改组员原始 first 和 forth 核心源码的前提下，补一个完整链路 runner。
5. 补文档并整理 `docs/` 目录。

## API key 泄露排查

检查结果：

- 当前真实仓库在 `G:\university\璞玉项目\pre\PURE-JADE`。
- `scripts/first/.env` 和 `scripts/third/.env` 当前未被 Git 跟踪。
- 已被跟踪并进入远端历史的是 `scripts/third——v0.2/(2).env`。
- 原 `.gitignore` 只忽略 `.env`，没有覆盖 `*.env` 或 `*.env.*`。
- 两个 `.env.example` 里曾出现真实 key 形态内容，example 文件本来会被提交，因此也属于泄露风险。

处理结果：

- 更新 `.gitignore`，忽略 `.env`、`.env.*`、`*.env`、`*.env.*`，保留 `.env.example`。
- 脱敏 `scripts/first/.env.example`。
- 脱敏 `scripts/first_v021_boundary_copy/.env.example`。
- 从 Git 跟踪中移除 `scripts/third——v0.2/(2).env`，本地文件仍被 ignored。
- 做过 key 形态扫描，当前 tracked 文件未再命中明显 `sk-...` 形态。

用户后续确认相关 key 已 revoke。

## 源码保护边界

用户明确要求不要改组员发来的原始核心代码。

已执行的边界处理：

- 曾短暂修改过 `scripts/first/main.py` 和 `scripts/first/requirements.txt`，后来按用户要求全部撤回。
- 曾短暂修改过 `scripts/forth/empathy_evaluator.py`，后来按用户要求全部撤回。
- 当前不再改 `scripts/first/` 原始核心代码。
- 当前不再改 `scripts/forth/` 源码。

保留的代码改动：

- `scripts/first_v021_boundary_copy/main.py`：副本入口优先读取第二部分统一 API 配置。
- `scripts/run_full_chain_v021.py`：新增完整链路 runner。

## 单段测试结果

已验证：

- 23 个 Python 文件语法检查通过；新增 runner 后为 24 个 Python 文件语法检查通过。
- `scripts/api_smoke_test.py --send` 真实 API smoke 通过。
- 第二部分：
  - `run_strategy_pipeline.py --mode rules`：3/3 pass。
  - `run_strategy_pipeline.py --mode mock`：3/3 pass。
  - `run_strategy_pipeline_v021.py --mode rules`：pass。
  - `run_strategy_pipeline_v021.py --mode mock`：pass。
  - v0.1 API 单 case：pass。
- 第三部分：
  - `behavior_generator_api_schema_aligned.py --mode dry-run`：pass。
  - `behavior_generator_api_schema_aligned.py --mode mock`：pass。
  - API 单例：pass。
- 第一部分：
  - `scripts/first` 原始入口 `/health` 曾验证可返回 200，但该源码已恢复，不作为当前主链路修改点。
  - `scripts/first_v021_boundary_copy` `/health` 返回 200。
  - `scripts/first_v021_boundary_copy` `/generate_state_card` 真实 API 调用返回 200。
- 第四部分：
  - 用显式参数 `--env-file .env --dimensions scripts/forth/evaluation_dimensions.json` 跑单例评估通过。
  - 单例评估结果曾得到 `v0.1=5/5`。

## 完整链路 runner

新增文件：

```text
scripts/run_full_chain_v021.py
```

链路：

```text
first_v021_boundary_copy
-> run_strategy_pipeline_v021.py
-> third/behavior_generator_api_schema_aligned.py
-> forth/run_full_evaluation.py
```

runner 做的事情：

- 接收 `--message` 时调用 first v0.2.1 副本生成状态卡和 conversation record。
- 接收 `--record` 时跳过 first，直接使用已有 v0.2.1 record。
- 复制一份工作 record 到 `reports/full_chain_v021/<run_id>/conversation_record_v021_chain.json`。
- 调用第二部分生成 `strategy_decision_card`，并回填到工作 record。
- 调用第三部分生成 `behavior_response_card`，并回填到工作 record。
- 从工作 record 生成 fourth 需要的 `04_evaluation_cases.json`。
- 调用 `scripts/forth/run_full_evaluation.py` 做评估。
- 写出 `full_chain_summary.json`。

runner 定位：

- 是编排层，不是单文件替代项目。
- 不复制四部分核心逻辑。
- 运行时仍依赖原本链条文件存在。

## 完整链路验证

已验证 dry-run：

```powershell
python -B scripts\run_full_chain_v021.py `
  --record examples\conversation-record-v0.2.1.json `
  --strategy-mode rules `
  --behavior-mode dry-run `
  --skip-evaluation `
  --run-id codex_chain_dry_run
```

结果：pass。

已验证从用户输入开始的 first 集成 dry-run：

```powershell
python -B scripts\run_full_chain_v021.py `
  --message "I feel exhausted by exams and I am not sure what to do." `
  --strategy-mode rules `
  --behavior-mode dry-run `
  --skip-evaluation `
  --run-id codex_chain_first_dry_run
```

结果：pass。

已验证完整 API 链路：

```powershell
python -B scripts\run_full_chain_v021.py `
  --record examples\conversation-record-v0.2.1.json `
  --strategy-mode api `
  --behavior-mode api `
  --eval-stage empathetic_actions `
  --run-id codex_chain_api_record
```

结果：

- strategy stage：pass。
- behavior stage：pass。
- forth evaluation：pass。
- 评估输出 `v0.1=5/5`，violations 为 0。

## 依赖问题

测试 first 阶段时遇到：

```text
Using SOCKS proxy, but the 'socksio' package is not installed.
```

原因是当前网络环境使用 SOCKS 代理，而 `httpx` 需要 `socksio` 支持。`scripts/first_v021_boundary_copy/requirements.txt` 已包含 `socksio>=1.0.0`。原始 `scripts/first/requirements.txt` 没有保留修改。

## 当前 staged 改动概览

截至本文档创建时，主要 staged 改动包括：

- `.gitignore`
- `scripts/first/.env.example`
- `scripts/first_v021_boundary_copy/.env.example`
- `scripts/first_v021_boundary_copy/main.py`
- `scripts/run_full_chain_v021.py`
- 删除 `scripts/third——v0.2/(2).env`
- 新增和整理 `docs/` 文档

## 后续建议

建议下一步：

1. 用中文展示样例跑一次完整链路，并保留输出报告。
2. 检查 `reports/full_chain_v021/<run_id>/` 下所有输出是否适合答辩展示。
3. 单独提交防泄露和 runner 文档改动。
4. push 前再检查一次 `git diff --cached --name-status`。
5. 如果需要公开仓库，考虑是否还要清理 Git 历史；即使 key 已 revoke，历史中仍可能存在泄露痕迹。
