# 研究内容二测试结果 v0.1

## 测试范围

本轮测试只覆盖第二部分 pipeline：

```text
原始对话 + 用户状态卡 + ESConv 策略参考摘要
-> 共情策略决策卡
```

不测试最终回复生成，也不测试评价卡生成。

## 测试集

当前有两组测试集：

| 测试集 | 文件 | 数量 | 说明 |
|---|---|---:|---|
| 基础 golden cases | `examples/test-cases-v0.1.json` | 3 | 学习挫败、亲子沟通、孤独陪伴 |
| 扩展策略测试集 | `examples/strategy-test-cases-expanded-v0.1.json` | 8 | 只测第二部分策略决策，覆盖澄清、肯定、建议、信息支持和安全分支 |

扩展测试集新增覆盖：

- 线上课程混乱澄清；
- 羞耻求助肯定；
- 多任务过载建议；
- 居家办公资源信息；
- 高风险安全覆盖；
- 朋友关系矛盾澄清；
- 求职被拒自我否定肯定；
- 哀伤纪念日行动建议。

## 运行命令

基础测试：

```powershell
python scripts\run_strategy_pipeline.py --mode api --report reports\final\api\strategy_pipeline_api_report.json

python scripts\run_strategy_pipeline.py --mode api --no-references --report reports\final\api\strategy_pipeline_api_no_references_report.json
```

扩展测试：

```powershell
python scripts\run_strategy_pipeline.py --mode api --cases examples\strategy-test-cases-expanded-v0.1.json --report reports\final\api\strategy_pipeline_api_expanded_report.json

python scripts\run_strategy_pipeline.py --mode api --no-references --cases examples\strategy-test-cases-expanded-v0.1.json --report reports\final\api\strategy_pipeline_api_expanded_no_references_report.json
```

当前整理后的报告文件位于：

```text
reports/final/api/strategy_pipeline_api_report.json
reports/final/api/strategy_pipeline_api_no_references_report.json
reports/final/api/strategy_pipeline_api_expanded_report.json
reports/final/api/strategy_pipeline_api_expanded_no_references_report.json
```

## 当前结果

| 测试 | ESConv 参考 | 通过 | 失败 |
|---|---|---:|---:|
| 基础测试 | 使用 | 3 | 0 |
| 基础测试 | 不使用 | 3 | 0 |
| 扩展测试 | 使用 | 8 | 0 |
| 扩展测试 | 不使用 | 8 | 0 |

## 解释

当前结果说明：

- 第二部分 API pipeline 已经可以稳定输出合法的策略决策卡；
- 输出可以通过本地 Schema、枚举、安全规则和 golden case 核心策略校验；
- 高风险样例可以进入 `safety_override`，不使用普通 ESConv 策略；
- 当前测试还不能证明 ESConv 参考显著提升判断，因为无 ESConv 对照同样全部通过。

后续如果要证明 ESConv 的增益，需要继续设计更有区分度的样例，例如：

- 没有参考时容易把 `comfort` 误判成 `advise`；
- 没有参考时容易在 `action` 场景漏掉澄清问题；
- 没有参考时容易把 `inform` 写成普通建议；
- 没有参考时容易在自我否定场景只反映情绪而没有具体肯定。
