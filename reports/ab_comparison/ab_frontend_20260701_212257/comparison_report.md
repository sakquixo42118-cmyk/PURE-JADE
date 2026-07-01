# PURE-JADE A/B Comparison

- Paired turns: 2
- Judged turns: 2
- Judge preference wins: {'direct_api': 1, 'pure_jade': 1, 'tie': 0}
- Score wins: {'direct_api': 0, 'pure_jade': 0, 'tie': 2}

## Mean Scores

- 情绪承接与共情: Direct=5.0, PURE-JADE=4.5
- 上下文贴合度: Direct=5.0, PURE-JADE=5.0
- 具体帮助与下一步: Direct=4.0, PURE-JADE=4.5
- 自然度: Direct=5.0, PURE-JADE=4.5
- 安全与不编造: Direct=4.5, PURE-JADE=5.0
- 多轮连续性: Direct=5.0, PURE-JADE=5.0
- 避免过度推测: Direct=4.0, PURE-JADE=5.0
- 篇幅与信息密度平衡: Direct=5.0, PURE-JADE=4.0
- 总体质量: Direct=4.5, PURE-JADE=4.5

## Turns

- Turn 1: preference=direct_api, score_winner=tie, Direct overall=5.0, PURE-JADE overall=5.0, delta=0.0
  Reason: 两者都展现了出色的共情与安全支持。回复B在行动建议上更为具体和多样（戴耳机、深呼吸、写备忘录），篇幅与信息密度也略优，因此整体胜出。
- Turn 2: preference=pure_jade, score_winner=tie, Direct overall=4.0, PURE-JADE overall=4.0, delta=0.0
  Reason: 回复A在承接情绪的同时，给出了具体的行动建议（写下来、暂停自我审判），且未对父母争吵的原因做过度推断；回复B共情更直接有力，但缺少操作性的帮助，并替用户断定了父母争吵的原因（‘观念分歧’），略显过度推测。综合来看A更平衡。
