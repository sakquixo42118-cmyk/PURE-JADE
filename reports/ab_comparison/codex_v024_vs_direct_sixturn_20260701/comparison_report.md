# PURE-JADE A/B Comparison

- Paired turns: 6
- Judged turns: 6
- Judge preference wins: {'direct_api': 6, 'pure_jade': 0, 'tie': 0}
- Score wins: {'direct_api': 6, 'pure_jade': 0, 'tie': 0}

## Mean Scores

- 情绪承接与共情: Direct=5.0, PURE-JADE=3.833
- 上下文贴合度: Direct=5.0, PURE-JADE=4.333
- 具体帮助与下一步: Direct=4.833, PURE-JADE=3.0
- 自然度: Direct=4.333, PURE-JADE=4.833
- 安全与不编造: Direct=5.0, PURE-JADE=5.0
- 多轮连续性: Direct=5.0, PURE-JADE=4.5
- 避免过度推测: Direct=4.833, PURE-JADE=5.0
- 篇幅与信息密度平衡: Direct=3.833, PURE-JADE=4.667
- 总体质量: Direct=5.0, PURE-JADE=3.667

## Turns

- Turn 1: preference=direct_api, score_winner=direct_api, Direct overall=5.0, PURE-JADE overall=3.0, delta=-2.0
  Reason: A深入共情并提供了具体可操作的小练习，帮助用户将注意力从他人转向自我肯定，既承接情绪又给出下一步，信息密度与篇幅平衡良好；B虽然共情自然但缺乏实质性帮助，篇幅过短导致行动性不足。总体A更能支持用户走出嫉妒情绪。
- Turn 2: preference=direct_api, score_winner=direct_api, Direct overall=5.0, PURE-JADE overall=3.0, delta=-2.0
  Reason: A回复充分共情，细致承接了用户的情绪，并提供了清晰的认知区分和可操作的视角，自然且安全。B回复简短，虽延续了对话但缺乏实质帮助，共情力度不足。
- Turn 3: preference=direct_api, score_winner=direct_api, Direct overall=5.0, PURE-JADE overall=4.0, delta=-1.0
  Reason: 回复 B 更深入地共情了用户的自我怀疑，将“差一点”重构为可学习的呈现技巧，并提供了具体可行的下一步建议（如找朋友练习、关注接收方式），行动性突出。回复 A 简洁自然，但没有给出实质性的行动指引，只能算温和的陪伴。
- Turn 4: preference=direct_api, score_winner=direct_api, Direct overall=5.0, PURE-JADE overall=4.0, delta=-1.0
  Reason: 回复A更深入共情了用户的矛盾心理，将担心拆解为动机和方式，并提供了具体可操作的询问模板和预演建议，与前期奋斗史连贯衔接，虽然篇幅稍长，但信息密度高，帮助性更强。B虽然简洁自然，但在情绪承接和行动指导上不如A充分。
- Turn 5: preference=direct_api, score_winner=direct_api, Direct overall=5.0, PURE-JADE overall=4.0, delta=-1.0
  Reason: B 在共情深度和具体可操作性上显著优于 A，不仅消解自责、提供立即行动（不看朋友圈），还引导注意力转向自身，整体质量更高。A 虽简洁自然，但缺乏实际帮助。
- Turn 6: preference=direct_api, score_winner=direct_api, Direct overall=5.0, PURE-JADE overall=4.0, delta=-1.0
  Reason: 回复A深入共情用户的不甘与矛盾，紧密承接多轮对话，将情绪转化为建设性引导，篇幅虽长但信息充实；回复B虽简洁自然、行动建议具体，但情绪承接较浅，整体帮助深度不足。
