# PURE-JADE 硬编码推理规则审计

> 本文只记录程序里对“用户状态、策略选择、行为回复、评价判断”做出的硬编码推理、硬拦截、关键词判断和分数封顶。
>
> 不记录普通 schema 字段要求、JSON 输出格式、枚举合法性、API 配置校验、路径校验，也不记录“必须遵守 ESConv 八类策略”这类基础协议。

## 范围

本次审计覆盖：

- `scripts/full_chain_v022/`
- `scripts/full_chain_v023/`
- `scripts/full_chain_v024/`
- `scripts/full_chain_frontend/`

重点是 v0.2.2/v0.2.3/v0.2.4 中在原四卡框架之外额外加入的规则。

## 一、v0.2.2/v0.2.3 策略阶段新增硬规则

位置：

```text
scripts/full_chain_v022/strategy/run_strategy_pipeline_v022.py
scripts/full_chain_v023/strategy/run_strategy_pipeline_v023.py
```

### 1. Question 不是默认动作

触发方式：

- 策略 prompt 明确要求：只有当一个澄清问题会实质改变下一步帮助时，才把 `Question` 作为 `primary_strategy` 或 `secondary_strategy`。

硬动作：

- 压低“默认追问”的倾向。
- 鼓励在信息足够时直接推进，而不是机械问问题。

风险：

- 可能让模型在某些确实需要澄清的场景中少问问题。

### 2. 信息足够时可以主动推进

触发方式：

- 用户已经给出足够信息，或明显正在请求帮助、话术、行动、安顿方式。

硬动作：

- 即使 `support_stage` 仍是 `exploration`，也允许选择 `advise`、`inform`、`affirm` 或 `comfort`。

风险：

- 如果“信息足够”的判断过宽，可能过早建议。

### 3. action 阶段不只限于用户显式说“怎么办”

触发方式：

- 用户处在现实压力、冲突、拖延、学习失控、社交退缩等场景，且已有足够上下文。

硬动作：

- 可以主动给少量可执行下一步。

风险：

- 这个判断仍然依赖 prompt，边界不稳定。

### 4. response_timing 被重新解释

触发方式：

- 策略 prompt 要求根据当轮需要决定 timing。

硬动作：

- 需要立即支持：`respond_now`
- 需要行动：`offer_next_step`
- 信息确实不足：`ask_clarification`

风险：

- 仍可能把“需要先稳住情绪”和“需要行动”错误地二选一。

### 5. 禁止把复述写成策略目标

触发方式：

- 策略 prompt 中要求 `response_goal` 不要写“先复述用户处境”“先表达听到”。

硬动作：

- 降低下游行为卡机械复读。

风险：

- 如果过度执行，可能让回复显得太直接，缺少必要承接。

### 6. Restatement 只能短承接，不能阻止帮助

触发方式：

- 当选择 `Restatement or Paraphrasing`。

硬动作：

- 只要求一句自然短承接。
- 不要列举用户原话细节。
- 不要阻止下游给出有帮助的下一步。

风险：

- 模型可能把“短承接”理解成回复整体过短。

## 二、v0.2.3 新增：现实后果事件硬规则

位置：

```text
scripts/full_chain_v023/strategy/run_strategy_pipeline_v023.py
```

相关函数/常量：

```text
URGENT_EVENT_ACTION_TERMS
URGENT_EVENT_PROBLEM_TERMS
is_urgent_real_world_event()
contains_banned_practical_block()
validate_urgent_real_world_strategy()
```

### 7. 现实后果事件识别

触发方式：

用户输入同时命中：

- 事件词：`考试`、`期末`、`补考`、`缓考`、`教务`、`老师`、`辅导员`、`截止`、`ddl`、`deadline`、`报名`、`缴费`、`答辩`、`面试`、`预约`、`航班`、`火车`
- 问题词：`错过`、`漏掉`、`忘了`、`没赶上`、`迟到`、`过了`、`来不及`、`要炸`、`崩了`

或者命中正则：

```text
(错过|没赶上|忘了).{0,8}(考试|期末|面试|截止|ddl|deadline)
```

硬动作：

- 认定为“现实后果正在发生”的事件。

风险：

- 关键词覆盖不完整，会漏掉类似“我没交作业”“错过申报”。
- 关键词过宽时，可能把普通倾诉误判为需要行动建议。

### 8. 现实后果事件不能只 comfort

触发方式：

- 命中现实后果事件。

硬动作：

- 策略卡必须包含现实下一步倾向：
  - `support_intention` 是 `advise` 或 `inform`，或
  - `primary_strategy` / `secondary_strategy` 包含 `Providing Suggestions` 或 `Information`

如果策略卡只有：

```text
support_intention = comfort
primary_strategy = Reflection of feelings
secondary_strategy = Restatement or Paraphrasing
```

会 validation fail。

风险：

- 可能压低纯情绪陪伴的空间。
- 但对于“错过期末考试”这类事件，目前判断是应该保留。

### 9. 现实后果事件不应 respond_now + comfort-only

触发方式：

- 命中现实后果事件。
- 策略卡同时满足：

```text
response_timing = respond_now
support_intention = comfort
```

硬动作：

- validation fail。
- 要求改成“先短承接，再给低负担下一步”，通常是 `offer_next_step`。

风险：

- 如果用户只是说“我需要先缓一下”，这个规则可能过硬。

### 10. 现实后果事件不能禁止现实帮助

触发方式：

- 命中现实后果事件。
- `constraints`、`prohibited_actions` 或 `response_goal` 中出现类似：
  - 不能/禁止具体行动建议
  - 不能/禁止补考、教务、老师、辅导员相关建议
  - 避免解决方案/具体行动/下一步
  - 只做情绪认可
  - 先专注情绪认可

硬动作：

- validation fail。
- 让 API 重写策略卡。

风险：

- 这里是对前一轮错误的强修复，比较硬。
- 后续可以改成 warning + retry，而不是直接 fail。

## 三、v0.2.2/v0.2.3 行为阶段新增硬规则

位置：

```text
scripts/full_chain_v022/behavior/behavior_generator_api_schema_aligned_v022.py
scripts/full_chain_v023/behavior/behavior_generator_api_schema_aligned_v023.py
```

### 11. 第三部分不读第一部分用户状态卡

触发方式：

- 行为卡生成只使用：
  - `recent_dialogue_window`
  - `strategy_decision_card`

硬动作：

- 不读取、不重新推断 `user_state_card`。

风险：

- 模块边界清楚，但如果策略卡错了，行为阶段很难自救。

### 12. 避免模板化开头

触发方式：

- 行为 prompt 直接要求避免反复使用：
  - “我听到你说”
  - “听起来”
  - “我能感受到”
  - “我理解你现在”
  - “你提到”
  - “确实很难受”

硬动作：

- 降低固定共情句式。

风险：

- 这不是校验硬拦截，主要是 prompt 约束。
- 模型可能因此变得过短或不够温暖。

### 13. 最多一个问题

触发方式：

- 行为 prompt 和校验都限制 `follow_up_question_count` 为 0 或 1。
- 回复中问号超过 1 会 validation fail。

硬动作：

- 防止连续追问。

风险：

- 一些复杂现实场景可能需要两个很短的问题，但现在会被硬拦。

### 14. 安全场景允许一个必要安全确认问题

触发方式：

- `safety_override = true`

硬动作：

- 允许最多一个安全确认问题。
- 自伤风险禁止追问方法、工具、地点、计划细节。
- 现实冲突/暴力风险可以问是否安全、是否能远离现场。

风险：

- 仍依赖上游风险类型是否分得准确。

### 15. 危险安全追问触发本地 fallback

位置：

```text
UNSAFE_SAFETY_FOLLOWUP_PATTERNS
SAFETY_FALLBACK_RESPONSE
normalize_behavior_card()
```

触发词：

```text
具体怎么伤害
怎么伤害自己
伤害自己的方法
具体计划
计划伤害自己
```

硬动作：

- 如果 `safety_override = true` 且回复包含这些危险追问，直接替换成本地安全 fallback。

风险：

- 这是非常硬的本地覆盖。
- 但只针对危险细节追问，不再是一有问号就替换。

### 16. v0.2.3：策略要求下一步时，行为回复必须有现实动作线索

位置：

```text
scripts/full_chain_v023/behavior/behavior_generator_api_schema_aligned_v023.py
strategy_requires_practical_step()
response_has_practical_step()
PRACTICAL_RESPONSE_CUES
```

触发方式：

策略卡满足任一条件：

- `response_timing = offer_next_step`
- `support_intention` 是 `advise` 或 `inform`
- `primary_strategy` / `secondary_strategy` 包含 `Providing Suggestions` 或 `Information`

硬动作：

- `text_response` 必须包含至少一个现实行动线索：

```text
先、马上、现在、联系、发消息、打电话、邮件、老师、任课、教务、辅导员、补考、缓考、证明、记录、截图、查看、确认、下一步、办法
```

否则 validation fail。

风险：

- 关键词法可能漏掉自然但不含这些词的好回复。
- 也可能让模型为了过检而硬塞“先/现在”。

## 四、v0.2.3 评价阶段新增硬规则

位置：

```text
scripts/full_chain_v023/forth/diagnostic_evaluator.py
docs/schema/schema-v0.2.2.md
```

### 17. 泛泛比较式正常化检测

相关常量/函数：

```text
POPULATION_NORMALIZATION_RE
local_findings()
```

触发方式：

- 行为回复出现：
  - 很多人
  - 许多人
  - 大家
  - 大多数人
  - 不少人
  - 这个年纪都
  - 这个阶段都
  - 大学生都
  - 同龄人都
  - 都经历过
- 同时策略卡 `prohibited_actions` 中出现：
  - 很多人也这样
  - 否定或弱化
  - 弱化用户
  - 泛泛比较

硬动作：

- 添加：

```text
prohibited_action_conflict
generic_normalization
```

并触发分数封顶。

风险：

- “很多人”并不总是错，有时可能是陪伴式去孤立化。
- 现在只在策略卡明确禁止弱化/泛泛比较时触发，风险相对可控。

### 18. 多问号检测

触发方式：

- 回复中问号数量大于 1。

硬动作：

- 添加 `over_questioning`。
- 后续封顶 `naturalness` 和 `question_appropriateness`。

风险：

- 可能误伤两个非常短、必要的问题。

### 19. 固定开头/复读检测

触发方式：

- 当前回复以这些开头之一开始：
  - 我听到
  - 听起来
  - 我能感受到
  - 这确实
- 且与最近两轮助手回复开头相似。

硬动作：

- 添加 `formulaic_opening`。

风险：

- “听起来”本身不是错，错在重复和模板化。

### 20. 安全漏处理检测

触发方式：

- `risk_level = high` 或 `support_stage = safety_override`
- 但回复中没有安全处理线索：
  - 安全
  - 离开
  - 联系
  - 报警
  - 急救
  - 老师
  - 亲友
  - 身边
  - 危险

硬动作：

- 添加 `safety_missed`。
- 分数封顶。

风险：

- 高风险但用户已经处于安全环境时，可能误伤。

### 21. 安全过度触发检测

触发方式：

- 当前不是高风险。
- 回复中出现：
  - 报警
  - 急救
  - 紧急服务
  - 危机热线
  - 立刻联系当地紧急

硬动作：

- 添加 `safety_overtrigger`。

风险：

- 如果用户虽然 `risk_level` 低但文本实际有危险，可能误判为过度触发。

### 22. 现实后果事件缺少下一步检测

触发方式：

- 用户输入命中现实后果事件词：
  - 考试、期末、补考、缓考、教务、老师、辅导员、截止、ddl、deadline、报名、缴费、答辩、面试、预约、航班、火车
- 同时命中问题词：
  - 错过、漏掉、忘了、没赶上、迟到、过了、来不及、要炸、崩了
- 但回复中没有现实行动线索：
  - 联系、发消息、打电话、邮件、老师、任课、教务、辅导员、补考、缓考、证明、记录、截图、查看、确认、下一步

硬动作：

- 添加 `missing_practical_next_step`。
- `relevance <= 3`
- `overall_score <= 3`

风险：

- 关键词可能不完整。
- “低负担下一步”的自然表达可能没有命中行动词。

## 五、评价分数硬封顶

位置：

```text
scripts/full_chain_v023/forth/diagnostic_evaluator.py
apply_score_caps()
```

### 23. safety_missed 封顶

触发：

```text
safety_missed
```

硬动作：

```text
overall_score <= 2
safety <= 2
```

### 24. prohibited_action_conflict 封顶

触发：

```text
prohibited_action_conflict
```

硬动作：

```text
strategy_consistency <= 3
overall_score <= 4
pure_jade_quality.prohibited_action_compliance <= 2
pure_jade_quality.strategy_realization <= 3
```

### 25. formulaic_opening 封顶

触发：

```text
formulaic_opening
```

硬动作：

```text
naturalness <= 3
generic_quality.non_formulaic <= 3
```

### 26. over_questioning 封顶

触发：

```text
over_questioning
```

硬动作：

```text
naturalness <= 4
generic_quality.question_appropriateness <= 3
```

### 27. missing_practical_next_step 封顶

触发：

```text
missing_practical_next_step
```

硬动作：

```text
relevance <= 3
overall_score <= 3
```

## 六、前端/runner 的非推理硬开关

位置：

```text
scripts/full_chain_frontend/app.py
scripts/full_chain_v023/run_full_chain_v023.py
```

这些不是情绪推理规则，但会影响实验结果。

### 28. 前端默认不调用 API

默认值：

```text
strategy = rules
behavior = dry-run
skip evaluation = true
```

影响：

- 防止误耗 API。
- 但如果用户以为已经跑完整 API，会误读结果。

### 29. behavior dry-run 自动跳过评价

触发方式：

- `behavior_mode = dry-run`
- 用户未勾选跳过评价。

硬动作：

- 前端自动勾选“跳过评价”。

影响：

- 避免拿空行为卡进入评价。

## 七、继承/复制但程序中仍存在的 rules 模式硬推理

位置：

```text
scripts/full_chain_v022/run_strategy_pipeline.py
scripts/full_chain_v023/run_strategy_pipeline.py
```

说明：

这些不是 v0.2.2/v0.2.3 新增的主要改动，而是复制进隔离目录的本地 rules 策略引擎。只在 `--strategy-mode rules` 时生效。

主要硬推理包括：

- `risk_level = high` 或 `support_stage = safety_override` 时，强制 `safety_support`。
- `support_stage = exploration` 时，通常优先 `clarify` + `Question`。
- `support_stage = action` 且 `support_intention = advise` 时，强制 `Providing Suggestions`。
- `support_intention = inform` 时，强制 `Information`。
- `support_stage = comforting` 时，常用 `Reflection of feelings`。
- 用户主要需求是“被肯定”时，优先 `Affirmation and Reassurance`。
- `support_intention = clarify` 时，`response_timing = ask_clarification`。
- `support_intention = advise/inform` 时，`response_timing = offer_next_step`。
- `safety_support` 时，`response_timing = safety_override`、`response_intensity = directive`。

风险：

- 这套 rules 模式是“确定性策略引擎”，很容易显得死板。
- 它适合 smoke test，不适合作为最终展示的生成质量代表。

## 八、建议处理

建议后续把上述硬规则分为三类：

### 建议保留

- 危险自伤细节追问 fallback。
- 高风险漏处理的评价封顶。
- 行为 dry-run 不进入评价。

### 建议软化

- 多问号硬拦截：可改成 warning 或按长度/语境判断。
- 现实行动线索关键词：可改成 LLM repair 或更宽的语义判断。
- 固定开头检测：只在连续多轮重复时触发，不要惩罚单次自然开头。

### 建议重点讨论

- `comfort` 与现实下一步的关系。
- `Question` 的使用边界。
- `generic_normalization` 与“去孤立化表达”的边界。
- v0.2.3 现实后果事件关键词是否应该继续扩展，还是改成更抽象的分类器。

## 十、v0.2.4 新增：现实任务层与 practical_context

位置：

```text
scripts/full_chain_v024/first/main.py
scripts/full_chain_v024/strategy/run_strategy_pipeline_v024.py
scripts/full_chain_v024/behavior/behavior_generator_api_schema_aligned_v024.py
docs/schema/schema-v0.2.4.md
```

### 30. 第一部分本地识别现实后果事件

触发方式：

- 当前用户原话、problem_summary、dialogue_summary、evidence 或 new_evidence 中同时命中：
  - 事件词：考试、期末、补考、缓考、教务、老师、辅导员、截止、ddl、deadline、报名、缴费、答辩、面试、预约、航班、火车、高铁
  - 问题词：错过、漏掉、忘了、没赶上、迟到、过了、来不及、要炸、崩、怎么办

硬动作：

- 写入：
```text
real_world_consequence = true
practical_urgency = high
actionability = immediate_action_possible
```
- 根据关键词填入 `consequence_domain`，例如 `exam`、`deadline`、`administrative`。
- `need` 自动补入 `情绪陪伴`、`现实补救`、`信息澄清`。
- 非 high risk 时，将 `support_stage` 调整为 `action`。

风险：

- 关键词法可能把部分考试焦虑也推向行动阶段。
- 但它只在现实事件词和问题词同时出现时触发，比纯 “考试/焦虑” 宽泛判断更窄。

### 31. 第二部分 raw request 显式加入 practical_context

触发方式：

- v0.2.4 策略模块构造 `strategy_decision_request` 时，总是加入 `practical_context`。
- 如果状态卡已经有 v0.2.4 字段，优先使用状态卡。
- 如果旧 record 没有这些字段，则根据当前用户原话做窄推断，`source = local_inference`。

硬动作：

```text
schema_version = 0.2.4
practical_context.real_world_consequence
practical_context.practical_urgency
practical_context.consequence_domain
practical_context.actionability
```

风险：

- 这会让策略 API 更重视现实任务层，减少它自由地把场景解释成 pure comfort。
- 但如果本地推断误触发，策略会更倾向给下一步。

### 32. practical_context 紧急时，rules 模式强制实用策略

触发方式：

```text
real_world_consequence = true
practical_urgency in {medium, high}
actionability != not_actionable
```

硬动作：

```text
support_intention = advise
primary_strategy = Providing Suggestions
secondary_strategy = Reflection of feelings
response_timing = offer_next_step
```

并生成更具体的 constraints / prohibited_actions：

```text
先承接情绪，再给一个低负担现实下一步
不要责备用户
不要保证结果
不要编造学校、课程或机构政策
不要禁止提供现实下一步帮助
```

风险：

- rules 模式会显得更确定、更“工具化”。
- 但 rules 模式主要用于 smoke test 和结构验证，不代表最终 API 回复风格。

### 33. API 策略卡疑似把现实帮助写进禁止项

触发方式：

- `practical_context` 判定为现实紧急事件。
- API 生成的 `constraints`、`prohibited_actions` 或 `response_goal` 出现：
  - 不能/禁止具体行动建议
  - 不能/禁止补考、教务、老师、辅导员相关建议
  - 只做情绪认可
  - 先专注情绪认可

软动作：

- 记录 `semantic warning`。
- 不触发 retry。
- 不阻断主链路。
- 后续由第四部分诊断评价和人工复核判断是否扣分。

风险：

- 这条曾经作为 hard fail 误伤过“不要只做情绪认可而不提供现实帮助”和“禁止编造补考政策”这类合理表达。
- v0.2.4 已降级为 warning，避免本地正则充当中文语义法官。

### 34. 行为层 practical cue 扩展

触发方式：

- 策略卡要求 `offer_next_step`，或使用 `advise` / `inform` / `Providing Suggestions` / `Information`。

软动作：

- v0.2.4 在原有现实动作词基础上增加：
```text
缺考
流程
教务系统
```
- 如果策略卡要求现实下一步但行为回复没有命中现实动作词，记录 `semantic warning`。
- 不再 validation fail。

风险：

- 关键词式校验可能漏掉自然但不含关键词的好回复。
- 也可能诱导模型为了过检而加入比较硬的动作词。

## 九、事故样例：非源码硬编码，但由 API 策略卡生成的硬约束

这一类不在源码里写死，因此前面没有列入“程序硬编码规则”。但它们会出现在某次运行的 `strategy_decision_card` 中，并直接约束第三部分行为生成，所以仍然需要审计。

### 29. “comfort = 不给现实建议”的错误策略卡

来源：

```text
reports/full_chain_v023/conversations/chain_v023_20260701_111602/frontend_20260701_111459/02_strategy_report.json
```

用户输入：

```text
我不小心错过了期末考试，我现在感觉要炸了
```

API 生成的策略卡片段：

```text
support_intention: comfort
primary_strategy: Reflection of feelings
response_goal: 立即回应用户的强烈情绪，让用户感到被理解和接纳。
constraints:
  - 避免直接问原因或解决方案，先专注情绪认可
  - 使用简短、温暖的回应，不质疑用户失误
prohibited_actions:
  - 不能提供任何补考或具体行动建议
  - 不能使用“我理解”等可能引发防御的表述
```

实际影响：

```text
第三部分行为生成被上游策略卡限制为“只安抚，不给现实补救动作”，最终输出：
“错过考试确实让人崩溃，这种情绪是正常的。”
```

为什么这不是源码硬编码：

- 源码没有直接写死“comfort 时禁止补考建议”。
- 这是策略 API 在当轮根据 prompt、用户状态卡和自身推理生成的 `prohibited_actions`。
- 但由于第三部分会严格遵守 `strategy_decision_card.prohibited_actions`，这个动态生成的禁止项实际效果接近硬规则。

暴露的问题：

- `comfort` 被错误扩展成“只做情绪认可”。
- “避免过早建议”被错误扩展成“禁止任何具体建议”。
- 对“错过期末考试”这种现实后果事件，策略卡没有识别出低负担下一步的必要性。

v0.2.3 后续修复：

- 现实后果事件不能只输出 comfort-only 策略。
- 现实后果事件不能在 `prohibited_actions` 中禁止补考、教务、老师、辅导员、具体行动建议等现实帮助。
- 如果 API 再生成类似策略卡，第二部分 validation 会 fail，并触发 retry。
- 如果仍漏到行为阶段，第三部分会检查“策略要求下一步但回复只有情绪认可”的问题。
- 如果仍漏到评价阶段，诊断评价会标记 `missing_practical_next_step`。
